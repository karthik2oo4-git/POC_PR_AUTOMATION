# LLM & LangGraph Integration Architecture

## Overview

The system uses LangGraph workflows to analyze PR changes with Claude LLM, then formats the results into GitHub comments.

### Data Flow Diagram

```
CI Environment (GitHub Actions)
│
├─ Detect function changes (git_diff.py)
├─ Run tests (runner.py)
├─ Analyze coverage (test_matcher.py)
│
└─> Create AnalysisRequest
    │
    └─> LangGraphClient
        │
        └─> HTTP POST /v1/analyze/{mode}
            │
            ├─> LangGraph Service
            │   │
            │   ├─ Route to mode (failure/coverage/summary)
            │   │
            │   ├─ Failure Node:
            │   │  └─> LLM + FailureAnalysis schema
            │   │      └─> Analyze failing tests
            │   │
            │   ├─ Coverage Node:
            │   │  └─> LLM + CoverageAnalysis schema
            │   │      └─> Analyze missing tests
            │   │
            │   └─ Summary Node:
            │      └─> LLM + SummaryAnalysis schema
            │          └─> Analyze PR risk/changes
            │
            └─> AnalysisResponse
                │
                └─> Format to GitHub Comment (comments.py)
                    │
                    └─> Post to PR
```

---

## LLM Implementation

### 1. LLM Model Setup

**File:** `langgraph_service/llm.py`

```python
def build_chat_model():
    model = os.getenv("PR_VALIDATION_MODEL", "openai:gpt-4-mini")
    temperature = float(os.getenv("PR_VALIDATION_TEMPERATURE", "0"))
    return init_chat_model(model, temperature=temperature)
```

**Environment variables:**
```bash
PR_VALIDATION_MODEL="openai:gpt-4-mini"  # or gpt-4, claude-3-opus, etc.
PR_VALIDATION_TEMPERATURE="0"             # 0 = deterministic, 1 = creative
OPENAI_API_KEY="sk-..."                   # For OpenAI models
```

### 2. LangGraph Workflow

**File:** `langgraph_service/graph.py`

The `AnalysisGraph` class implements a 3-mode workflow:

```python
class AnalysisGraph:
    def __init__(self):
        # Initialize LLM
        self.llm = build_chat_model()
        
        # Create LangGraph state machine
        graph = StateGraph(AnalysisState)
        
        # Add 3 analysis nodes
        graph.add_node("failure", self._failure_node)
        graph.add_node("coverage", self._coverage_node)
        graph.add_node("summary", self._summary_node)
        
        # Route based on mode
        graph.set_conditional_entry_point(self._route, {
            "failure": "failure",
            "coverage": "coverage",
            "summary": "summary",
        })
        
        # All nodes connect to END
        graph.add_edge("failure", END)
        graph.add_edge("coverage", END)
        graph.add_edge("summary", END)
        
        self.compiled = graph.compile()
```

### 3. Analysis Nodes

#### Failure Analysis Node
```python
def _failure_node(self, state: AnalysisState) -> dict:
    request = state["request"]
    try:
        # Use LLM with structured output (FailureAnalysis schema)
        structured = self.llm.with_structured_output(FailureAnalysis)
        response = structured.invoke([
            SystemMessage(content=FAILURE_SYSTEM_PROMPT),
            HumanMessage(content=_json_block(request)),
        ])
        failure = FailureAnalysis.model_validate(response)
    except Exception:
        # Fallback if LLM fails
        failure = _fallback_failure(request)
    return {"response": AnalysisResponse(failure_analysis=failure)}
```

**What it does:**
- Analyzes test failure logs
- Identifies failing tests
- Suggests root cause
- Recommends fix

**System Prompt:** `FAILURE_SYSTEM_PROMPT` (see prompts.py)

#### Coverage Analysis Node
```python
def _coverage_node(self, state: AnalysisState) -> dict:
    request = state["request"]
    try:
        structured = self.llm.with_structured_output(CoverageAnalysis)
        response = structured.invoke([
            SystemMessage(content=COVERAGE_SYSTEM_PROMPT),
            HumanMessage(content=_json_block(request)),
        ])
        coverage = CoverageAnalysis.model_validate(response)
    except Exception:
        coverage = _fallback_coverage(request)
    return {"response": AnalysisResponse(coverage_analysis=coverage)}
```

**What it does:**
- Analyzes newly added functions
- Identifies functions without tests
- Suggests test cases

#### Summary Analysis Node
```python
def _summary_node(self, state: AnalysisState) -> dict:
    request = state["request"]
    try:
        structured = self.llm.with_structured_output(SummaryAnalysis)
        response = structured.invoke([
            SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
            HumanMessage(content=_json_block(request)),
        ])
        summary = SummaryAnalysis.model_validate(response)
    except Exception:
        summary = _fallback_summary(request)
    return {"response": AnalysisResponse(summary=summary)}
```

**What it does:**
- High-level PR summary
- Risk insights
- Change assessment notes

---

## System Prompts

**File:** `langgraph_service/prompts.py`

Three system prompts guide LLM analysis:

### FAILURE_SYSTEM_PROMPT
```
You are an expert code review assistant analyzing test failures.
Given a PR with test failure logs, analyze:
1. Which tests are failing
2. Root cause of failures (code logic, setup issues, etc.)
3. Specific fix recommendations

Respond with structured data: failing_tests, root_cause, suggested_fix
```

### COVERAGE_SYSTEM_PROMPT
```
You are a test coverage expert reviewing new code.
Given newly added/modified functions, identify:
1. Which functions lack test coverage
2. Evidence of test coverage
3. Specific test cases to write

Respond with structured data: missing_tests with evidence and suggestions
```

### SUMMARY_SYSTEM_PROMPT
```
You are a senior engineer assessing PR quality and risk.
Given a complete PR, provide:
1. High-level summary of changes
2. Risk insights (security, performance, breaking changes)
3. Additional notes

Respond with structured data: high_level_summary, risk_insights, notes
```

---

## How Comments Are Generated

**File:** `comments.py`

The comment rendering functions take LLM analysis and format it as GitHub comments:

### Test Failure Comment
```python
def render_test_failure_comment(
    marker: str,
    author: str,
    test_result: TestRunResult,
    analysis: AnalysisResponse | None,  # <-- LLM ANALYSIS
) -> str:
    # Extract LLM analysis
    failure = analysis.failure_analysis if analysis else None
    failed_tests = failure.failing_tests if failure else []
    root_cause = failure.root_cause if failure else "Unable to infer root cause."
    suggested_fix = failure.suggested_fix if failure else "..."
    
    # Format as GitHub comment
    return f"""
@{author} ❌ Test failures detected

Failed Tests:
{format_tests(failed_tests)}

🤖 Analysis:  # <-- LLM OUTPUT
{root_cause}

💡 Suggested Fix:  # <-- LLM OUTPUT
{suggested_fix}
...
"""
```

### Missing Tests Comment
```python
def render_missing_tests_comment(
    marker: str,
    author: str,
    findings: list[TestCoverageFinding],
    analysis: AnalysisResponse | None,  # <-- LLM ANALYSIS
) -> str:
    # Extract LLM analysis
    coverage_analysis = analysis.coverage_analysis if analysis else None
    analyzed_findings = coverage_analysis.missing_tests if coverage_analysis else findings
    notes = coverage_analysis.notes if coverage_analysis else ""
    
    # Format as GitHub comment
    return f"""
@{author} ❌ Missing unit tests for new functions

Newly added functions:
{format_findings(analyzed_findings)}

💡 Suggested Test Cases:  # <-- LLM SUGGESTIONS
{format_suggestions(analyzed_findings)}

{notes}  # <-- LLM NOTES
"""
```

### Success Comment
```python
def render_success_comment(
    marker: str,
    files_changed: list[str],
    new_functions: list[FunctionSymbol],
    modified_functions: list[FunctionSymbol],
    analysis: AnalysisResponse | None,  # <-- LLM ANALYSIS
) -> str:
    # Extract LLM analysis
    summary = analysis.summary if analysis else None
    high_level_summary = summary.high_level_summary if summary else "..."  # <-- LLM
    risk_insights = summary.risk_insights if summary else []  # <-- LLM
    
    # Format as GitHub comment
    return f"""
✅ All checks passed. Ready for review.

📌 Changes in this PR:
...

🤖 Summary Analysis:  # <-- LLM OUTPUT
{high_level_summary}

⚠️ Risk Insights:  # <-- LLM INSIGHTS
{format_risks(risk_insights)}
...
"""
```

---

## Complete Request-Response Flow

### 1. CI Runner Prepares Analysis Request

```python
# ci/runner.py - validate()
request = _analysis_request(
    pr=pr,
    files=changed_files,
    new_functions=newly_detected_functions,
    modified_functions=modified_functions,
    test_result=test_run_result,
    coverage_findings=coverage_analysis,
    diff_excerpt=diff_text,
)
```

### 2. Client Sends to Service

```python
# langgraph_client.py
client = LangGraphClient()
analysis_response = client.analyze(request, mode="failure")
# POST /v1/analyze/failure with Authorization header
```

### 3. Service Processes with LLM

```python
# langgraph_service/app.py
@app.post("/v1/analyze/{mode}")
async def analyze(
    mode: Literal["failure", "coverage", "summary"],
    request: AnalysisRequest,
    _: Annotated[None, Depends(verify_token)] = None,  # Auth
) -> AnalysisResponse:
    # Get LangGraph workflow
    graph = get_graph()
    
    # Run LLM analysis
    result = graph.invoke(request, mode)
    
    # Return structured result
    return result
```

### 4. CI Formats Results

```python
# ci/runner.py - validate()
if analysis_response.failure_analysis:
    comment = render_test_failure_comment(
        marker=config.comments.marker,
        author=pr.author,
        test_result=test_result,
        analysis=analysis_response,  # <-- LLM RESULTS
    )
    github.upsert_comment(pr, config.comments.marker, comment)
```

---

## Data Models

### AnalysisRequest
```python
class AnalysisRequest(BaseModel):
    pr: PullRequestContext              # GitHub PR info
    files_changed: list[str]            # Modified files
    new_functions: list[FunctionSymbol] # Newly added functions
    modified_functions: list[FunctionSymbol]  # Modified functions
    test_result: TestRunResult | None   # Test run output
    coverage_findings: list[TestCoverageFinding]  # Coverage analysis
    diff_excerpt: str                   # Git diff
    log_excerpt: str                    # Test output log
```

### AnalysisResponse
```python
class AnalysisResponse(BaseModel):
    failure_analysis: FailureAnalysis | None      # LLM failure analysis
    coverage_analysis: CoverageAnalysis | None    # LLM coverage analysis
    summary_analysis: SummaryAnalysis | None      # LLM summary analysis
```

### LLM Structured Outputs

```python
class FailureAnalysis(BaseModel):
    failing_tests: list[str]     # Extracted from logs
    root_cause: str              # LLM analysis
    suggested_fix: str           # LLM recommendation

class CoverageAnalysis(BaseModel):
    missing_tests: list[TestCoverageFinding]  # Identified untested functions
    notes: str                                # LLM notes

class SummaryAnalysis(BaseModel):
    high_level_summary: str       # LLM summary
    risk_insights: list[str]      # LLM risk assessment
    notes: list[str]              # LLM additional notes
```

---

## Fallback Handling

If LLM call fails, fallback functions provide basic analysis:

```python
def _fallback_failure(request: AnalysisRequest) -> FailureAnalysis:
    # Parse test output for failing test names
    lines = [line for line in request.log_excerpt.splitlines() if line.strip()]
    failing = [line.strip() for line in lines if "FAILED" in line][:10]
    return FailureAnalysis(
        failing_tests=failing,
        root_cause="Unable to run LLM analysis. Review logs manually.",
        suggested_fix="Reproduce locally and fix.",
    )

def _fallback_coverage(request: AnalysisRequest) -> CoverageAnalysis:
    missing = [f for f in request.coverage_findings if not f.has_test]
    return CoverageAnalysis(
        missing_tests=missing,
        notes="No LLM analysis available.",
    )

def _fallback_summary(request: AnalysisRequest) -> SummaryAnalysis:
    return SummaryAnalysis(
        high_level_summary=f"PR changes {len(request.files_changed)} files...",
        risk_insights=[],
        notes=[],
    )
```

---

## Testing the LLM Integration

### 1. Check LLM Model is Configured

```bash
echo $PR_VALIDATION_MODEL
echo $OPENAI_API_KEY
```

### 2. Start Service with LLM

```bash
export PR_VALIDATION_MODEL="openai:gpt-4-mini"
export OPENAI_API_KEY="sk-..."
python -m pr_validation_agent.langgraph_service.app
```

### 3. Test LLM Analysis

```bash
curl -X POST http://localhost:8000/v1/analyze/failure \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "pr": {...},
    "files_changed": ["test.py"],
    "test_result": {
      "command": "pytest",
      "exit_code": 1,
      "passed": false,
      "duration_seconds": 5.2,
      "stdout": "FAILED test_main.py::test_add - AssertionError: assert 3 == 4",
      "stderr": ""
    },
    "log_excerpt": "FAILED test_main.py::test_add - AssertionError: assert 3 == 4"
  }'
```

Response will include:
```json
{
  "failure_analysis": {
    "failing_tests": ["test_main.py::test_add"],
    "root_cause": "The test_add function expects 1+2=4 but got 3...",
    "suggested_fix": "Fix the add function to return 3, or update the test expectation..."
  }
}
```

### 4. Check GitHub Comment Output

The comment will include LLM analysis:
```
❌ Test failures detected

Failed Tests:
- test_main.py::test_add

🤖 Analysis:
The test_add function expects 1+2=4 but got 3. The add implementation is incorrect.

💡 Suggested Fix:
Fix the add function to properly sum the inputs.
```

---

## Environment Variables Summary

### LLM Configuration
```bash
PR_VALIDATION_MODEL="openai:gpt-4-mini"  # Model to use
PR_VALIDATION_TEMPERATURE="0"             # LLM temperature (0-1)
OPENAI_API_KEY="sk-..."                  # For OpenAI
ANTHROPIC_API_KEY="sk-ant-..."          # For Claude
```

### Service Configuration
```bash
LANGGRAPH_SERVICE_URL="http://localhost:8000"     # Service URL
LANGGRAPH_SERVICE_TOKEN="..."                     # Auth token
```

### Logger Configuration
```bash
LOG_LEVEL="INFO"  # Logging verbosity
```

---

## Architecture Summary

- **LLM Models:** Configured via `PR_VALIDATION_MODEL` env var
- **LangGraph Workflow:** 3-node state machine (failure/coverage/summary) in `graph.py`
- **System Prompts:** Guide LLM analysis in `prompts.py`
- **Service:** FastAPI endpoint exposes `/v1/analyze/{mode}` 
- **Client:** CI runner sends `AnalysisRequest`, receives `AnalysisResponse`
- **Comments:** Formatter takes LLM output and creates GitHub comments
- **Fallbacks:** Basic analysis if LLM fails

**Result:** Automated AI-powered PR review comments on GitHub!
