# Implementation Roadmap

## Phase 1: Foundation

- Create UV-managed Python project
- Define settings and environment model
- Add FastAPI application bootstrap
- Add webhook endpoint and signature validation
- Add duplicate delivery protection

## Phase 2: GitHub App integration

- Implement JWT generation
- Implement installation token exchange
- Add GitHub API client abstraction
- Add workflow dispatch support
- Add repository and PR metadata retrieval

## Phase 3: Validation orchestration

- Dispatch lightweight validation on push
- Ignore protected branches on push
- Evaluate latest PR SHA on pull request events
- Gate heavy validation on successful lightweight validation
- Ignore stale workflow results for older SHAs
- Update validation state from workflow run completions

## Phase 4: Test enforcement

- Retrieve changed files for PR
- Detect newly added source files only
- Infer language and expected test patterns
- Search repository tree for matching tests
- Publish consolidated missing coverage result
- Publish deduplicated PR comments for missing tests

## Phase 5: GitHub feedback loop

- Create GitHub Checks for:
  - Lightweight Validation
  - Heavy Validation
  - Test Enforcement
- Surface actionable remediation guidance in GitHub UI
- Preserve workflow details URLs in check summaries

## Phase 6: Production hardening

- Replace in-memory delivery store with shared durable storage
- Replace in-memory validation state with durable shared storage
- Replace in-memory checks/comments adapters with GitHub-backed implementations
- Add retry and timeout policies for GitHub API calls
- Add rate-limit aware retry handling
- Add background processing for webhook fan-out
- Add observability, metrics, and tracing
- Add deployment manifests for target runtime

## Service implementation map

- [`GovernanceService`](src/github_ci_governance_app/services/governance.py:25)
  - push orchestration
  - PR heavy validation gating
  - workflow completion updates
- [`PullRequestGovernanceService`](src/github_ci_governance_app/services/pr_governance.py:10)
  - test enforcement checks
  - deduplicated PR comments
  - stale SHA comparison helper
- [`InMemoryValidationStateStore`](src/github_ci_governance_app/services/validation_state.py:8)
  - repository/branch/SHA validation state
- [`InMemoryCheckPublisher`](src/github_ci_governance_app/services/checks.py:8)
  - check publishing abstraction
- [`InMemoryPullRequestCommentService`](src/github_ci_governance_app/services/comments.py:8)
  - comment deduplication abstraction
- [`with_retry()`](src/github_ci_governance_app/services/retry.py:10)
  - bounded exponential backoff

## Test strategy

Unit tests should cover:

- protected branch filtering
- duplicate delivery handling
- lightweight gating for heavy validation
- stale SHA suppression
- workflow conclusion mapping
- language rule inference
- missing test detection
- comment deduplication
- retry behavior

Integration tests should cover:

- push webhook to lightweight dispatch path
- PR webhook to queued heavy validation path
- PR webhook to heavy dispatch path after lightweight success
- workflow run completion updating validation state and checks
- malformed payload rejection
- unsupported event graceful ignore

## Edge-case checklist

- Pushes to `main`, `master`, `release/*`, `hotfix/*`
- Multiple pushes for SHA1, SHA2, SHA3 before PR open
- PR synchronize while lightweight validation still running
- Duplicate webhook deliveries
- Unsupported PR actions
- Unsupported file extensions
- Generated files and docs-only changes
- Workflow completion for stale SHA
- GitHub API transient failures
- Missing installation payloads

## UV-based developer workflow

Initialize environment:

```bash
uv venv
source .venv/bin/activate
uv sync
```

Run locally:

```bash
uv run uvicorn github_ci_governance_app.main:app --reload
```

Test:

```bash
uv run pytest
```

Lint:

```bash
uv run ruff check .
```

Type-check:

```bash
uv run mypy src
```

Build container:

```bash
docker build -t github-ci-governance-app .