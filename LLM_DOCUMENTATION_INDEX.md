# LLM & LangGraph Documentation Index

## Quick Overview

The system uses **LangGraph** workflows to analyze PRs with **Claude/GPT** LLM, then formats results into GitHub comments.

**Key Files:**
- `langgraph_service/graph.py` - LangGraph 3-node workflow
- `langgraph_service/llm.py` - LLM initialization
- `langgraph_service/prompts.py` - System prompts
- `comments.py` - Formats LLM output to GitHub comments
- `langgraph_client.py` - Sends requests from CI to service

---

## Documentation Files

### 1. **LLM_LANGGRAPH_ARCHITECTURE.md**
**What:** Complete architecture overview
- Data flow diagram
- Implementation of each analysis node
- System prompts explained
- How comments are generated
- Environment variables
- Testing guide

**When to read:** First time setup, understanding the full system

### 2. **LLM_EXAMPLE_WALKTHROUGH.md**
**What:** Real-world step-by-step example
- Example PR with failing test
- What LLM sees (request data)
- What LLM responds with (analysis)
- How GitHub comment is generated
- Multiple modes (failure, coverage, summary)

**When to read:** Want to see how it works in practice

### 3. **CODE_FLOW_LLM_INTEGRATION.md**
**What:** Technical code flow and file dependencies
- Where LLM analysis happens (file-by-file)
- Data structures (AnalysisRequest, AnalysisResponse)
- Fallback handling
- File dependencies tree
- How to run end-to-end

**When to read:** Debugging, modifying code, understanding file organization

### 4. **SECURITY_IMPLEMENTATION.md**
**What:** Security, logging, rate limiting (from earlier implementation)
- Authentication tokens
- Request validation
- Rate limiting
- Concurrency limits
- Secret redaction

**When to read:** Deploying to production

---

## Quick Start

### To understand the LLM flow:
```
LLM_EXAMPLE_WALKTHROUGH.md  ← Start here
        ↓
LLM_LANGGRAPH_ARCHITECTURE.md  ← Deep dive
        ↓
CODE_FLOW_LLM_INTEGRATION.md  ← Implementation details
```

### Key concepts:

1. **LangGraph**: State machine routing requests to LLM nodes
   - File: `langgraph_service/graph.py`
   - 3 nodes: failure, coverage, summary

2. **LLM Model**: Configurable (GPT-4-mini, Claude, etc.)
   - File: `langgraph_service/llm.py`
   - Config: `PR_VALIDATION_MODEL` env var

3. **System Prompts**: Guide LLM analysis
   - File: `langgraph_service/prompts.py`
   - 3 prompts: failure, coverage, summary analysis

4. **Comments**: Format LLM output for GitHub
   - File: `comments.py`
   - Takes LLM response, creates GitHub comment

---

## Environment Setup

```bash
# LLM Configuration
export PR_VALIDATION_MODEL="openai:gpt-4-mini"
export OPENAI_API_KEY="sk-..."
export PR_VALIDATION_TEMPERATURE="0"

# Service (if deployed)
export LANGGRAPH_SERVICE_URL="http://localhost:8000"
export LANGGRAPH_SERVICE_TOKEN="token"
```

---

## Files Modified/Created for LLM Support

**Service Files:**
- ✅ `langgraph_service/app.py` - FastAPI endpoint
- ✅ `langgraph_service/graph.py` - LangGraph workflow (3 analysis nodes)
- ✅ `langgraph_service/llm.py` - LLM initialization
- ✅ `langgraph_service/prompts.py` - System prompts

**Client Files:**
- ✅ `langgraph_client.py` - HTTP client to service
- ✅ `comments.py` - Format LLM output to GitHub comments
- ✅ `models.py` - Data structures (AnalysisRequest/Response)

---

## What the LLM Does

### Failure Analysis (`mode="failure"`)
Input: Failed test logs + code changes
Output:
- Which tests failed
- Why they failed (root cause analysis)
- How to fix them

### Coverage Analysis (`mode="coverage"`)
Input: Newly added functions + test results
Output:
- Which functions lack tests
- Suggested test cases for each function

### Summary Analysis (`mode="summary"`)
Input: Complete PR diff + all changes
Output:
- High-level summary of changes
- Risk insights (breaking changes, security, performance)
- General assessment notes

---

## Next: Deploy to Production

1. See `SECURITY_IMPLEMENTATION.md` for auth + rate limiting
2. Deploy service with LLM API keys
3. Configure GitHub Actions to call service
4. Check logs for LLM analysis

---

## Troubleshooting

**LLM not being called?**
- Check `PR_VALIDATION_MODEL` env var is set
- Check `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` is valid
- Look for errors in service logs

**Wrong analysis from LLM?**
- Modify system prompts in `prompts.py`
- Try different model: `PR_VALIDATION_MODEL="openai:gpt-4"` (more expensive, better)
- Check input data: what is the request sending to LLM?

**Comments not appearing?**
- Check GitHub API token in `github.py`
- Look for errors in CI runner logs
- Verify `comments.py` formatting is correct

---

## Files Structure

```
src/pr_validation_agent/
├─ comments.py                      # Format LLM output to comments
├─ langgraph_client.py              # HTTP client to LLM service
├─ models.py                        # Data structures
│
└─ langgraph_service/
   ├─ app.py                        # FastAPI endpoint
   ├─ auth.py                       # Token auth (security impl)
   ├─ graph.py                      # ⭐ LangGraph workflow (LLM here)
   ├─ llm.py                        # ⭐ LLM initialization
   ├─ prompts.py                    # ⭐ System prompts
   ├─ logging_config.py             # Structured logging
   └─ service_protections.py        # Rate limiting, etc.
```

⭐ = Main LLM integration points
