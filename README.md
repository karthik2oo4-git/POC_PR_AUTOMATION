# PR Validation Agent

A production-ready PR validation system for GitHub that:

- runs automatically when a pull request is opened, synchronized, reopened, or marked ready for review
- executes repository setup and unit tests in CI
- blocks merge when tests fail
- checks whether newly added functions have corresponding tests
- posts a single bot comment on the PR with failure reasons or success summary
- uses LangGraph only for analysis and suggestions, not for merge decisions
- scales from one repository to many repositories and organizations

This document is the main guide for understanding, setting up, and extending the project.

> Documentation rule: use only [`README.md`](README.md) and [`NEXT_STEPS.md`](NEXT_STEPS.md). Other legacy markdown files are no longer part of the main reading path.

## 1. Problem This Project Solves

In a normal team workflow:

1. A developer pulls the latest changes from the base branch such as `development`.
2. The developer creates a branch and works on a feature or fix.
3. The developer raises a pull request back to that base branch.
4. A reviewer needs to know whether the PR branch is still safe to merge with the latest base branch state.

This project automates that check.

Example:

- Suresh joins a company and creates a branch from `development`.
- The test suite already present in `development` is treated as the required baseline.
- Suresh makes code changes in his branch and raises a PR back to `development`.
- The PR validation agent runs automatically.
- In CI, the latest base branch is merged into Suresh's PR branch context before validation.
- The existing tests from `development` are then executed against Suresh's branch changes.
- If Suresh added a new function, he must also add matching test cases for that new function.
- The PR passes only when:
  - the baseline tests from `development` still pass on the PR branch
  - the new tests added for new functions are present and pass
- If either condition fails, the PR gets a failure status and a bot comment explains the reason.
- The reviewer only approves merge when GitHub shows the required status check as successful.

With branch protection enabled, merge stays blocked until the validation check passes.

## 2. Final Workflow

```text
PR Raised (opened / synchronize / reopened / ready_for_review)
  -> GitHub Actions workflow starts
  -> checkout PR head SHA
  -> merge latest base branch into PR branch inside CI
  -> run setup commands
  -> run configured test suite on the merged PR state

IF SETUP OR TESTS FAIL:
  -> this includes failures from tests that already existed in the base branch
  -> collect logs
  -> send request to LangGraph service in failure mode
  -> update one PR comment with root cause + suggestions
  -> mention PR author
  -> add label: test-failed
  -> set GitHub status: FAILURE
  -> merge remains blocked
  -> stop

IF TESTS PASS:
  -> detect changed/new/modified functions via AST + git diff
  -> check whether newly added functions have matching tests in the PR branch

IF TESTS ARE MISSING:
  -> this means new code was added without corresponding new tests
  -> send request to LangGraph service in coverage mode
  -> update one PR comment with suggested test cases
  -> mention PR author
  -> add label: needs-tests
  -> set GitHub status: FAILURE
  -> merge remains blocked
  -> stop

IF EVERYTHING PASSES:
  -> send request to LangGraph service in summary mode
  -> optionally run non-gating code review command
  -> update one PR comment with success summary
  -> add label: ready-for-review
  -> request reviewers if configured
  -> set GitHub status: SUCCESS
  -> optional auto-merge
```

## 3. Architecture and Responsibility Split

This split is important.

### GitHub Actions + Runner are responsible for:

- checking out code
- merging base into head in CI
- running setup commands
- running tests
- detecting new and modified functions
- checking test discipline
- applying labels
- requesting reviewers
- posting/updating PR comments
- setting GitHub commit status
- deciding pass/fail

### LangGraph service is responsible only for:

- analyzing test failure logs
- suggesting likely root cause and fixes
- suggesting missing test cases
- generating PR summaries for human reviewers

### LangGraph service must never:

- run tests
- decide merge eligibility
- orchestrate GitHub Actions
- enable or disable merge directly

That keeps CI deterministic and keeps LLM usage limited to analysis only.

## 4. Project Structure

```text
.github/workflows/pr-validation.yml       Example workflow
action.yml                                Reusable composite GitHub Action
configs/pr-validation.example.yml         Example repository config
src/pr_validation_agent/
  ci/runner.py                            Main validation flow
  config.py                               YAML config loader
  comments.py                             PR comment rendering
  github.py                               GitHub API integration
  langgraph_client.py                     Client for LangGraph service
  models.py                               Shared data models
  detection/                              AST + diff-based change detection
  langgraph_service/                      FastAPI + LangGraph service
tests/                                    Unit tests
README.md                                 Main implementation guide
NEXT_STEPS.md                             Future improvements / rollout roadmap
```

## 5. Core Files You Should Understand First

### [`.github/workflows/pr-validation.yml`](.github/workflows/pr-validation.yml)

GitHub Actions workflow that triggers on pull request events and calls the reusable action.

### [`action.yml`](action.yml)

Reusable composite action for organizations or multiple repositories.

### [`validate()`](src/pr_validation_agent/ci/runner.py:223)

Main orchestration flow:

- sets pending status
- merges base into head
- runs setup
- runs tests
- checks test coverage for new functions
- calls LangGraph service
- updates PR comment
- applies labels
- requests reviewers
- sets final success/failure status

### [`GitHubClient`](src/pr_validation_agent/github.py:19)

Handles:

- commit status updates
- PR comment upsert
- labels
- reviewer requests
- optional auto-merge

### [`AnalysisGraph`](src/pr_validation_agent/langgraph_service/graph.py:67)

LangGraph-based analysis workflow with three modes:

- `failure`
- `coverage`
- `summary`

## 6. End-to-End Data Flow

```text
GitHub PR event
  -> GitHub Actions workflow
  -> composite action
  -> Python validation runner
  -> setup + test execution
  -> AST detection + test matching
  -> LangGraph service analysis
  -> PR comment update
  -> label update
  -> status update
  -> reviewer sees pass/fail in GitHub UI
```

## 7. Setup from Scratch

## 7.1 Local prerequisites

You need:

- Python 3.11+
- `uv`
- Git
- a GitHub repository
- access to an LLM provider supported by [`init_chat_model()`](src/pr_validation_agent/langgraph_service/llm.py:17)

## 7.2 Install dependencies

```bash
uv sync --dev
```

## 7.3 Keep secrets in a local `.env` file

A local [`.env`](.env) file is supported for developer machines.

Use [`.env.example`](.env.example) as the template:

```bash
cp .env.example .env
```

Then set the credentials for the provider you actually use with [`build_chat_model()`](src/pr_validation_agent/langgraph_service/llm.py:12). The current default is [`openai:gpt-4.1-mini`](src/pr_validation_agent/langgraph_service/llm.py:13), so [`.env.example`](.env.example) exposes [`OPENAI_API_KEY`](.env.example:16).

Then fill in your real local secrets such as:

- `LANGGRAPH_SERVICE_TOKEN`
- `PR_VALIDATION_MODEL`
- `OPENAI_API_KEY`
- `LANGGRAPH_SERVICE_URL`
- `GITHUB_TOKEN`

Important:
- [`.env`](.gitignore) is already ignored by git
- never commit real secrets
- the default provider path in [`build_chat_model()`](src/pr_validation_agent/langgraph_service/llm.py:12) is OpenAI-compatible via [`openai:gpt-4.1-mini`](src/pr_validation_agent/langgraph_service/llm.py:13)
- GitHub Actions still needs GitHub repository or organization secrets; the local [`.env`](.env) is only for local development and testing

## 7.4 Run tests locally

```bash
uv run pytest -q
```

## 7.5 Start the LangGraph service locally

Load your local env first, then start the service.

Recommended command (uses the app module default host/port, typically `127.0.0.1:8000`):

```bash
set -a && source .env && set +a
uv run python -m pr_validation_agent.langgraph_service.app
```

Equivalent factory-based command if you want port `8080` explicitly:

```bash
set -a && source .env && set +a
uv run uvicorn pr_validation_agent.langgraph_service.app:create_app --factory --host 0.0.0.0 --port 8080
```

## 7.6 Quick local verification checklist

After starting the service, verify the project in this order:

1. Confirm the service starts without errors.
2. If you started the service with [`uv run python -m pr_validation_agent.langgraph_service.app`](src/pr_validation_agent/langgraph_service/app.py:131), open `http://localhost:8000/healthz`
3. If you started the service with [`uv run uvicorn pr_validation_agent.langgraph_service.app:create_app --factory --host 0.0.0.0 --port 8080`](src/pr_validation_agent/langgraph_service/app.py:128), open `http://localhost:8080/healthz`
4. Confirm the health response is:

```json
{"status":"ok"}
```

5. In another terminal, run:

```bash
uv run pytest -q
```

6. Confirm all tests pass.
7. If you want an end-to-end check, connect a test repository with [`.github/pr-validation.yml`](.github/pr-validation.yml) and raise a sample PR.

## 7.7 Shortest possible local start flow

If you just want the minimum commands:

```bash
uv sync --dev
set -a && source .env && set +a
uv run python -m pr_validation_agent.langgraph_service.app
```

Then in another terminal:

```bash
uv run pytest -q
```

## 8. Configure a Repository to Use This System

## 8.1 Copy the example config

Copy [`configs/pr-validation.example.yml`](configs/pr-validation.example.yml) into the consuming repository as:

```text
.github/pr-validation.yml
```

Example:

```yaml
version: 1

status:
  context: "intelligent-pr-validation"

setup:
  commands:
    - "uv sync --frozen"

tests:
  command: "uv run pytest -q --maxfail=1"

test_detection:
  test_file_patterns:
    - "tests/**"
    - "**/tests/**"
    - "**/*_test.py"
    - "**/test_*.py"
    - "**/*.test.ts"
    - "**/*.spec.ts"
  require_symbol_reference: true
  allow_llm_coverage_review: true

reviewers:
  request_review_when_passed: true
  fallback_reviewers: []
  fallback_teams: []

labels:
  enabled: true
  test_failed: "test-failed"
  needs_tests: "needs-tests"
  ready_for_review: "ready-for-review"
  merge_conflict: "merge-conflict"

auto_merge:
  enabled: false
  method: "SQUASH"
```

## 8.2 Use the included workflow

Use [`.github/workflows/pr-validation.yml`](.github/workflows/pr-validation.yml) in the repository.

It already:

- triggers on PR lifecycle events
- checks out PR head
- calls the reusable action
- passes service URL and tokens through secrets

## 8.3 Configure GitHub secrets

At repository or organization level, set:

- `LANGGRAPH_SERVICE_URL`
- `LANGGRAPH_SERVICE_TOKEN` (recommended if auth is enabled)

GitHub automatically provides:

- `GITHUB_TOKEN`

## 8.4 Enable branch protection

In GitHub branch protection or rulesets:

- require the `intelligent-pr-validation` status check
- optionally require branch to be up to date before merge

This is what actually disables merge until the workflow passes.

## 9. How Labels and Comments Work

The system keeps one idempotent PR comment using a marker string.

That means:

- it updates the same comment instead of spamming many comments
- the PR always shows the latest agent result

Possible labels:

- `test-failed`
- `needs-tests`
- `ready-for-review`
- `merge-conflict`

The workflow removes stale outcome labels and adds the current one.

## 10. What Happens in Each Outcome

## 10.1 Merge conflict

If the PR branch cannot merge the base branch in CI:

- PR comment explains merge conflict
- label `merge-conflict` is applied
- status becomes failure

## 10.2 Setup failure

If repository setup commands fail:

- PR comment explains failure
- PR author is mentioned
- label `test-failed` is applied
- status becomes failure

## 10.3 Test failure

If tests fail:

- test logs are summarized
- LangGraph suggests root cause and fixes
- PR author is mentioned
- label `test-failed` is applied
- status becomes failure

## 10.4 Missing tests for new functions

If new functions are added but tests are missing:

- AST/diff detection finds new functions
- test matching checks whether tests exist
- LangGraph suggests test cases
- PR author is mentioned
- label `needs-tests` is applied
- status becomes failure

## 10.5 Success

If everything passes:

- LangGraph generates PR summary
- optional code review command may run
- success comment is posted
- reviewers may be requested
- label `ready-for-review` is applied
- status becomes success

## 11. How to Test This End-to-End on GitHub

Yes — the correct real-world test is to create a small dummy repository, ask your friend to create branches and PRs, and then verify that the workflow, comments, labels, status checks, and merge button behave exactly as expected.

### 11.1 Create a dummy repository

Create a very small repository with:

- one source file
- one test file
- [`.github/workflows/pr-validation.yml`](.github/workflows/pr-validation.yml)
- [`.github/pr-validation.yml`](.github/pr-validation.yml)

Example structure:

```text
dummy-pr-demo/
  .github/
    workflows/
      pr-validation.yml
    pr-validation.yml
  src/
    calculator.py
  tests/
    test_calculator.py
```

Example `calculator.py`:

```python
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
```

Example `test_calculator.py`:

```python
from src.calculator import add, multiply

def test_add():
    assert add(2, 3) == 5

def test_multiply():
    assert multiply(2, 4) == 8
```

### 11.2 Add the PR validation setup

In that dummy repo:

1. add [`.github/workflows/pr-validation.yml`](.github/workflows/pr-validation.yml)
2. add [`.github/pr-validation.yml`](.github/pr-validation.yml) using [`configs/pr-validation.example.yml`](configs/pr-validation.example.yml)
3. configure repository secrets:
   - `LANGGRAPH_SERVICE_URL`
   - `LANGGRAPH_SERVICE_TOKEN`
4. make sure the LangGraph service is running and reachable

### 11.3 Enable branch protection

This step is mandatory if you want GitHub to truly disable merge.

In branch protection or rulesets for the target branch:

- require the `intelligent-pr-validation` check
- optionally require the branch to be up to date before merge

Without this, GitHub may still show the merge button even if the workflow fails.

### 11.4 Ask your friend to raise real PRs

Yes — this is exactly how you should test it.

Ask your friend to:

1. clone the dummy repo
2. create a new branch
3. make a change
4. push the branch
5. raise a PR to the protected branch

As soon as the PR is opened, the workflow should start automatically.

### 11.5 Test scenarios to try

#### Scenario A: Passing PR

Ask your friend to change code and keep tests passing.

Expected result:

- workflow passes
- PR gets success comment
- label becomes `ready-for-review`
- reviewer may be requested
- required status is green
- merge button is available

#### Scenario B: Failing tests

Ask your friend to intentionally break one function.

Example:

```python
def add(a, b):
    return a + b + 1
```

Expected result:

- CI test step fails
- PR gets failure comment
- author is mentioned
- label becomes `test-failed`
- required status is red
- merge button is disabled

#### Scenario C: Missing tests for a new function

Ask your friend to add a new function without adding tests.

Example:

```python
def subtract(a, b):
    return a - b
```

and do not add a matching test.

Expected result:

- main tests may still pass
- AST detection finds the new function
- missing-test validation fails
- PR gets missing-tests comment
- label becomes `needs-tests`
- required status is red
- merge button is disabled

#### Scenario D: Merge conflict

Create a conflict between the base branch and your friend’s branch, then raise the PR.

Expected result:

- merge step in CI fails
- PR gets merge-conflict comment
- label becomes `merge-conflict`
- required status is red
- merge button is disabled

### 11.6 What you should verify on every PR

For each test PR, check these in GitHub:

- GitHub Action started automatically
- exactly one bot comment is present and gets updated
- correct label is applied
- required status check is correct
- merge button is enabled only when validation succeeds

### 11.7 Best demo plan

The simplest and strongest demo is this:

1. create one dummy repository
2. enable this full setup
3. protect the target branch
4. ask your friend to create 3 PRs:
   - one passing PR
   - one failing-test PR
   - one missing-tests PR
5. compare the outcome of each PR in GitHub

If those three behave correctly, your automation is working the way you want.

## 12. Organization-Wide Reuse

This project is designed for reuse across many repositories and organizations.

### Recommended rollout model

1. Keep this project in one central repository.
2. Reuse [`action.yml`](action.yml) from multiple repositories.
3. Standardize [`.github/pr-validation.yml`](.github/pr-validation.yml) per repo.
4. Store `LANGGRAPH_SERVICE_URL` and `LANGGRAPH_SERVICE_TOKEN` as organization secrets.
5. Enforce `intelligent-pr-validation` in branch protection/rulesets.

### Why this works well

- central maintenance
- shared behavior across teams
- repository-specific test commands through config
- one reusable action instead of copying scripts everywhere

## 13. Security Model

### GitHub runner side

- uses `GITHUB_TOKEN`
- only needs the minimum permissions already defined in the workflow
- should avoid printing raw secrets or full sensitive logs

### LangGraph service side

- can require `LANGGRAPH_SERVICE_TOKEN`
- validates incoming requests
- supports rate limiting and concurrency control
- should stay internal or protected behind secure deployment

### Important rule

Do not let the LLM service become the system of record for merge decisions.
The CI runner is the source of truth.

## 14. Local Development Commands

Install:

```bash
uv sync --dev
```

Run tests:

```bash
uv run pytest -q
```

Run the service:

```bash
uv run uvicorn pr_validation_agent.langgraph_service.app:create_app --factory --reload
```

## 14. Implementation Notes for Developers

If you want to modify behavior, start with these files:

- validation flow: [`src/pr_validation_agent/ci/runner.py`](src/pr_validation_agent/ci/runner.py)
- GitHub integration: [`src/pr_validation_agent/github.py`](src/pr_validation_agent/github.py)
- PR comment formatting: [`src/pr_validation_agent/comments.py`](src/pr_validation_agent/comments.py)
- config model: [`src/pr_validation_agent/config.py`](src/pr_validation_agent/config.py)
- LLM prompts: [`src/pr_validation_agent/langgraph_service/prompts.py`](src/pr_validation_agent/langgraph_service/prompts.py)
- LangGraph routing: [`src/pr_validation_agent/langgraph_service/graph.py`](src/pr_validation_agent/langgraph_service/graph.py)

## 15. Prompt to Regenerate This Project Using an LLM

Use this prompt with an implementation model:

```text
Build a production-ready, organization-scalable Pull Request validation system for GitHub.

Goal:
Create an automated agent that runs whenever a PR is opened, synchronized, reopened, or marked ready for review. The system must decide merge readiness by combining CI test execution, AST-based change detection, test coverage discipline for newly added functions, and LLM-generated PR feedback. It must work for many repositories and be usable across multiple organizations.

Required workflow:
1. Trigger on pull_request events: opened, synchronize, reopened, ready_for_review.
2. Checkout the PR head SHA in GitHub Actions.
3. Merge the base branch into the PR branch inside CI before validation.
4. Run repository setup commands and then configured unit/integration tests.
5. If setup or tests fail:
   - collect logs
   - send logs and metadata to a LangGraph-based analysis service
   - generate a single idempotent PR comment that mentions the PR author
   - explain the likely root cause
   - list failed tests or failing checks
   - suggest fixes
   - apply label test-failed
   - set a GitHub commit status/check to failure
   - ensure branch protection can block merge
   - stop further processing
6. If tests pass:
   - diff base...head
   - detect new and modified functions using AST-based parsing, at minimum for Python and JavaScript/TypeScript
   - verify whether newly added functions have corresponding tests in the PR branch
7. If tests for new functions are missing:
   - call the LangGraph service to suggest meaningful tests
   - update the same PR comment
   - mention the PR author
   - apply label needs-tests
   - set status/check to failure
   - block merge
   - stop further processing
8. If all validation passes:
   - call the LangGraph service to create a concise reviewer summary
   - optionally run a non-gating code review command
   - update the same PR comment with success status and summary
   - request reviewers or teams if configured
   - apply label ready-for-review
   - set commit status/check to success
   - optionally enable auto-merge
   - make the system compatible with GitHub branch protection so merge is enabled only on success

Architecture constraints:
- separate CI orchestration from LLM logic
- GitHub Actions handles checkout, merge, setup, tests, labels, statuses, and PR comment updates
- LangGraph service only analyzes logs, ambiguous coverage findings, and PR summaries
- LangGraph must never decide merge eligibility or run tests itself
- maintain a single upserted PR comment identified by a marker string
- support reusable config via .github/pr-validation.yml
- support repository-level and organization-level secret management
- provide a reusable composite GitHub Action and an example GitHub workflow
- design for organization-wide adoption and multi-repository reuse

Implementation requirements:
- Python project managed with uv
- FastAPI service for LangGraph endpoints
- Pydantic models for contracts
- GitHub REST/GraphQL integration for comments, labels, reviewer requests, statuses, and optional auto-merge
- structured validation result model
- robust error handling for GitHub failures and unexpected internal failures
- tests for comment rendering, AST detection, and service security/authentication
- documentation explaining setup, scaling, security boundaries, and usage

Deliverables:
- GitHub workflow file
- composite action definition
- validation runner
- GitHub integration module
- AST detection modules
- LangGraph service with prompts and auth
- example config
- unit tests
- README with architecture, setup, scaling guidance, and example prompt
```

## 16. Which Files to Ignore Now

To reduce confusion, treat these as secondary/internal notes rather than primary docs:

- `CODE_FLOW_LLM_INTEGRATION.md`
- `LLM_DOCUMENTATION_INDEX.md`
- `LLM_EXAMPLE_WALKTHROUGH.md`
- `LLM_LANGGRAPH_ARCHITECTURE.md`
- `SECURITY_IMPLEMENTATION.md`

The primary docs should now be:

1. [`README.md`](README.md) — complete guide from scratch to implementation
2. [`NEXT_STEPS.md`](NEXT_STEPS.md) — future improvements and rollout roadmap
