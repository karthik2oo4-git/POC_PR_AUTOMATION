# PR Validation Agent

Production-ready reference implementation for Pull Request validation with GitHub Actions,
AST-based change analysis, native GitHub status checks, idempotent PR comments, and a
LangGraph-powered analysis service.

## Architecture

```text
Pull Request
  -> GitHub Actions checkout head SHA
  -> merge base branch into head in CI
  -> install dependencies with cache
  -> run configured tests
  -> detect changed/new/modified functions from base...head diff
  -> validate test discipline
  -> call LangGraph service for allowed LLM work only
  -> optionally run a non-gating code review command
  -> update one bot PR comment
  -> apply one workflow label
  -> set GitHub commit status and exit with pass/fail
```

LangGraph is intentionally isolated behind an API. It analyzes logs, suggests fixes,
evaluates ambiguous test coverage, and generates reviewer summaries. It never runs tests,
orchestrates CI, or decides merge eligibility.

## Project Structure

```text
.github/workflows/pr-validation.yml       GitHub Actions workflow
action.yml                                Reusable composite action wrapper
configs/pr-validation.example.yml         Per-repository config example
src/pr_validation_agent/
  ci/runner.py                            CI entrypoint and validation flow
  config.py                               YAML config loader
  models.py                               Shared typed contracts
  github.py                               GitHub comments/status/reviewer integration
  comments.py                             Idempotent PR comment body rendering
  detection/                              AST and diff-based function detection
  langgraph_service/                      FastAPI + LangGraph analysis service
tests/                                    Unit tests for core local behavior
```

## Setup

1. Copy `configs/pr-validation.example.yml` to `.github/pr-validation.yml` in each repo.
2. Keep repository setup isolated with uv in `.github/pr-validation.yml`:

```yaml
setup:
  commands:
    - "uv sync --frozen"
tests:
  command: "uv run pytest -q --maxfail=1"
```

3. Deploy the service:

```bash
uv sync --frozen
uv run uvicorn pr_validation_agent.langgraph_service.app:create_app --factory --host 0.0.0.0 --port 8080
```

4. Add `LANGGRAPH_SERVICE_URL` as a repository or organization secret.
5. Protect the base branch and require the `intelligent-pr-validation` status check.

Labels are managed through the PR issue API, so the workflow grants `issues: write`.
If `auto_merge.enabled` is turned on, grant the workflow the additional repository
permission required by your branch protection and merge policy.

Optional code review tools can be attached without changing the merge decision:

```yaml
code_review:
  enabled: true
  command: "uv run semgrep scan --config auto"
```

## Local Development

```bash
uv sync --dev
uv run pytest
uv run uvicorn pr_validation_agent.langgraph_service.app:create_app --factory --reload
```

## Scaling Model

Use the included workflow directly for a single repository, package `action.yml` as a
reusable GitHub Action for many repositories, or move the GitHub integration layer into a
GitHub App when central installation, organization-wide policy, and richer permissions are
needed.
