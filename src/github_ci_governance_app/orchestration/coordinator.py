from __future__ import annotations

from github_ci_governance_app.core.settings import Settings
from github_ci_governance_app.domain.models import PullRequestRef, WorkflowDispatchRequest
from github_ci_governance_app.integrations.github.client import GitHubClient


class ValidationCoordinator:
    def __init__(self, settings: Settings, github_client: GitHubClient) -> None:
        self._settings = settings
        self._github_client = github_client

    async def dispatch_basic_validation(
        self,
        installation_id: int,
        owner: str,
        repo: str,
        sha: str,
    ) -> None:
        token = await self._github_client.create_installation_token(installation_id)
        request = WorkflowDispatchRequest(
            repository={"owner": owner, "name": repo},  # type: ignore[arg-type]
            workflow_file=self._settings.basic_validation_workflow,
            ref=sha,
            inputs={"sha": sha, "stage": "basic"},
        )
        await self._github_client.dispatch_workflow(
            installation_token=token,
            owner=owner,
            repo=repo,
            workflow_file=request.workflow_file,
            ref=request.ref,
            inputs=request.inputs,
        )

    async def dispatch_heavy_validation(
        self,
        installation_id: int,
        pull_request: PullRequestRef,
    ) -> None:
        token = await self._github_client.create_installation_token(installation_id)
        await self._github_client.dispatch_workflow(
            installation_token=token,
            owner=pull_request.repository.owner,
            repo=pull_request.repository.name,
            workflow_file=self._settings.heavy_validation_workflow,
            ref=pull_request.head_ref,
            inputs={"sha": pull_request.head_sha, "pr_number": str(pull_request.number), "stage": "heavy"},
        )

# Made with Bob
