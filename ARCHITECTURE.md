# Architecture

## Level 1 platform overview

```text
GitHub App
    │
    ▼
GitHub Webhooks
    │
    ▼
FastAPI Webhook API
    │
    ▼
Event Router
    │
    ├── Push Handler
    ├── Pull Request Handler
    ├── Workflow Run Handler
    └── Duplicate Delivery Guard
    │
    ▼
Business Logic Layer
    ├── Governance Service
    ├── Validation State Store
    ├── Check Publisher
    ├── PR Comment Service
    ├── Test Enforcement Service
    └── Retry Policy
    │
    ▼
GitHub REST APIs / GitHub Actions
    ├── workflow dispatch
    ├── checks
    ├── pull request files
    └── comments
```

## Folder structure

```text
src/github_ci_governance_app/
├── api/
│   └── webhooks.py
├── core/
│   ├── logging.py
│   └── settings.py
├── domain/
│   ├── governance_models.py
│   └── models.py
├── integrations/
│   └── github/
│       ├── auth.py
│       └── client.py
├── orchestration/
│   └── coordinator.py
└── services/
    ├── checks.py
    ├── comments.py
    ├── delivery_store.py
    ├── governance.py
    ├── language_rules.py
    ├── pr_governance.py
    ├── retry.py
    ├── signature.py
    ├── test_enforcement.py
    └── validation_state.py
```

## Responsibility boundaries

GitHub App platform responsibilities:

- installation authentication
- webhook validation
- event routing
- staged validation orchestration
- SHA-aware decision making
- test enforcement
- checks and PR comments
- duplicate delivery protection
- retry-aware GitHub API coordination

GitHub Actions responsibilities:

- workflow execution
- runner allocation
- retries inside workflow execution
- logs
- execution lifecycle

## Core components

### API layer

[`src/github_ci_governance_app/api/webhooks.py`](src/github_ci_governance_app/api/webhooks.py) exposes [`github_webhook()`](src/github_ci_governance_app/api/webhooks.py:76) as the GitHub entry point and routes supported events into the business layer.

### Settings and runtime configuration

[`Settings`](src/github_ci_governance_app/core/settings.py:9) centralizes environment-driven configuration, allowed events, workflow names, and retry policy construction.

### Authentication

[`build_app_jwt()`](src/github_ci_governance_app/integrations/github/auth.py:9) generates GitHub App JWTs.
[`GitHubClient.create_installation_token()`](src/github_ci_governance_app/integrations/github/client.py:15) exchanges JWTs for installation tokens.

### Business logic layer

[`GovernanceService`](src/github_ci_governance_app/services/governance.py:25) handles push, pull request, and workflow run orchestration.
[`PullRequestGovernanceService`](src/github_ci_governance_app/services/pr_governance.py:10) handles PR-specific test enforcement and deduplicated comment publishing.

### Validation state

[`InMemoryValidationStateStore`](src/github_ci_governance_app/services/validation_state.py:8) stores validation state keyed by repository, branch, SHA, and validation type.

### Checks and comments

[`InMemoryCheckPublisher`](src/github_ci_governance_app/services/checks.py:8) models GitHub Checks publishing behavior.
[`InMemoryPullRequestCommentService`](src/github_ci_governance_app/services/comments.py:8) models deduplicated PR comment publishing.

### Test enforcement

[`expected_test_patterns()`](src/github_ci_governance_app/services/language_rules.py:65) infers expected tests from built-in conventions.
[`TestEnforcementService.evaluate()`](src/github_ci_governance_app/services/test_enforcement.py:9) evaluates newly added source files against repository tree contents.

### Reliability controls

[`validate_github_signature()`](src/github_ci_governance_app/services/signature.py:10) validates webhook signatures.
[`InMemoryDeliveryStore`](src/github_ci_governance_app/services/delivery_store.py:6) provides duplicate delivery protection using `X-GitHub-Delivery`.
[`with_retry()`](src/github_ci_governance_app/services/retry.py:10) provides bounded exponential backoff for retryable operations.

## Sequence diagrams

### Push flow

```text
GitHub push webhook
  -> Event Router
  -> GovernanceService.handle_push()
  -> create "Lightweight Validation" check as in_progress
  -> persist validation state for SHA
  -> dispatch lightweight workflow
  -> workflow_run event arrives later
  -> update validation state
  -> update check conclusion
```

### Pull request flow

```text
GitHub pull_request webhook
  -> Event Router
  -> GovernanceService.handle_pull_request()
  -> fetch latest lightweight validation for PR head SHA
  -> if not successful:
       create queued "Heavy Validation" check
       stop
  -> else:
       create in_progress "Heavy Validation" check
       dispatch heavy workflow
```

### Test enforcement flow

```text
PR synchronization/open/reopen
  -> PullRequestGovernanceService.enforce_tests()
  -> inspect newly added source files
  -> infer expected test patterns
  -> compare against repository files
  -> publish "Test Enforcement" check
  -> if missing tests:
       publish deduplicated PR comment
```

## SHA-aware orchestration model

Commit SHA is the only source of truth.

Rules:

1. Push events dispatch lightweight validation for the pushed SHA.
2. Pull request events evaluate only the latest PR head SHA.
3. Heavy validation is allowed only when lightweight validation for the latest SHA succeeds.
4. Older workflow results are treated as stale and ignored.
5. PR governance must compare candidate SHA against current PR head SHA before acting on results.

## Idempotency model

The webhook layer tolerates retries and duplicate deliveries.

Current Level 1 implementation uses:

- [`InMemoryDeliveryStore`](src/github_ci_governance_app/services/delivery_store.py:6) for delivery deduplication
- check keys based on repository, SHA, and check name
- comment deduplication keys based on repository, PR number, and semantic purpose

For production hardening, these in-memory stores should evolve to durable shared storage while preserving the same interfaces.

## Edge-case handling strategy

Handled or modeled explicitly:

- unsupported events are ignored with `202`
- unsupported PR actions are ignored
- pushes to `main`, `master`, `release/*`, and `hotfix/*` are ignored
- duplicate deliveries are ignored
- malformed payloads return `400`
- stale SHA results are non-authoritative
- missing lightweight validation queues heavy validation instead of dispatching it
- unsupported file types are skipped during test enforcement
- generated and infrastructure files are skipped during test enforcement

## Observability model

Every business log should include:

- repository
- event
- sha
- pr_number
- delivery_id

Recommended metrics:

- `push_received`
- `pr_received`
- `workflow_completed`
- `validation_success`
- `validation_failure`
- `test_enforcement_failure`

## Deployment model

- local development via UV and Uvicorn
- containerized deployment via Docker
- stateless application design
- GitHub APIs as operational source of truth
- future production deployment should externalize state stores and metrics sinks