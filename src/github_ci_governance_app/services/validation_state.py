from __future__ import annotations

from collections.abc import MutableMapping

from github_ci_governance_app.domain.governance_models import ValidationKey, ValidationRecord, ValidationStatus, ValidationType


class InMemoryValidationStateStore:
    def __init__(self) -> None:
        self._records: MutableMapping[ValidationKey, ValidationRecord] = {}

    def upsert(self, record: ValidationRecord) -> ValidationRecord:
        self._records[record.key] = record
        return record

    def get(
        self,
        repository: str,
        branch: str,
        sha: str,
        validation_type: ValidationType,
    ) -> ValidationRecord | None:
        key = ValidationKey(
            repository=repository,
            branch=branch,
            sha=sha,
            validation_type=validation_type,
        )
        return self._records.get(key)

    def latest_for_sha(
        self,
        repository: str,
        branch: str,
        sha: str,
        validation_type: ValidationType,
    ) -> ValidationRecord | None:
        return self.get(repository=repository, branch=branch, sha=sha, validation_type=validation_type)

    def has_successful_validation(
        self,
        repository: str,
        branch: str,
        sha: str,
        validation_type: ValidationType,
    ) -> bool:
        record = self.latest_for_sha(
            repository=repository,
            branch=branch,
            sha=sha,
            validation_type=validation_type,
        )
        return record is not None and record.status == ValidationStatus.SUCCESS

# Made with Bob
