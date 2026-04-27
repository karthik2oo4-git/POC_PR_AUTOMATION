from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ValidationState(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    PENDING = "pending"


class TestRunResult(BaseModel):
    command: str
    exit_code: int
    passed: bool
    duration_seconds: float
    log_path: str | None = None
    stdout: str = ""
    stderr: str = ""


class PullRequestContext(BaseModel):
    owner: str
    repo: str
    number: int
    node_id: str = ""
    author: str
    head_sha: str
    base_sha: str
    head_ref: str
    base_ref: str
    html_url: str = ""
    requested_reviewers: list[str] = Field(default_factory=list)
    requested_teams: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    state: ValidationState
    reason: str
    phase: str = ""
    outcome_label: str = ""
    notify_users: list[str] = Field(default_factory=list)
    test_result: TestRunResult | None = None
