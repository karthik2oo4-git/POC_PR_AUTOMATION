# Code Flow: LLM & LangGraph Integration

## Where LLM Analysis Happens

```
GitHub Action Triggers
        ↓
src/pr_validation_agent/ci/runner.py:validate()
        ├─ Detects changed functions (detection/)
        ├─ Runs tests (runner.py)
        └─ Calls LangGraphClient
              ↓
src/pr_validation_agent/langgraph_client.py
        ├─ Sends AnalysisRequest
        └─ Makes HTTP POST /v1/analyze/{mode}
              ↓
src/pr_validation_agent/langgraph_service/app.py
        └─ @app.post("/v1/analyze/{mode}")
              ↓
src/pr_validation_agent/langgraph_service/graph.py:AnalysisGraph
        ├─ Routes to appropriate node (failure/coverage/summary)
        └─ Each node calls LLM
              ↓
src/pr_validation_agent/langgraph_service/llm.py:build_chat_model()
        ├─ Creates LLM (openai:gpt-4-mini by default)
        └─ Sends request to LLM API
              ↓
src/pr_validation_agent/langgraph_service/prompts.py
        ├─ FAILURE_SYSTEM_PROMPT
        ├─ COVERAGE_SYSTEM_PROMPT
        └─ SUMMARY_SYSTEM_PROMPT
              ↓
LLM Response (Structured JSON)
        ↓
src/pr_validation_agent/comments.py
        ├─ Formats to GitHub comment
        └─ Returns formatted string
              ↓
src/pr_validation_agent/github.py
        └─ Posts comment to GitHub PR
```

---

## Key Files

### 1. **CI Runner** - Entry Point
**File:** `src/pr_validation_agent/ci/runner.py`

```python
def validate() -> int:
    # ... detection and test execution ...
    
    # Create analysis request
    request = _analysis_request(pr=pr, files=files, ...)
    
    # Initialize LLM client
    langgraph = LangGraphClient()
    
    # Get LLM analysis for failure mode
    failure_analysis = langgraph.analyze(request, mode="failure")
    
    # Get LLM analysis for coverage mode
    coverage_analysis = langgraph.analyze(request, mode="coverage")
    
    # Format results into GitHub comments
    comment = render_test_failure_comment(
        marker=config.comments.marker,
        author=pr.author,
        test_result=test_result,
        analysis=failure_analysis,  # <-- LLM RESULTS
    )
    
    # Post to GitHub
    github.upsert_comment(pr, config.comments.marker, comment)
```

### 2. **LangGraph Client** - Makes Request
**File:** `src/pr_validation_agent/langgraph_client.py`

```python
class LangGraphClient:
    def analyze(self, request: AnalysisRequest, mode: str) -> AnalysisResponse:
        # Send HTTP request to service
        response = httpx.post(
            f"{self.base_url}/v1/analyze/{mode}",
            json=request.model_dump(mode="json"),
            headers={"Authorization": f"Bearer {self.token}"},  # Auth
            timeout=90,
        )
        response.raise_for_status()
        return AnalysisResponse.model_validate(response.json())
```

### 3. **FastAPI Endpoint** - Routes Request
**File:** `src/pr_validation_agent/langgraph_service/app.py`

```python
@app.post("/v1/analyze/{mode}", response_model=AnalysisResponse)
async def analyze(
    mode: Literal["failure", "coverage", "summary"],
    request: AnalysisRequest,
    _: Annotated[None, Depends(verify_token)] = None,  # Auth verification
) -> AnalysisResponse:
    # Get LangGraph workflow
    graph = get_graph()
    
    # Run LLM analysis
    result = graph.invoke(request, mode)
    
    # Return structured response
    return result
```

### 4. **LangGraph Workflow** - Routes to LLM Nodes
**File:** `src/pr_validation_agent/langgraph_service/graph.py`

```python
class AnalysisGraph:
    def __init__(self) -> None:
        # Initialize LLM model
        self.llm = build_chat_model()
        
        # Create state machine
        graph = StateGraph(AnalysisState)
        
        # Add three analysis nodes
        graph.add_node("failure", self._failure_node)
        graph.add_node("coverage", self._coverage_node)
        graph.add_node("summary", self._summary_node)
        
        # Route based on mode
        graph.set_conditional_entry_point(self._route, {
            "failure": "failure",
            "coverage": "coverage",
            "summary": "summary",
        })
        
        # All paths lead to END
        graph.add_edge("failure", END)
        graph.add_edge("coverage", END)
        graph.add_edge("summary", END)
        
        self.compiled = graph.compile()
    
    def _route(self, state: AnalysisState) -> str:
        return state["mode"]  # Route to appropriate node
```

### 5. **LLM Node** - Calls LLM
**File:** `src/pr_validation_agent/langgraph_service/graph.py`

```python
def _failure_node(self, state: AnalysisState) -> dict:
    request = state["request"]
    try:
        # Configure LLM for structured output
        structured = self.llm.with_structured_output(FailureAnalysis)
        
        # Call LLM with system prompt + request
        response = structured.invoke([
            SystemMessage(content=FAILURE_SYSTEM_PROMPT),  # System prompt
            HumanMessage(content=_json_block(request)),    # User request
        ])
        
        # Validate response matches schema
        failure = FailureAnalysis.model_validate(response)
    except Exception:
        # Fallback if LLM fails
        failure = _fallback_failure(request)
    
    return {"response": AnalysisResponse(failure_analysis=failure)}
```

Similar for `_coverage_node()` and `_summary_node()`.

### 6. **LLM Model** - Configuration
**File:** `src/pr_validation_agent/langgraph_service/llm.py`

```python
def build_chat_model():
    # Get model from env (default: gpt-4-mini)
    model = os.getenv("PR_VALIDATION_MODEL", "openai:gpt-4-mini")
    
    # Get temperature from env (default: 0)
    temperature = float(os.getenv("PR_VALIDATION_TEMPERATURE", "0"))
    
    # Initialize chat model using LangChain
    return init_chat_model(model, temperature=temperature)
```

### 7. **System Prompts** - Guide LLM
**File:** `src/pr_validation_agent/langgraph_service/prompts.py`

```python
FAILURE_SYSTEM_PROMPT = """You analyze CI test logs for pull requests.
Return concise, actionable JSON. Identify failing tests, likely root cause, and a practical fix.
Do not decide whether the PR can merge."""

COVERAGE_SYSTEM_PROMPT = """You review whether newly added functions have meaningful tests.
Return concise JSON with missing tests and suggested test cases.
Do not run tests or make merge decisions."""

SUMMARY_SYSTEM_PROMPT = """You summarize pull request diffs for human reviewers.
Return concise JSON with a high-level summary, risks, and notes.
Do not approve the PR or make merge decisions."""
```

### 8. **Comment Formatter** - Renders Results
**File:** `src/pr_validation_agent/comments.py`

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
    return f"""@{author} ❌ Test failures detected

Failed Tests:
{format_tests(failed_tests)}

🤖 Analysis:
{root_cause}

💡 Suggested Fix:
{suggested_fix}
"""
```

### 9. **Models** - Data Structures
**File:** `src/pr_validation_agent/models.py`

```python
# Request sent to LLM service
class AnalysisRequest(BaseModel):
    pr: PullRequestContext
    files_changed: list[str]
    new_functions: list[FunctionSymbol]
    modified_functions: list[FunctionSymbol]
    test_result: TestRunResult | None
    coverage_findings: list[TestCoverageFinding]
    diff_excerpt: str
    log_excerpt: str

# Response from LLM service
class AnalysisResponse(BaseModel):
    failure_analysis: FailureAnalysis | None      # From LLM
    coverage_analysis: CoverageAnalysis | None    # From LLM
    summary: SummaryAnalysis | None               # From LLM

# Structured LLM outputs
class FailureAnalysis(BaseModel):
    failing_tests: list[str]
    root_cause: str
    suggested_fix: str

class CoverageAnalysis(BaseModel):
    missing_tests: list[TestCoverageFinding]
    notes: str

class SummaryAnalysis(BaseModel):
    high_level_summary: str
    risk_insights: list[str]
    notes: list[str]
```

---

## Data Flow Sequence

```python
# 1. CI Runner prepares request
request = AnalysisRequest(
    pr=pr_context,
    files_changed=[...],
    new_functions=[...],
    test_result=test_output,
    ...
)

# 2. Client sends to service (with auth)
response = LangGraphClient().analyze(request, mode="failure")
# POST /v1/analyze/failure
# Authorization: Bearer token

# 3. Service receives and routes
@app.post("/v1/analyze/failure")
def analyze(request: AnalysisRequest) -> AnalysisResponse:
    result = graph.invoke(request, mode="failure")
    return result

# 4. LangGraph invokes failure node
def _failure_node(state):
    response = self.llm.with_structured_output(FailureAnalysis).invoke([
        SystemMessage(content="You analyze CI test logs..."),
        HumanMessage(content=json.dumps(request.model_dump()))
    ])
    failure = FailureAnalysis.model_validate(response)
    return {"response": AnalysisResponse(failure_analysis=failure)}

# 5. LLM generates structured JSON response
# {
#   "failing_tests": ["test_add"],
#   "root_cause": "The add() function was modified...",
#   "suggested_fix": "Either revert or update test..."
# }

# 6. Service returns to client
return AnalysisResponse(failure_analysis=FailureAnalysis(...))

# 7. CI formats comment
comment = render_test_failure_comment(
    marker="...",
    author=pr.author,
    test_result=test_result,
    analysis=response  # <-- LLM OUTPUT HERE
)

# 8. Post to GitHub
github.upsert_comment(pr, marker, comment)
```

---

## File Dependencies

```
ci/runner.py (CI entry point)
    ├─ langgraph_client.py (HTTP client)
    │   └─ models.py (AnalysisRequest/Response)
    │
    └─ comments.py (GitHub comment formatter)
        └─ models.py (LLM outputs: FailureAnalysis, etc.)

langgraph_service/
    ├─ app.py (FastAPI endpoint)
    │   ├─ auth.py (Token validation)
    │   ├─ graph.py (LangGraph workflow)
    │   │   ├─ llm.py (LLM initialization)
    │   │   ├─ prompts.py (System prompts)
    │   │   └─ models.py (Data structures)
    │   │
    │   ├─ service_protections.py (Rate limit, etc.)
    │   └─ logging_config.py (Structured logging)
    │
    └─ models.py (AnalysisRequest/Response)
```

---

## Environment Variables

```bash
# LLM Configuration
PR_VALIDATION_MODEL="openai:gpt-4-mini"  # Model to use
PR_VALIDATION_TEMPERATURE="0"             # LLM temperature
OPENAI_API_KEY="sk-..."                  # API key for OpenAI
ANTHROPIC_API_KEY="sk-ant-..."          # API key for Claude

# Service URLs (CI side)
LANGGRAPH_SERVICE_URL="http://localhost:8000"
LANGGRAPH_SERVICE_TOKEN="..."

# Logging
LOG_LEVEL="INFO"
```

---

## How to Run End-to-End

### 1. Start LLM Service

```bash
export PR_VALIDATION_MODEL="openai:gpt-4-mini"
export OPENAI_API_KEY="sk-..."
export LANGGRAPH_SERVICE_TOKEN="test-token"
python -m pr_validation_agent.langgraph_service.app
# Service listens on http://localhost:8000
```

### 2. Run CI Validation

```bash
export LANGGRAPH_SERVICE_URL="http://localhost:8000"
export LANGGRAPH_SERVICE_TOKEN="test-token"
export GITHUB_EVENT_PATH="path/to/github/event.json"
python -m pr_validation_agent.ci.runner
# Posts comments to GitHub PR
```

### 3. See Results

- Check GitHub PR for comments with LLM analysis
- Comments include: failed tests, root cause, suggestions, missing tests, risk assessment

---

## Summary

✅ **LLM Integration Points:**
1. `langgraph_client.py` - Sends request to service
2. `langgraph_service/graph.py` - Routes to LLM node
3. `langgraph_service/llm.py` - Initializes LLM model
4. `langgraph_service/prompts.py` - Guides LLM behavior
5. `models.py` - Validates LLM output structure

✅ **LangGraph Workflow:**
- StateGraph with 3 nodes (failure/coverage/summary)
- Conditional routing based on mode
- Each node calls LLM with appropriate prompt
- Structured output validation

✅ **Result Flow:**
- LLM generates JSON
- Formatted into GitHub comments
- Posted to PR

**This is a complete AI-powered PR review system!**
