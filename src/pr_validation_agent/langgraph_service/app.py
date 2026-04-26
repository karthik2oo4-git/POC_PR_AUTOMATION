from __future__ import annotations

import time
from functools import lru_cache
from typing import Annotated, Literal

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, status

from pr_validation_agent.langgraph_service.auth import verify_token
from pr_validation_agent.langgraph_service.graph import AnalysisGraph
from pr_validation_agent.langgraph_service.logging_config import (
    StructuredLoggingMiddleware,
    log_analysis_request,
    log_analysis_response,
)
from pr_validation_agent.langgraph_service.service_protections import (
    ConcurrencyLimitMiddleware,
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    validate_analysis_request_fields,
)
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

    # Add middleware in reverse order (last added = first executed)
    # This ensures proper ordering of security, logging, and rate limiting
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(ConcurrencyLimitMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(StructuredLoggingMiddleware)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Health check endpoint (public, no auth required)."""
        return {"status": "ok"}

    @app.post("/v1/analyze/{mode}", response_model=AnalysisResponse)
    async def analyze(
        mode: Literal["failure", "coverage", "summary"],
        request: AnalysisRequest,
        _: Annotated[None, Depends(verify_token)] = None,
    ) -> AnalysisResponse:
        """Analyze pull request with specified mode.
        
        Requires LANGGRAPH_SERVICE_TOKEN authorization header if configured.
        
        Args:
            mode: Analysis mode (failure, coverage, or summary)
            request: Pull request analysis request
            _: Token verification dependency
            
        Returns:
            AnalysisResponse with analysis results
            
        Raises:
            HTTPException: 401 if auth fails, 400 if validation fails
        """
        # Validate required fields
        try:
            validate_analysis_request_fields(request.model_dump())
        except HTTPException:
            raise

        # Log the incoming request
        log_analysis_request(
            owner=request.pr.owner,
            repo=request.pr.repo,
            pr_number=request.pr.number,
            mode=mode,
            head_sha=request.pr.head_sha,
            base_branch=request.pr.base_ref,
            files_count=len(request.files_changed),
        )

        # Process analysis with timing
        start_time = time.monotonic()
        try:
            result = get_graph().invoke(request, mode)
            latency_ms = round((time.monotonic() - start_time) * 1000, 2)

            # Log successful response
            log_analysis_response(
                owner=request.pr.owner,
                repo=request.pr.repo,
                pr_number=request.pr.number,
                mode=mode,
                latency_ms=latency_ms,
                status="success",
            )

            return result
        except Exception as exc:
            latency_ms = round((time.monotonic() - start_time) * 1000, 2)

            # Log error response
            log_analysis_response(
                owner=request.pr.owner,
                repo=request.pr.repo,
                pr_number=request.pr.number,
                mode=mode,
                latency_ms=latency_ms,
                status="error",
            )

            # Return generic error to client (don't expose internal details)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Analysis service error",
            ) from exc

    return app


def main() -> None:
    uvicorn.run("pr_validation_agent.langgraph_service.app:create_app", factory=True)


if __name__ == "__main__":
    main()
