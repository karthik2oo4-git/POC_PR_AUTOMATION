from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from pr_validation_agent.config import AppConfig
from pr_validation_agent.models import PullRequestContext, ValidationState


class GitHubError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubClient:
    token: str
    api_url: str = "https://api.github.com"

    @classmethod
    def from_env(cls) -> "GitHubClient":
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise GitHubError("GITHUB_TOKEN is required")
        return cls(token=token, api_url=os.getenv("GITHUB_API_URL", "https://api.github.com"))

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self.api_url.rstrip('/')}{path}"
        response = httpx.request(method, url, headers=self._headers, timeout=30, **kwargs)
        if response.status_code >= 400:
            raise GitHubError(f"GitHub API {method} {path} failed: {response.text}")
        return response

    def load_pr_context_from_event(self, event: dict[str, Any]) -> PullRequestContext:
        repo = event["repository"]
        pr = event["pull_request"]
        return PullRequestContext(
            owner=repo["owner"]["login"],
            repo=repo["name"],
            number=pr["number"],
            node_id=pr.get("node_id", ""),
            author=pr["user"]["login"],
            head_sha=pr["head"]["sha"],
            base_sha=pr["base"]["sha"],
            head_ref=pr["head"]["ref"],
            base_ref=pr["base"]["ref"],
            html_url=pr["html_url"],
            requested_reviewers=[reviewer["login"] for reviewer in pr.get("requested_reviewers", [])],
            requested_teams=[team["slug"] for team in pr.get("requested_teams", [])],
        )

    def set_status(
        self,
        pr: PullRequestContext,
        state: ValidationState,
        description: str,
        config: AppConfig,
    ) -> None:
        self._request(
            "POST",
            f"/repos/{pr.owner}/{pr.repo}/statuses/{pr.head_sha}",
            json={
                "state": state.value,
                "context": config.status.context,
                "description": description[:140],
                "target_url": config.status.target_url or pr.html_url,
            },
        )

    def upsert_comment(self, pr: PullRequestContext, marker: str, body: str) -> None:
        comments = self._request(
            "GET",
            f"/repos/{pr.owner}/{pr.repo}/issues/{pr.number}/comments?per_page=100",
        ).json()
        existing = next(
            (
                comment
                for comment in comments
                if comment.get("user", {}).get("type") == "Bot" and marker in comment.get("body", "")
            ),
            None,
        )
        if existing:
            self._request(
                "PATCH",
                f"/repos/{pr.owner}/{pr.repo}/issues/comments/{existing['id']}",
                json={"body": body},
            )
            return
        self._request(
            "POST",
            f"/repos/{pr.owner}/{pr.repo}/issues/{pr.number}/comments",
            json={"body": body},
        )

    def request_reviewers(self, pr: PullRequestContext, config: AppConfig) -> list[str]:
        if not config.reviewers.request_review_when_passed:
            return []
        reviewers = pr.requested_reviewers or config.reviewers.fallback_reviewers
        teams = pr.requested_teams or config.reviewers.fallback_teams
        mentions = [f"@{reviewer}" for reviewer in reviewers] + [f"@{team}" for team in teams]
        if not reviewers and not teams:
            return mentions
        self._request(
            "POST",
            f"/repos/{pr.owner}/{pr.repo}/pulls/{pr.number}/requested_reviewers",
            json={"reviewers": reviewers, "team_reviewers": teams},
        )
        return mentions

    def ensure_label(self, pr: PullRequestContext, name: str) -> None:
        if not name:
            return
        response = httpx.post(
            f"{self.api_url.rstrip('/')}/repos/{pr.owner}/{pr.repo}/labels",
            headers=self._headers,
            timeout=30,
            json={"name": name, "color": "ededed", "description": "Managed by PR Validation Agent"},
        )
        if response.status_code not in {201, 422}:
            raise GitHubError(f"GitHub API create label failed: {response.text}")

    def add_labels(self, pr: PullRequestContext, labels: list[str]) -> None:
        labels = [label for label in labels if label]
        if not labels:
            return
        self._request(
            "POST",
            f"/repos/{pr.owner}/{pr.repo}/issues/{pr.number}/labels",
            json={"labels": labels},
        )

    def remove_label(self, pr: PullRequestContext, label: str) -> None:
        if not label:
            return
        url = (
            f"{self.api_url.rstrip('/')}/repos/{pr.owner}/{pr.repo}/issues/"
            f"{pr.number}/labels/{quote(label, safe='')}"
        )
        response = httpx.delete(url, headers=self._headers, timeout=30)
        if response.status_code in {200, 404}:
            return
        if response.status_code >= 400:
            raise GitHubError(f"GitHub API remove label failed: {response.text}")

    def apply_outcome_label(self, pr: PullRequestContext, config: AppConfig, label: str) -> None:
        if not config.labels.enabled or not label:
            return
        if config.labels.create_missing:
            self.ensure_label(pr, label)
        if config.labels.remove_stale:
            for stale_label in config.labels.outcome_labels():
                if stale_label != label:
                    self.remove_label(pr, stale_label)
        self.add_labels(pr, [label])

    def enable_auto_merge(self, pr: PullRequestContext, config: AppConfig) -> None:
        if not config.auto_merge.enabled or not pr.node_id:
            return
        response = httpx.post(
            f"{self.api_url.rstrip('/')}/graphql",
            headers=self._headers,
            timeout=30,
            json={
                "query": """
                mutation EnableAutoMerge($input: EnablePullRequestAutoMergeInput!) {
                  enablePullRequestAutoMerge(input: $input) {
                    pullRequest {
                      number
                    }
                  }
                }
                """,
                "variables": {
                    "input": {
                        "pullRequestId": pr.node_id,
                        "mergeMethod": config.auto_merge.method,
                    }
                },
            },
        )
        if response.status_code >= 400:
            raise GitHubError(f"GitHub API enable auto-merge failed: {response.text}")
        payload = response.json()
        if payload.get("errors"):
            raise GitHubError(f"GitHub API enable auto-merge failed: {payload['errors']}")
