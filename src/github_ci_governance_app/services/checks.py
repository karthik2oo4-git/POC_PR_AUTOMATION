from __future__ import annotations

from collections.abc import MutableMapping

from github_ci_governance_app.domain.governance_models import CheckRunRequest


class InMemoryCheckPublisher:
    def __init__(self) -> None:
        self._checks: MutableMapping[str, CheckRunRequest] = {}

    async def publish(self, request: CheckRunRequest) -> CheckRunRequest:
        key = f"{request.repository.full_name}:{request.sha}:{request.name}"
        self._checks[key] = request
        return request

    async def get(self, repository: str, sha: str, name: str) -> CheckRunRequest | None:
        return self._checks.get(f"{repository}:{sha}:{name}")

# Made with Bob
