from __future__ import annotations

from github_ci_governance_app.domain.governance_models import (
    CheckRunRequest,
    PullRequestCommentRequest,
    PullRequestContext,
    ValidationStatus,
)
from github_ci_governance_app.domain.models import TestEnforcementResult
from github_ci_governance_app.services.checks import InMemoryCheckPublisher
from github_ci_governance_app.services.comments import InMemoryPullRequestCommentService
from github_ci_governance_app.services.test_enforcement import TestEnforcementService
from github_ci_governance_app.services.validation_state import InMemoryValidationStateStore


class PullRequestGovernanceService:
    def __init__(
        self,
        validation_state: InMemoryValidationStateStore,
        checks: InMemoryCheckPublisher,
        comments: InMemoryPullRequestCommentService,
        test_enforcement: TestEnforcementService,
    ) -> None:
        self._validation_state = validation_state
        self._checks = checks
        self._comments = comments
        self._test_enforcement = test_enforcement

    async def enforce_tests(
        self,
        context: PullRequestContext,
        added_files: list[str],
        repository_files: list[str],
    ) -> TestEnforcementResult:
        result = self._test_enforcement.evaluate(added_files=added_files, repository_files=repository_files)
        await self._checks.publish(
            CheckRunRequest(
                repository=context.repository,
                sha=context.sha,
                name="Test Enforcement",
                status=result.status,
                summary=self._build_summary(result),
                external_id=f"{context.delivery_id}:test-enforcement",
            )
        )
        if result.status == ValidationStatus.FAILURE:
            await self._comments.publish_once(
                request=self._build_comment_request(context=context, result=result)
            )
        return result

    @staticmethod
    def is_latest_sha(current_pr_sha: str, candidate_sha: str) -> bool:
        return current_pr_sha == candidate_sha

    @staticmethod
    def _build_summary(result: TestEnforcementResult) -> str:
        if result.status == ValidationStatus.SUCCESS:
            return "All newly added source files have matching tests."
        missing_files = ", ".join(item.source_file for item in result.missing)
        return f"Missing test files detected for: {missing_files}"

    @staticmethod
    def _build_comment_request(
        context: PullRequestContext,
        result: TestEnforcementResult,
    ) -> PullRequestCommentRequest:
        lines = ["Missing test coverage detected:", ""]
        for item in result.missing:
            lines.append(f"- {item.source_file}")
            for pattern in item.expected_patterns:
                lines.append(f"  - Expected test file: {pattern}")
        body = "\n".join(lines)
        return PullRequestCommentRequest(
            repository=context.repository,
            pr_number=context.number,
            body=body,
            deduplication_key=f"missing-tests:{context.sha}",
        )

# Made with Bob
