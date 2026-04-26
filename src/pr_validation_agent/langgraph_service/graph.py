from __future__ import annotations

import json
from typing import Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from pr_validation_agent.langgraph_service.llm import build_chat_model
from pr_validation_agent.langgraph_service.prompts import (
    COVERAGE_SYSTEM_PROMPT,
    FAILURE_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
)
from pr_validation_agent.models import (
    AnalysisRequest,
    AnalysisResponse,
    CoverageAnalysis,
    FailureAnalysis,
    SummaryAnalysis,
)


class AnalysisState(TypedDict, total=False):
    mode: Literal["failure", "coverage", "summary"]
    request: AnalysisRequest
    response: AnalysisResponse


def _json_block(payload: object) -> str:
    if hasattr(payload, "model_dump"):
        return json.dumps(payload.model_dump(mode="json"), indent=2)
    return json.dumps(payload, indent=2)


def _fallback_failure(request: AnalysisRequest) -> FailureAnalysis:
    lines = [line for line in request.log_excerpt.splitlines() if line.strip()]
    failing = [
        line.strip()
        for line in lines
        if "FAILED" in line or "ERROR" in line or "AssertionError" in line
    ][:10]
    return FailureAnalysis(
        failing_tests=failing,
        root_cause="The configured test command exited with a non-zero status. Review the listed failures and CI log excerpt.",
        suggested_fix="Reproduce the failing command locally, fix the failing behavior, and push an update.",
    )


def _fallback_coverage(request: AnalysisRequest) -> CoverageAnalysis:
    missing = [finding for finding in request.coverage_findings if not finding.has_test]
    return CoverageAnalysis(missing_tests=missing, notes="No LLM coverage analysis was available.")


def _fallback_summary(request: AnalysisRequest) -> SummaryAnalysis:
    return SummaryAnalysis(
        high_level_summary=(
            f"This PR changes {len(request.files_changed)} file(s), adds "
            f"{len(request.new_functions)} function(s), and modifies "
            f"{len(request.modified_functions)} function(s)."
        ),
        risk_insights=[],
        notes=[],
    )


class AnalysisGraph:
    def __init__(self) -> None:
        self.llm = build_chat_model()
        graph = StateGraph(AnalysisState)
        graph.add_node("failure", self._failure_node)
        graph.add_node("coverage", self._coverage_node)
        graph.add_node("summary", self._summary_node)
        graph.set_conditional_entry_point(self._route, {
            "failure": "failure",
            "coverage": "coverage",
            "summary": "summary",
        })
        graph.add_edge("failure", END)
        graph.add_edge("coverage", END)
        graph.add_edge("summary", END)
        self.compiled = graph.compile()

    def invoke(self, request: AnalysisRequest, mode: str) -> AnalysisResponse:
        result = self.compiled.invoke({"request": request, "mode": mode})
        return result["response"]

    def _route(self, state: AnalysisState) -> str:
        return state["mode"]

    def _failure_node(self, state: AnalysisState) -> dict:
        request = state["request"]
        try:
            structured = self.llm.with_structured_output(FailureAnalysis)
            response = structured.invoke(
                [
                    SystemMessage(content=FAILURE_SYSTEM_PROMPT),
                    HumanMessage(content=_json_block(request)),
                ]
            )
            failure = FailureAnalysis.model_validate(response)
        except Exception:
            failure = _fallback_failure(request)
        return {"response": AnalysisResponse(failure_analysis=failure)}

    def _coverage_node(self, state: AnalysisState) -> dict:
        request = state["request"]
        try:
            structured = self.llm.with_structured_output(CoverageAnalysis)
            response = structured.invoke(
                [
                    SystemMessage(content=COVERAGE_SYSTEM_PROMPT),
                    HumanMessage(content=_json_block(request)),
                ]
            )
            coverage = CoverageAnalysis.model_validate(response)
        except Exception:
            coverage = _fallback_coverage(request)
        return {"response": AnalysisResponse(coverage_analysis=coverage)}

    def _summary_node(self, state: AnalysisState) -> dict:
        request = state["request"]
        try:
            structured = self.llm.with_structured_output(SummaryAnalysis)
            response = structured.invoke(
                [
                    SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
                    HumanMessage(content=_json_block(request)),
                ]
            )
            summary = SummaryAnalysis.model_validate(response)
        except Exception:
            summary = _fallback_summary(request)
        return {"response": AnalysisResponse(summary=summary)}
