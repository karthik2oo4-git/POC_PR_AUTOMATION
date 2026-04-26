# LLM & LangGraph: Step-by-Step Example

## Real-World Scenario

A developer opens a PR that modifies test coverage and some tests fail. Here's what happens:

---

## Step 1-4: Setup and Detection

GitHub Action triggers → Code analysis detects:
- `src/math.py`: Added `multiply()`, modified `add()`
- `tests/test_math.py`: No test for `multiply()`
- Test run fails: `test_add` assertion error

---

## Step 5: Create Analysis Request

```python
request = AnalysisRequest(
    pr=PullRequestContext(owner="acme", repo="compute-lib", number=123, ...),
    files_changed=["src/math.py", "tests/test_math.py"],
    new_functions=[FunctionSymbol(name="multiply", ...)],
    modified_functions=[FunctionSymbol(name="add", ...)],
    test_result=TestRunResult(
        exit_code=1,
        passed=False,
        stdout="FAILED tests/test_math.py::test_add - AssertionError: assert 3 == 4",
    ),
    coverage_findings=[
        TestCoverageFinding(symbol=multiply, has_test=False, ...),
        TestCoverageFinding(symbol=add, has_test=True, ...),
    ],
)
```

---

## Step 6: Send to Service

```python
client = LangGraphClient()
failure_response = client.analyze(request, mode="failure")
```

**HTTP:**
```
POST /v1/analyze/failure HTTP/1.1
Authorization: Bearer token
Content-Type: application/json

{ pr, files_changed, test_result, ... }
```

---

## Step 7: Service Routes Request

```python
@app.post("/v1/analyze/{mode}")
def analyze(mode: str, request: AnalysisRequest):
    graph = get_graph()  # LangGraph with LLM
    result = graph.invoke(request, mode="failure")
    return result
```

**LangGraph Routes:**
```
mode="failure" ──> _failure_node ──> LLM ──> FailureAnalysis
```

---

## Step 8: LLM Processes Request

```python
def _failure_node(self, state: AnalysisState):
    request = state["request"]
    
    # Initialize LLM (gpt-4-mini via OpenAI)
    structured = self.llm.with_structured_output(FailureAnalysis)
    
    # Send request to LLM
    response = structured.invoke([
        SystemMessage(content="""You analyze CI test logs for pull requests.
        Return JSON: failing_tests, root_cause, suggested_fix."""),
        HumanMessage(content=json.dumps(request.model_dump(), indent=2))
    ])
    
    # Parse structured output
    failure = FailureAnalysis.model_validate(response)
    
    return {"response": AnalysisResponse(failure_analysis=failure)}
```

---

## Step 9: LLM Analysis

**LLM Input:**
```
System Prompt:
  You analyze CI test logs for pull requests.
  Return concise, actionable JSON. Identify failing tests, likely root cause, and a practical fix.

Request Data:
  - test_result.stdout: "FAILED tests/test_math.py::test_add - AssertionError: assert 3 == 4"
  - modified_functions: [add() at lines 1-5]
  - log_excerpt: "FAILED tests/test_math.py::test_add - AssertionError: assert 3 == 4"
  - diff shows: "def add(a, b): return a + b + 1" (was "return a + b")
```

**LLM Output (Structured):**
```json
{
  "failing_tests": ["tests/test_math.py::test_add"],
  "root_cause": "The add() function was modified to return a + b + 1 instead of a + b. The test expects 1 + 2 = 3 but now gets 4.",
  "suggested_fix": "Either revert add() to the original implementation (return a + b) or update the test to expect the new behavior (assertEqual(add(1, 2), 4))."
}
```

---

## Step 10: Service Returns Response

```python
{
  "failure_analysis": {
    "failing_tests": ["tests/test_math.py::test_add"],
    "root_cause": "The add() function was modified...",
    "suggested_fix": "Either revert add() or update the test..."
  }
}
```

---

## Step 11: CI Formats GitHub Comment

```python
# ci/runner.py
comment = render_test_failure_comment(
    marker="<!-- pr-validation -->",
    author="alice",
    test_result=test_result,
    analysis=failure_response,  # <-- LLM ANALYSIS
)
```

**Generated Comment:**
```
<!-- pr-validation -->
@alice ❌ Test failures detected

Failed Tests:
- `tests/test_math.py::test_add`

🤖 Analysis:
The add() function was modified to return a + b + 1 instead of a + b. 
The test expects 1 + 2 = 3 but now gets 4.

💡 Suggested Fix:
Either revert add() to the original implementation (return a + b) or update the test to expect the new behavior (assertEqual(add(1, 2), 4)).

Command: `pytest`
Exit code: `1`
```

---

## Step 12: Post to PR

```python
github.upsert_comment(pr, marker, comment)
```

**Result on GitHub:**
The PR now has a comment with AI-powered analysis of the test failure, including:
- ✅ Which tests failed
- ✅ Why they failed (LLM analysis)
- ✅ How to fix it (LLM suggestion)

---

## Coverage Analysis Example

Same process, but with `mode="coverage"`:

```python
coverage_response = client.analyze(request, mode="coverage")
```

**LLM Node:**
```
_coverage_node(state) ──> LLM with COVERAGE_SYSTEM_PROMPT
```

**LLM Analysis:**
```json
{
  "missing_tests": [
    {
      "symbol": {"name": "multiply", "file_path": "src/math.py", ...},
      "has_test": false,
      "suggested_tests": ["test_multiply_positive", "test_multiply_negative", "test_multiply_zero"]
    }
  ],
  "notes": "New multiply() function has no test coverage. Add at least basic positive/negative/edge case tests."
}
```

**Generated Comment:**
```
@alice ❌ Missing unit tests for new functions

Newly added functions:
- `multiply` in `src/math.py:7`

💡 Suggested Test Cases:
- `multiply`: test_multiply_positive; test_multiply_negative; test_multiply_zero

Add tests that exercise the new public behavior.
```

---

## Summary Analysis Example

`mode="summary"` analyzes overall PR quality:

```python
summary_response = client.analyze(request, mode="summary")
```

**LLM Node:**
```
_summary_node(state) ──> LLM with SUMMARY_SYSTEM_PROMPT
```

**LLM Analysis:**
```json
{
  "high_level_summary": "PR adds a new multiply() function and fixes a bug in add(). Adds 2 files with 1 new function and 1 modified function.",
  "risk_insights": [
    "Modified add() changes behavior which could be a breaking change for existing code",
    "multiply() lacks test coverage"
  ],
  "notes": [
    "Check if add() change is intentional",
    "Add tests for multiply()"
  ]
}
```

**Generated Comment:**
```
✅ All checks passed. Ready for review.

📌 Changes in this PR:

Files Modified:
- `src/math.py`
- `tests/test_math.py`

➕ New Functions:
- `multiply` in `src/math.py:7`

➖ Modified Functions:
- `add` in `src/math.py:1`

🤖 Summary Analysis:
PR adds a new multiply() function and fixes a bug in add(). 
Adds 2 files with 1 new function and 1 modified function.

⚠️ Risk Insights:
- Modified add() changes behavior which could be a breaking change
- multiply() lacks test coverage

📝 Notes:
- Check if add() change is intentional
- Add tests for multiply()
```

---

## LLM Configuration

To use different models:

```bash
# OpenAI
PR_VALIDATION_MODEL="openai:gpt-4-mini"
OPENAI_API_KEY="sk-..."

# Or Claude
PR_VALIDATION_MODEL="anthropic:claude-3-sonnet"
ANTHROPIC_API_KEY="sk-ant-..."

# Or any LangChain supported model
PR_VALIDATION_TEMPERATURE="0"  # Deterministic
```

---

## Key Points

✅ **LLM analyzes in 3 modes:**
- `failure`: Why tests failed
- `coverage`: Which functions lack tests
- `summary`: Overall PR quality assessment

✅ **Structured outputs:**
- LLM response validated against Pydantic schemas
- Fallbacks if LLM fails

✅ **Service architecture:**
- LangGraph routes to appropriate LLM node
- HTTP API with auth + rate limiting
- Comments format results into GitHub-friendly text

✅ **End-to-end:**
- GitHub Action triggers
- CI detects changes
- Service calls LLM
- Comments posted with AI insights
