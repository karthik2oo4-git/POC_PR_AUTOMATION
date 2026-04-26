# NEXT STEPS

This is the only follow-up document you need after reading [`README.md`](README.md).

Use [`README.md`](README.md) for:

- understanding the full problem
- architecture
- repository structure
- setup from scratch
- workflow behavior
- implementation details
- organization-wide rollout
- LLM generation prompt

Use this file only for what should be done next after the current implementation is working.

## 1. Current Status

The project already supports:

- PR-triggered validation through GitHub Actions
- base-into-head merge check in CI
- setup command execution
- test execution
- AST-based function change detection
- missing-test validation for newly added functions
- LangGraph-powered failure analysis, coverage suggestions, and PR summaries
- single upserted PR comment
- labels for failed tests, missing tests, merge conflict, and ready-for-review
- reviewer notification on success
- optional auto-merge hooks
- reusable composite action for multi-repository adoption

## 2. What to Do Before Production Rollout

## 2.1 Deploy the LangGraph service

Deploy the FastAPI service from [`src/pr_validation_agent/langgraph_service/app.py`](src/pr_validation_agent/langgraph_service/app.py) to a secure environment.

Recommended:

- internal network deployment
- HTTPS
- environment-based secret management
- restricted inbound access

Required environment variables typically include:

- `LANGGRAPH_SERVICE_TOKEN`
- `PR_VALIDATION_MODEL`
- provider API key such as `OPENAI_API_KEY`

## 2.2 Configure GitHub secrets

At repository level or organization level, add:

- `LANGGRAPH_SERVICE_URL`
- `LANGGRAPH_SERVICE_TOKEN`

Then confirm [`.github/workflows/pr-validation.yml`](.github/workflows/pr-validation.yml) can reach the service.

## 2.3 Enforce branch protection

In GitHub branch protection or rulesets:

- require the `intelligent-pr-validation` status check
- optionally require branches to be up to date before merge
- optionally restrict who can bypass protections

This step is what ensures the merge button stays disabled until validation passes.

## 2.4 Standardize per-repository config

For each consuming repository:

- create [`.github/pr-validation.yml`](.github/pr-validation.yml)
- define setup commands
- define test command
- define language patterns if needed
- define fallback reviewers or teams if needed

Start from [`configs/pr-validation.example.yml`](configs/pr-validation.example.yml).

## 3. Recommended Improvements

## 3.1 Add integration tests

The current project has unit coverage, but production confidence improves a lot with integration tests.

Recommended scenarios:

- merge conflict path
- setup failure path
- test failure path
- missing tests path
- success path
- stale label removal
- reviewer request behavior
- auto-merge behavior
- comment upsert behavior

Best approach:

- use temporary git repositories
- mock GitHub API calls
- mock LangGraph responses
- feed real PR event payloads to [`validate()`](src/pr_validation_agent/ci/runner.py:223)

## 3.2 Improve JavaScript and TypeScript coverage

The repository already includes JS/TS detection support, but if you want organization-wide adoption, validate that your target repositories are covered well.

Focus areas:

- React projects
- Node services
- monorepos
- mixed Python and TypeScript repositories

## 3.3 Improve missing-test accuracy

Current missing-test detection is practical, but still heuristic.

Future upgrades can include:

- stronger symbol-to-test mapping
- per-language conventions
- framework-aware matching
- optional coverage-file integration
- deeper AST relationships between changed code and tests

## 3.4 Add observability

Recommended additions:

- structured logs
- validation counts by repository
- latency metrics
- GitHub API failure metrics
- LangGraph service error metrics
- alerting for service failures and high latency

## 3.5 Add stronger governance for org-wide rollout

If many teams will use this:

- publish the action from a central repository
- version releases clearly
- keep one managed LangGraph service
- document supported repository types
- define a standard onboarding checklist for new teams

## 4. Suggested Rollout Plan

### Phase 1: Local and sandbox validation
- run [`uv run pytest -q`](pyproject.toml:34)
- deploy service in a test environment
- connect one sample repository
- verify all PR outcomes manually

### Phase 2: Single-team production rollout
- enable branch protection
- add organization or repository secrets
- validate comments, labels, and reviewer notifications
- keep auto-merge disabled at first

### Phase 3: Multi-repository rollout
- publish and version the reusable action
- onboard additional repositories with standard config
- centralize secrets and documentation
- track performance and failures

### Phase 4: Organization-wide platform
- move to GitHub App model if needed
- add richer observability
- add more integration coverage
- improve governance and onboarding

## 5. Simple Rule for Documentation

From now on, use only these two files as the main docs:

1. [`README.md`](README.md) — complete guide from scratch to implementation
2. [`NEXT_STEPS.md`](NEXT_STEPS.md) — roadmap after implementation

Other markdown files in the repository should be treated as legacy reference notes, not the main reading path.
