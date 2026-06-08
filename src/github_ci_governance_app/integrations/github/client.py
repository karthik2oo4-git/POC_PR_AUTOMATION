from __future__ import annotations

from typing import Any

import httpx

from github_ci_governance_app.core.settings import Settings
from github_ci_governance_app.integrations.github.auth import build_app_jwt


class GitHubClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def create_installation_token(self, installation_id: int) -> str:
        jwt_token = build_app_jwt(self._settings)
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json",
        }
        async with httpx.AsyncClient(base_url=self._settings.github_api_url, timeout=20.0) as client:
            response = await client.post(
                f"/app/installations/{installation_id}/access_tokens",
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
            return str(payload["token"])

    async def dispatch_workflow(
        self,
        installation_token: str,
        owner: str,
        repo: str,
        workflow_file: str,
        ref: str,
        inputs: dict[str, str],
    ) -> None:
        headers = {
            "Authorization": f"token {installation_token}",
            "Accept": "application/vnd.github+json",
        }
        body: dict[str, Any] = {"ref": ref, "inputs": inputs}
        async with httpx.AsyncClient(base_url=self._settings.github_api_url, timeout=20.0) as client:
            response = await client.post(
                f"/repos/{owner}/{repo}/actions/workflows/{workflow_file}/dispatches",
                headers=headers,
                json=body,
            )
            response.raise_for_status()

# Made with Bob
