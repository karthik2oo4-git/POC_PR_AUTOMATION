from __future__ import annotations

from github_ci_governance_app.core.logging import get_logger
from github_ci_governance_app.core.settings import Settings
from github_ci_governance_app.domain.governance_models import (
    CheckRunRequest,
    PullRequestCommentRequest,
    PullRequestContext,
    PushContext,
    RepositoryContext,
    ValidationRecord,
    ValidationStatus,
    ValidationType,
    WorkflowRunContext,
)
from github_ci_governance_app.integrations.github.client import GitHubClient
from github_ci_governance_app.services.checks import InMemoryCheckPublisher
from github_ci_governance_app.services.comments import InMemoryPullRequestCommentService
from github_ci_governance_app.services.retry import with_retry
from github_ci_governance_app.services.validation_state import InMemoryValidationStateStore

logger = get_logger(__name__)


class GovernanceService:
    def __init__(
        self,
        settings: Settings,
        github_client: GitHubClient,
        validation_state: InMemoryValidationStateStore,
        checks: InMemoryCheckPublisher,
        comments: InMemoryPullRequestCommentService,
    ) -> None:
        self._settings = settings
        self._github_client = github_client
        self._validation_state = validation_state
        self._checks = checks
        self._comments = comments

    async def handle_push(self, context: PushContext) -> dict[str, str]:
        if self._is_protected_branch(context.branch):
            logger.info(
                "push_ignored repository=%s event=push sha=%s pr_number=%s delivery_id=%s branch=%s",
                context.repository.full_name,
                context.sha,
                "none",
                context.delivery_id,
                context.branch,
            )
            return {"status": "ignored", "reason": "protected_branch"}

        await self._checks.publish(
            CheckRunRequest(
                repository=context.repository,
                sha=context.sha,
                name="Lightweight Validation",
                status=ValidationStatus.IN_PROGRESS,
                summary="Lightweight validation has started.",
                external_id=context.delivery_id,
            )
        )
        self._validation_state.upsert(
            ValidationRecord(
                repository=context.repository.full_name,
                branch=context.branch,
                sha=context.sha,
                validation_type=ValidationType.LIGHTWEIGHT,
                status=ValidationStatus.IN_PROGRESS,
                summary="Lightweight validation dispatched.",
            )
        )

        async def dispatch() -> None:
            token = await self._github_client.create_installation_token(context.installation_id)
            await self._github_client.dispatch_workflow(
                installation_token=token,
                owner=context.repository.owner,
                repo=context.repository.name,
                workflow_file=self._settings.basic_validation_workflow,
                ref=context.branch,
                inputs={"sha": context.sha, "branch": context.branch, "validation_type": "lightweight"},
            )

        await with_retry(dispatch, policy=self._settings.retry_policy)
        logger.info(
            "push_processed repository=%s event=push sha=%s pr_number=%s delivery_id=%s branch=%s",
            context.repository.full_name,
            context.sha,
            "none",
            context.delivery_id,
            context.branch,
        )
        return {"status": "accepted", "validation": "lightweight"}

    async def handle_pull_request(self, context: PullRequestContext) -> dict[str, str]:
        lightweight_ready = self._validation_state.has_successful_validation(
            repository=context.repository.full_name,
            branch=context.branch,
            sha=context.sha,
            validation_type=ValidationType.LIGHTWEIGHT,
        )
        if not lightweight_ready:
            await self._checks.publish(
                CheckRunRequest(
                    repository=context.repository,
                    sha=context.sha,
                    name="Heavy Validation",
                    status=ValidationStatus.QUEUED,
                    summary="Waiting for lightweight validation to complete.",
                    external_id=context.delivery_id,
                )
            )
            logger.info(
                "pr_waiting_for_lightweight repository=%s event=pull_request sha=%s pr_number=%s delivery_id=%s",
                context.repository.full_name,
                context.sha,
                context.number,
                context.delivery_id,
            )
            return {"status": "queued", "validation": "heavy"}

        await self._checks.publish(
            CheckRunRequest(
                repository=context.repository,
                sha=context.sha,
                name="Heavy Validation",
                status=ValidationStatus.IN_PROGRESS,
                summary="Heavy validation has started.",
                external_id=context.delivery_id,
            )
        )
        self._validation_state.upsert(
            ValidationRecord(
                repository=context.repository.full_name,
                branch=context.branch,
                sha=context.sha,
                validation_type=ValidationType.HEAVY,
                status=ValidationStatus.IN_PROGRESS,
                summary="Heavy validation dispatched.",
            )
        )

        async def dispatch() -> None:
            token = await self._github_client.create_installation_token(context.installation_id)
            await self._github_client.dispatch_workflow(
                installation_token=token,
                owner=context.repository.owner,
                repo=context.repository.name,
                workflow_file=self._settings.heavy_validation_workflow,
                ref=context.branch,
                inputs={
                    "sha": context.sha,
                    "branch": context.branch,
                    "pr_number": str(context.number),
                    "validation_type": "heavy",
                },
            )

        await with_retry(dispatch, policy=self._settings.retry_policy)
        logger.info(
            "pr_processed repository=%s event=pull_request sha=%s pr_number=%s delivery_id=%s",
            context.repository.full_name,
            context.sha,
            context.number,
            context.delivery_id,
        )
        return {"status": "accepted", "validation": "heavy"}

    async def handle_workflow_run(self, context: WorkflowRunContext) -> dict[str, str]:
        validation_type = self._workflow_to_validation_type(context.workflow_name)
        self._validation_state.upsert(
            ValidationRecord(
                repository=context.repository.full_name,
                branch=context.branch,
                sha=context.sha,
                validation_type=validation_type,
                status=context.conclusion,
                workflow_run_id=context.workflow_run_id,
                details_url=context.details_url,
                summary=f"{context.workflow_name} completed with status {context.conclusion.value}.",
            )
        )
        await self._checks.publish(
            CheckRunRequest(
                repository=context.repository,
                sha=context.sha,
                name=self._check_name_for_validation(validation_type),
                status=context.conclusion,
                summary=f"{context.workflow_name} completed with status {context.conclusion.value}.",
                details_url=context.details_url,
                external_id=str(context.workflow_run_id),
            )
        )
        logger.info(
            "workflow_processed repository=%s event=workflow_run sha=%s pr_number=%s delivery_id=%s workflow=%s",
            context.repository.full_name,
            context.sha,
            "none",
            context.delivery_id,
            context.workflow_name,
        )
        return {"status": "accepted", "workflow": context.workflow_name}

    async def publish_missing_test_comment(
        self,
        repository: RepositoryContext,
        pr_number: int,
        body: str,
        deduplication_key: str,
    ) -> None:
        await self._comments.publish_once(
            PullRequestCommentRequest(
                repository=repository,
                pr_number=pr_number,
                body=body,
                deduplication_key=deduplication_key,
            )
        )

    @staticmethod
    def _is_protected_branch(branch: str) -> bool:
        return branch in {"main", "master"} or branch.startswith("release/") or branch.startswith("hotfix/")

    def _workflow_to_validation_type(self, workflow_name: str) -> ValidationType:
        lowered = workflow_name.lower()
        if "heavy" in lowered:
            return ValidationType.HEAVY
        return ValidationType.LIGHTWEIGHT

    @staticmethod
    def _check_name_for_validation(validation_type: ValidationType) -> str:
        if validation_type == ValidationType.HEAVY:
            return "Heavy Validation"
        if validation_type == ValidationType.TEST_ENFORCEMENT:
            return "Test Enforcement"
        return "Lightweight Validation"

# Made with Bob
