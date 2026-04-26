# Production Readiness Plan

This document is the ordered execution plan for taking the current PR validation scaffold and turning it into a production-ready system.

The current repository already gives you these foundations:

- GitHub Actions workflow for PR-triggered validation
- CI runner that merges base into head in CI
- Test execution and failure handling
- AST-based function detection for Python
- Heuristic missing-test detection
- LangGraph-backed summary and failure analysis service
- PR status updates, PR comments, labels, reviewer notification, and optional auto-merge hooks

What it does not yet give you is production hardening. The main gaps are:

- No authentication between GitHub Actions and the LangGraph service
- No strong service-side rate limiting or payload protection
- No structured observability or alerting
- No integration tests for GitHub API behavior
- No end-to-end validation against a real repository
- JavaScript and TypeScript detection is not fully operationalized
- Missing-test detection is still heuristic, not coverage-grade

The rest of this file is the exact sequence to close those gaps.

## 1. Freeze The Baseline

Before changing behavior, make sure the current project is in a stable, reproducible state.

Do this now:

```bash
git init
git add .
git commit -m "Initial PR validation agent scaffold"
```

If the repository already exists, just create a clean checkpoint commit before the production work begins.

Then verify the local baseline:

```bash
uv sync --dev
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/python -m compileall src
```

Exit criteria for this step:

- Tests pass locally
- Lint passes locally
- The current branch is committed
- `uv.lock` is present and up to date

## 2. Add Service Authentication

This is the first real production task. Right now, anyone who can reach the LangGraph API could call it if you deploy it without another network control.

Implement:

1. Add `LANGGRAPH_SERVICE_TOKEN` to GitHub Actions secrets.
2. Update the CI client to send `Authorization: Bearer <token>`.
3. Add FastAPI middleware or dependency-based auth in the LangGraph service.
4. Reject missing or invalid tokens with `401 Unauthorized`.
5. Document token rotation.

Recommended implementation details:

- Secret name in GitHub: `LANGGRAPH_SERVICE_TOKEN`
- Secret name in service runtime: `LANGGRAPH_SERVICE_TOKEN`
- Header format: `Authorization: Bearer <token>`
- Do not log the raw token

Verification:

- Valid token returns `200`
- Missing token returns `401`
- Wrong token returns `401`
- Health endpoint can remain public or internal-only based on deployment choice

Exit criteria:

- CI-to-service authentication is enforced
- Unauthorized requests are blocked
- The token is never hardcoded in the repo

## 3. Protect The Service Perimeter

Authentication alone is not enough. Add guardrails around the FastAPI service before exposing it to real repositories.

Implement:

1. Request size limits
2. Timeout controls
3. Concurrency limits
4. Basic rate limiting
5. Optional IP allowlisting or internal network-only deployment

Recommended limits for the first rollout:

- Max request body size: 1 MB to 3 MB
- Request timeout to LLM: 30s to 60s
- API request timeout: 60s to 90s
- Max concurrent requests per instance: set based on CPU and model latency
- Rate limit per repository or token: start conservative

Also add:

- Validation of required fields in all analysis requests
- Safe fallback when the LLM is unavailable
- Structured error responses instead of raw stack traces

Exit criteria:

- Oversized payloads are rejected cleanly
- Timeouts do not hang the service
- Load spikes do not crash the instance

## 4. Add Structured Logging And Redaction

Before you run this in real repositories, you need logs that are safe and useful.

Implement structured JSON logs for:

- Repository owner and repo name
- PR number
- Head SHA
- Base branch
- Validation mode: `failure`, `coverage`, `summary`
- Service latency
- Test command outcome
- GitHub API operation outcome

Redact before sending anything to LangGraph:

- API keys
- Tokens
- Passwords
- Connection strings
- Any value matching known secret patterns

Good practice:

- Redact both in service logs and in LLM-bound payloads
- Keep an allowlist mindset for fields you send to the model
- Truncate noisy logs before model submission

Exit criteria:

- Logs are machine-readable
- Sensitive material is removed before persistence and LLM analysis
- You can trace a single PR run across CI and service logs

## 5. Add Observability And Alerting

You want to know when the system is slow, failing, or quietly degrading.

Add metrics for:

- Total PR validations
- Validation duration
- Test-failure rate
- Missing-test failure rate
- Merge-conflict failure rate
- LangGraph API latency
- LangGraph API error rate
- GitHub API error rate
- Comment update failures
- Label update failures

Add dashboards for:

- Validation volume by repository
- Success vs failure over time
- Median and p95 latency
- Service error spikes

Add alerts for:

- Service unavailable
- LangGraph request failure rate above threshold
- Validation latency above threshold
- GitHub API failures above threshold

Exit criteria:

- You can answer “Is it healthy?” in under 2 minutes
- You can identify whether failures are from GitHub, tests, config, or LLM service

## 6. Harden GitHub Workflow Permissions And Controls

Your GitHub Actions workflow is part of the production boundary.

Review and lock down:

- `contents: read`
- `pull-requests: write`
- `issues: write`
- `statuses: write`
- Only add more permissions if a specific feature truly needs them

If you enable auto-merge, confirm the exact permission and repo policy needed before rollout.

Also configure:

1. Branch protection on the base branch
2. Required status check: `intelligent-pr-validation`
3. “Require branches to be up to date before merging” if your org wants stricter merge safety
4. Concurrency control so only the newest run for a PR remains active

Exit criteria:

- Invalid PRs are blocked by GitHub native controls
- A stale workflow run cannot override a newer one
- Workflow permissions are least-privilege

## 7. Add Integration Tests For GitHub And Runner Behavior

Right now the project has unit tests, but not enough production-confidence tests.

Add integration tests for:

1. Merge conflict path
2. Test failure path
3. Missing tests path
4. Success path
5. Label application and stale label removal
6. Reviewer request behavior
7. Optional auto-merge enablement
8. Comment upsert behavior

How to do it:

- Use a temporary git repository fixture
- Mock GitHub REST and GraphQL APIs
- Mock LangGraph API responses
- Feed a real `GITHUB_EVENT_PATH` payload into the runner

At minimum, verify:

- Correct status is set
- Correct label is applied
- Correct comment body is updated
- Reviewer request happens only on success
- Developer mention happens only on failure comments

Exit criteria:

- Core PR outcomes are covered by automated tests
- Regressions in GitHub behavior are caught before deployment

## 8. Improve Missing-Test Detection Accuracy

This is one of the biggest quality gaps today. The current implementation is useful, but heuristic.

The current state:

- It checks newly added functions
- It looks for corresponding test file changes
- It matches by symbol reference in changed test files

That is good for a first pass, but not enough for broad production rollout.

Recommended path:

1. Keep the current heuristic as a fast pre-check
2. Add language-specific AST parsing for test files where possible
3. Support coverage artifacts when available
4. Let LangGraph evaluate ambiguous cases instead of all cases
5. Add repository-level ignore rules for generated code, migrations, and framework glue

Best long-term improvement:

- Use coverage XML, LCOV, or language-native coverage reports to confirm whether new logic is exercised

Exit criteria:

- False positives are manageable
- False negatives are reduced
- Teams trust the “missing tests” signal enough to enforce it

## 9. Complete Multi-Language Support Properly

Python support is the most real today. JavaScript and TypeScript support needs packaging work, and additional languages are still future extensions.

Do this for JavaScript and TypeScript:

1. Decide whether parsing lives in this repo or in target repos
2. If it lives in this repo, package the parser dependency as part of the action or service runtime
3. Verify Node availability in the GitHub runner path that executes detection
4. Add tests that prove JS and TS function extraction works in CI

Then expand only if needed:

- Java
- Go
- Kotlin
- C#

Recommended rule:

- Do not advertise a language as “supported” until it has parser packaging, tests, and a sample validation repo

Exit criteria:

- Every enabled language in config is actually runnable in CI
- Language support claims match reality

## 10. Deploy The LangGraph Service Properly

Pick a deployment model before onboarding repositories.

Recommended rollout order:

1. Internal staging environment
2. One real test repository
3. Small pilot group
4. Broad rollout

Minimum production deployment checklist:

- Container image built from this repo
- Environment variables managed by secret store
- Health checks enabled
- Autoscaling or at least restart policy configured
- HTTPS enforced
- Deployment history retained
- Central logs connected

Environment variables to define:

- `OPENAI_API_KEY`
- `LANGGRAPH_SERVICE_TOKEN`
- `PR_VALIDATION_MODEL`
- Any provider-specific timeout or logging flags you add

Exit criteria:

- The service survives restarts
- Health checks work
- Secrets come from platform secret management, not shell history or files

## 11. Create A Staging Repository For End-To-End Testing

Do not test first in a critical repository.

Create one controlled staging repo and wire in:

- The workflow from this project
- `.github/pr-validation.yml`
- `LANGGRAPH_SERVICE_URL`
- `LANGGRAPH_SERVICE_TOKEN`
- Branch protection

Then execute these end-to-end scenarios:

1. Merge conflict
2. Setup failure
3. Test failure
4. Missing tests
5. Successful PR with reviewer request
6. Successful PR with optional code-review command
7. Successful PR with optional auto-merge

Record for each scenario:

- GitHub check result
- Label result
- Comment result
- Reviewer result
- Service logs
- Total latency

Exit criteria:

- All required flows work in a real GitHub repository
- No manual intervention is needed for normal PR validation

## 12. Add Failure Recovery And Retry Rules

Transient failures will happen in production. Make sure they fail predictably.

Add retries for:

- GitHub API transient errors
- LangGraph service transient errors
- Temporary network issues

Do not retry blindly for:

- Invalid config
- Authentication failure
- Persistent merge conflicts
- Deterministic test failures

Also define:

- What happens when LangGraph is unavailable
- Whether validation should fail closed or fail open

Recommended policy:

- Fail closed for merge gating
- Return a clear PR comment if analysis is unavailable
- Do not pretend a PR is safe when the required validation service is down

Exit criteria:

- Temporary outages do not create noisy false failures
- Permanent failures are surfaced clearly and fast

## 13. Prepare Repository Onboarding Documentation

Once the system works, make onboarding easy for other teams.

Each onboarding guide should include:

1. Required secrets
2. Required workflow permissions
3. Required branch protection settings
4. Example `.github/pr-validation.yml`
5. Supported languages
6. Known limitations
7. How to interpret labels and bot comments
8. How to disable optional features such as auto-merge or code review

Exit criteria:

- A new repo owner can onboard without asking the platform team basic setup questions

## 14. Decide The Distribution Model

You have three realistic rollout models:

1. Reusable GitHub Action
2. Reusable GitHub Workflow
3. GitHub App

Recommended order:

1. Start with the current workflow and action for one repo
2. Move to a reusable workflow for multi-repo consistency
3. Move to a GitHub App when you need org-wide installation, centralized permissions, or policy enforcement

Choose the GitHub App path when:

- Many repositories will use this
- You need organization-wide installation
- You want better auditability and permission control
- You want to avoid overloading `GITHUB_TOKEN`-based patterns

Exit criteria:

- The packaging model matches the scale of rollout
- You are not hand-copying workflow files repo by repo forever

## 15. Build An Operations Runbook

Before production rollout, document how humans support the system.

The runbook should answer:

1. How to diagnose a failed PR validation
2. How to distinguish test failure from service failure
3. How to rotate secrets
4. How to pause reviewer notification without removing merge blocking
5. How to disable auto-merge safely
6. How to respond when GitHub API changes or rate limits start failing runs
7. How to deploy a rollback for the LangGraph service

Exit criteria:

- The system can be operated by someone other than the original author

## 16. Recommended Order Of Work

If you want the shortest path to production readiness, do the work in this order:

1. Freeze the baseline and commit the current state
2. Add CI-to-service authentication
3. Add service-side request limits, timeouts, and redaction
4. Add structured logging, metrics, and alerts
5. Add integration tests for runner and GitHub behavior
6. Improve missing-test detection accuracy
7. Finish JavaScript and TypeScript packaging support
8. Deploy to staging
9. Validate all end-to-end scenarios in a staging repository
10. Enable branch protection and onboard one pilot repo
11. Run a pilot with real developers
12. Convert to reusable distribution for broader rollout

## 17. Production Readiness Checklist

Do not call the system production-ready until all of the following are true:

- CI-to-service authentication is enabled
- Secrets are stored only in GitHub Secrets or platform secret management
- LangGraph service has request limits and timeouts
- Structured logs and metrics exist
- Alerts exist for service failure and latency
- Branch protection is configured in GitHub
- A staging repository has validated all core scenarios
- Integration tests cover all major runner outcomes
- Missing-test detection quality is acceptable for the target team
- Every enabled language is truly supported in CI
- An operations runbook exists
- At least one real repository has completed a stable pilot period

## 18. The First Three Tasks You Should Do Next

If you want the most practical immediate path, start here:

1. Implement `LANGGRAPH_SERVICE_TOKEN` authentication end to end.
2. Create one staging repository and run all required PR scenarios against it.
3. Add integration tests for comment upsert, labels, statuses, and reviewer requests.

Those three steps will move this project from “good scaffold” to “serious candidate for production rollout.”
