from __future__ import annotations

from fnmatch import fnmatch

from github_ci_governance_app.domain.governance_models import ValidationStatus
from github_ci_governance_app.domain.models import MissingTestCoverage, TestEnforcementResult
from github_ci_governance_app.services.language_rules import expected_test_patterns


class TestEnforcementService:
    def evaluate(self, added_files: list[str], repository_files: list[str]) -> TestEnforcementResult:
        missing: list[MissingTestCoverage] = []

        for path in added_files:
            patterns = expected_test_patterns(path)
            if not patterns:
                continue

            if any(self._matches_any_pattern(repository_files, pattern) for pattern in patterns):
                continue

            missing.append(MissingTestCoverage(source_file=path, expected_patterns=patterns))

        status = ValidationStatus.SUCCESS if not missing else ValidationStatus.FAILURE
        return TestEnforcementResult(status=status, missing=missing)

    @staticmethod
    def _matches_any_pattern(repository_files: list[str], pattern: str) -> bool:
        return any(fnmatch(candidate, pattern) for candidate in repository_files)

# Made with Bob
