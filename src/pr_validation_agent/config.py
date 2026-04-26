from __future__ import annotations

from pathlib import Path
from typing import Literal
from typing import Any

import yaml
from pydantic import BaseModel, Field


class StatusConfig(BaseModel):
    context: str = "intelligent-pr-validation"
    target_url: str = ""


class TestsConfig(BaseModel):
    command: str = "pytest -q"
    timeout_seconds: int = 900
    log_max_bytes: int = 120_000
    parallel_hint: str = ""


class SetupConfig(BaseModel):
    commands: list[str] = Field(default_factory=list)
    timeout_seconds: int = 600


class LanguageConfig(BaseModel):
    enabled: bool = True
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)


class TestDetectionConfig(BaseModel):
    test_file_patterns: list[str] = Field(default_factory=list)
    require_symbol_reference: bool = True
    allow_llm_coverage_review: bool = True


class ReviewersConfig(BaseModel):
    request_review_when_passed: bool = True
    fallback_reviewers: list[str] = Field(default_factory=list)
    fallback_teams: list[str] = Field(default_factory=list)


class LabelsConfig(BaseModel):
    enabled: bool = True
    remove_stale: bool = True
    create_missing: bool = True
    test_failed: str = "test-failed"
    needs_tests: str = "needs-tests"
    ready_for_review: str = "ready-for-review"
    merge_conflict: str = "merge-conflict"

    def outcome_labels(self) -> list[str]:
        return [
            label
            for label in [
                self.test_failed,
                self.needs_tests,
                self.ready_for_review,
                self.merge_conflict,
            ]
            if label
        ]


class AutoMergeConfig(BaseModel):
    enabled: bool = False
    method: Literal["MERGE", "SQUASH", "REBASE"] = "SQUASH"


class CodeReviewConfig(BaseModel):
    enabled: bool = False
    command: str = ""
    timeout_seconds: int = 600
    log_max_bytes: int = 40_000


class CommentsConfig(BaseModel):
    marker: str = "<!-- pr-validation-agent:summary -->"
    max_log_lines: int = 120


class AppConfig(BaseModel):
    version: int = 1
    status: StatusConfig = Field(default_factory=StatusConfig)
    setup: SetupConfig = Field(default_factory=SetupConfig)
    tests: TestsConfig = Field(default_factory=TestsConfig)
    languages: dict[str, LanguageConfig] = Field(default_factory=dict)
    test_detection: TestDetectionConfig = Field(default_factory=TestDetectionConfig)
    reviewers: ReviewersConfig = Field(default_factory=ReviewersConfig)
    labels: LabelsConfig = Field(default_factory=LabelsConfig)
    code_review: CodeReviewConfig = Field(default_factory=CodeReviewConfig)
    auto_merge: AutoMergeConfig = Field(default_factory=AutoMergeConfig)
    comments: CommentsConfig = Field(default_factory=CommentsConfig)

    @classmethod
    def load(cls, path: str | Path) -> "AppConfig":
        config_path = Path(path)
        if not config_path.exists():
            return cls()
        with config_path.open("r", encoding="utf-8") as handle:
            raw: dict[str, Any] = yaml.safe_load(handle) or {}
        return cls.model_validate(raw)
