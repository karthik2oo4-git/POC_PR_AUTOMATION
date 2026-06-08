# Design

## GitHub App setup

Create the GitHub App with:

- webhook URL pointing to `/webhooks/github`
- webhook secret configured in [`.env.example`](.env.example)
- permissions:
  - Checks: read and write
  - Pull requests: read
  - Contents: read
  - Actions: read and write
  - Metadata: read

Subscribe to:

- push
- pull_request
- installation
- workflow_run

## Authentication flow

1. Receive webhook event.
2. Load settings from [`Settings`](src/github_ci_governance_app/core/settings.py:9).
3. Generate JWT using [`build_app_jwt()`](src/github_ci_governance_app/integrations/github/auth.py:9).
4. Exchange JWT for installation token using [`GitHubClient.create_installation_token()`](src/github_ci_governance_app/integrations/github/client.py:15).
5. Use installation token for repository-scoped API calls.

## Webhook processing design

[`github_webhook()`](src/github_ci_governance_app/api/webhooks.py:76) performs:

- signature validation
- allowed event validation
- duplicate delivery detection
- graceful ignore behavior for unsupported events
- event payload parsing
- event-specific business handler dispatch
- fast acknowledgment with HTTP 202 semantics

The webhook layer is intentionally preserved and extended rather than redesigned.

## Push event business flow

[`GovernanceService.handle_push()`](src/github_ci_governance_app/services/governance.py:40) performs:

1. Ignore protected branches:
   - `main`
   - `master`
   - `release/*`
   - `hotfix/*`
2. Create `Lightweight Validation` check with `in_progress`
3. Persist validation state for repository, branch, SHA, and validation type
4. Dispatch lightweight workflow with retry support
5. Wait for [`workflow_run`](src/github_ci_governance_app/api/webhooks.py:157) to finalize status

## Pull request business flow

[`GovernanceService.handle_pull_request()`](src/github_ci_governance_app/services/governance.py:95) performs:

1. Accept only:
   - `opened`
   - `synchronize`
   - `reopened`
2. Extract PR number, repository, head SHA, and base branch
3. Query validation state for the latest PR head SHA
4. If lightweight validation is not successful:
   - create queued `Heavy Validation` check
   - publish waiting summary
   - do not dispatch heavy workflow
5. If lightweight validation is successful:
   - create `Heavy Validation` check with `in_progress`
   - dispatch heavy workflow with retry support

## Latest SHA validation rule

The authoritative commit is always the current PR head SHA.

[`PullRequestGovernanceService.is_latest_sha()`](src/github_ci_governance_app/services/pr_governance.py:42) models the freshness comparison rule.

Decision rule:

- if candidate SHA != current PR head SHA, treat result as stale
- stale workflow results must not trigger heavy validation
- stale workflow results must not overwrite authoritative PR decisions

## Workflow run business flow

[`GovernanceService.handle_workflow_run()`](src/github_ci_governance_app/services/governance.py:169) performs:

1. Identify workflow name
2. Map workflow name to validation type
3. Update validation state for repository, branch, SHA, and workflow run id
4. Publish the corresponding GitHub Check conclusion
5. Preserve details URL for operator visibility

Supported conclusions:

- `queued`
- `in_progress`
- `success`
- `failure`
- `cancelled`
- `timed_out`

## Test enforcement design

[`expected_test_patterns()`](src/github_ci_governance_app/services/language_rules.py:65) infers expected tests from built-in conventions.
[`TestEnforcementService.evaluate()`](src/github_ci_governance_app/services/test_enforcement.py:9) checks newly added source files against repository tree contents.
[`PullRequestGovernanceService.enforce_tests()`](src/github_ci_governance_app/services/pr_governance.py:22) publishes checks and PR comments for missing tests.

Supported languages currently modeled:

- Python
- TypeScript
- JavaScript
- Java
- Go
- Kotlin
- C#

Extensibility path:

- add new suffix rules in [`RULES`](src/github_ci_governance_app/services/language_rules.py:14)
- add naming conventions per language
- add module-aware path constraints

Ignored categories:

- documentation-only files
- infrastructure-only files
- generated outputs
- test files
- unsupported languages

## Checks and comments strategy

Checks currently modeled:

- `Lightweight Validation`
- `Heavy Validation`
- `Test Enforcement`

Comment strategy:

- one semantic comment per PR purpose
- deduplicate using repository + PR number + semantic key
- consolidate missing coverage into one comment body

## Retry and failure handling strategy

[`with_retry()`](src/github_ci_governance_app/services/retry.py:10) provides bounded exponential backoff.

Current retry targets:

- workflow dispatch
- installation token dependent GitHub API operations

Production evolution should add:

- rate-limit aware retry using `Retry-After`
- retry classification by HTTP status
- circuit breaking for repeated upstream failures

## Edge-case handling strategy

Handled or planned:

- duplicate webhook deliveries
- unsupported events
- unsupported PR actions
- protected branch pushes
- malformed payloads
- stale SHA workflow completions
- missing lightweight validation before heavy validation
- missing tests for newly added source files only
- unsupported file extensions
- generated file paths
- repeated PR comments

## Logging and observability strategy

[`configure_logging()`](src/github_ci_governance_app/core/logging.py:5) sets structured console logging.

Required log fields:

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

## Production-ready implementation plan

1. Replace in-memory stores with durable shared storage
2. Extend [`GitHubClient`](src/github_ci_governance_app/integrations/github/client.py:11) with:
   - PR file retrieval
   - repository tree retrieval
   - Checks API integration
   - PR comment integration
3. Wire [`PullRequestGovernanceService`](src/github_ci_governance_app/services/pr_governance.py:10) into PR event handling
4. Add stale-result suppression before check updates
5. Add metrics and tracing exporters
6. Add unit and integration tests for all business handlers