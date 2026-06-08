from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class ValidationStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class ValidationType(str, Enum):
    LIGHTWEIGHT = "lightweight"
    HEAVY = "heavy"
    TEST_ENFORCEMENT = "test_enforcement"


@dataclass(slots=True, frozen=True)
class RepositoryContext:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(slots=True, frozen=True)
class ValidationKey:
    repository: str
    branch: str
    sha: str
    validation_type: ValidationType


@dataclass(slots=True)
class ValidationRecord:
    repository: str
    branch: str
    sha: str
    validation_type: ValidationType
    status: ValidationStatus
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    workflow_run_id: int | None = None
    check_run_id: int | None = None
    details_url: str | None = None
    summary: str | None = None

    @property
    def key(self) -> ValidationKey:
        return ValidationKey(
            repository=self.repository,
            branch=self.branch,
            sha=self.sha,
            validation_type=self.validation_type,
        )


@dataclass(slots=True, frozen=True)
class PushContext:
    repository: RepositoryContext
    branch: str
    sha: str
    installation_id: int
    delivery_id: str


@dataclass(slots=True, frozen=True)
class PullRequestContext:
    repository: RepositoryContext
    number: int
    branch: str
    base_branch: str
    sha: str
    installation_id: int
    delivery_id: str


@dataclass(slots=True, frozen=True)
class WorkflowRunContext:
    repository: RepositoryContext
    branch: str
    sha: str
    workflow_name: str
    workflow_run_id: int
    conclusion: ValidationStatus
    details_url: str | None
    installation_id: int
    delivery_id: str


@dataclass(slots=True, frozen=True)
class CheckRunRequest:
    repository: RepositoryContext
    sha: str
    name: str
    status: ValidationStatus
    summary: str
    details_url: str | None = None
    external_id: str | None = None


@dataclass(slots=True, frozen=True)
class PullRequestCommentRequest:
    repository: RepositoryContext
    pr_number: int
    body: str
    deduplication_key: str


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0

# Made with Bob
