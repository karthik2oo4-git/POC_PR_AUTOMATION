from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ValidationState(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"
    PENDING = "pending"


class FunctionKind(StrEnum):
    FUNCTION = "function"
    METHOD = "method"


class FunctionSymbol(BaseModel):
    name: str
    qualified_name: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    kind: FunctionKind
    signature: str = ""
    body_hash: str = ""


class FunctionChange(BaseModel):
    symbol: FunctionSymbol
    change_type: Literal["new", "modified"]


class TestRunResult(BaseModel):
    command: str
    exit_code: int
    passed: bool
    duration_seconds: float
    log_path: str | None = None
    stdout: str = ""
    stderr: str = ""


class TestCoverageFinding(BaseModel):
    symbol: FunctionSymbol
    has_test: bool
    evidence: list[str] = Field(default_factory=list)
    suggested_tests: list[str] = Field(default_factory=list)


class CoverageResult(BaseModel):
    passed: bool
    findings: list[TestCoverageFinding] = Field(default_factory=list)


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


class AnalysisRequest(BaseModel):
    pr: PullRequestContext
    files_changed: list[str]
    new_functions: list[FunctionSymbol] = Field(default_factory=list)
    modified_functions: list[FunctionSymbol] = Field(default_factory=list)
    test_result: TestRunResult | None = None
    coverage_findings: list[TestCoverageFinding] = Field(default_factory=list)
    diff_excerpt: str = ""
    log_excerpt: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class FailureAnalysis(BaseModel):
    failing_tests: list[str] = Field(default_factory=list)
    root_cause: str = ""
    suggested_fix: str = ""


class CoverageAnalysis(BaseModel):
    missing_tests: list[TestCoverageFinding] = Field(default_factory=list)
    notes: str = ""


class SummaryAnalysis(BaseModel):
    high_level_summary: str = ""
    risk_insights: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    failure_analysis: FailureAnalysis | None = None
    coverage_analysis: CoverageAnalysis | None = None
    summary: SummaryAnalysis | None = None


class ValidationResult(BaseModel):
    state: ValidationState
    reason: str
    files_changed: list[str] = Field(default_factory=list)
    new_functions: list[FunctionSymbol] = Field(default_factory=list)
    modified_functions: list[FunctionSymbol] = Field(default_factory=list)
    test_result: TestRunResult | None = None
    coverage_result: CoverageResult | None = None
    analysis: AnalysisResponse | None = None
