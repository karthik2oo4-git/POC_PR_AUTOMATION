from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from github_ci_governance_app.domain.governance_models import ValidationStatus


class CheckConclusion(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


class ValidationStage(str, Enum):
    BASIC = "basic"
    HEAVY = "heavy"
    TEST_ENFORCEMENT = "test_enforcement"


@dataclass(slots=True)
class RepositoryRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(slots=True)
class PullRequestRef:
    repository: RepositoryRef
    number: int
    head_sha: str
    base_ref: str
    head_ref: str


@dataclass(slots=True)
class WorkflowDispatchRequest:
    repository: RepositoryRef
    workflow_file: str
    ref: str
    inputs: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class MissingTestCoverage:
    source_file: str
    expected_patterns: list[str]


@dataclass(slots=True)
class TestEnforcementResult:
    status: ValidationStatus
    missing: list[MissingTestCoverage] = field(default_factory=list)

# Made with Bob
