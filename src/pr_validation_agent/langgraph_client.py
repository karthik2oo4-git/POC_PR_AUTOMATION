from __future__ import annotations

import os

import httpx

from pr_validation_agent.models import AnalysisRequest, AnalysisResponse


class LangGraphClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("LANGGRAPH_SERVICE_URL") or "").rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def analyze(self, request: AnalysisRequest, mode: str) -> AnalysisResponse:
        if not self.enabled:
            return AnalysisResponse()
        response = httpx.post(
            f"{self.base_url}/v1/analyze/{mode}",
            json=request.model_dump(mode="json"),
            timeout=60,
        )
        response.raise_for_status()
        return AnalysisResponse.model_validate(response.json())
