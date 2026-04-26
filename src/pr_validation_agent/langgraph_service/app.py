from __future__ import annotations

from functools import lru_cache
from typing import Literal

import uvicorn
from fastapi import FastAPI

from pr_validation_agent.langgraph_service.graph import AnalysisGraph
from pr_validation_agent.models import AnalysisRequest, AnalysisResponse


@lru_cache(maxsize=1)
def get_graph() -> AnalysisGraph:
    return AnalysisGraph()


def create_app() -> FastAPI:
    app = FastAPI(
        title="PR Validation LangGraph Service",
        version="0.1.0",
        description="LLM analysis service for CI-driven pull request validation.",
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/analyze/{mode}", response_model=AnalysisResponse)
    def analyze(
        mode: Literal["failure", "coverage", "summary"],
        request: AnalysisRequest,
    ) -> AnalysisResponse:
        return get_graph().invoke(request, mode)

    return app


def main() -> None:
    uvicorn.run("pr_validation_agent.langgraph_service.app:create_app", factory=True)


if __name__ == "__main__":
    main()
