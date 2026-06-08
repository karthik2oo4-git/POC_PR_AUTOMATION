from __future__ import annotations

from collections.abc import MutableMapping

from github_ci_governance_app.domain.governance_models import PullRequestCommentRequest


class InMemoryPullRequestCommentService:
    def __init__(self) -> None:
        self._comments: MutableMapping[str, PullRequestCommentRequest] = {}

    async def publish_once(self, request: PullRequestCommentRequest) -> PullRequestCommentRequest:
        key = f"{request.repository.full_name}:{request.pr_number}:{request.deduplication_key}"
        self._comments[key] = request
        return request

    async def exists(self, repository: str, pr_number: int, deduplication_key: str) -> bool:
        key = f"{repository}:{pr_number}:{deduplication_key}"
        return key in self._comments

# Made with Bob
