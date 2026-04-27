# PR Validation Agent

A reusable GitHub pull request validation system focused on one core job: run repository setup and unit tests on pull requests, then let GitHub branch protection decide whether merge is allowed.

## Overview

This project implements a GitHub-native PR validation flow that is portable across repositories and organizations.

Main behavior:

- A pull request is opened, synchronized, reopened, or marked ready for review
- GitHub Actions starts automatically
- The workflow checks out the PR head commit
- The validator merges the latest base branch into the PR branch inside CI
- Repository setup commands run
- Unit tests run
- If setup or tests fail, the workflow fails and merge stays blocked
- If setup and tests pass, the workflow succeeds and merge can be allowed by branch protection

This directly supports the two required flows:

1. PR raised -> GitHub workflow starts -> unit tests run -> all tests pass -> allow merge
2. PR raised -> GitHub workflow starts -> unit tests run -> any test fails -> GitHub shows failed checks/logs and merge is blocked

## Why this approach works

GitHub already provides the core merge-control features needed for this use case:

- Failed workflows show red status on the PR
- Required status checks block the merge button
- Actions logs show which step failed
- Reruns happen automatically when new commits are pushed
- Branch protection makes the rule enforceable for teams and organizations

Because of that, the current solution does not depend on any LLM-based analysis for merge decisions.

## High-level architecture

```text
Pull Request Raised
   ->
GitHub Actions Workflow
   ->
Composite Action
   ->
Python Validation Runner
   ->
Merge latest base branch into PR head in CI
   ->
Run setup commands
   ->
Run unit tests
   ->
If setup/tests fail:
   -> update one PR comment
   -> apply failure label
   -> set failed status
   -> GitHub blocks merge through required check

If setup/tests pass:
   -> update one PR comment
   -> apply success label
   -> set success status
   -> GitHub allows merge if branch protection requirements are satisfied
```

## Repository structure

Top-level items:

- [`.github`](.github) — GitHub Actions workflow definitions
- [`configs`](configs/pr-validation.example.yml) — example validator configuration
- [`src`](src/pr_validation_agent/__init__.py) — Python implementation
- [`tests`](tests/test_comments.py) — unit tests
- [`action.yml`](action.yml) — reusable composite GitHub Action
- [`Dockerfile`](Dockerfile) — optional packaging container
- [`pyproject.toml`](pyproject.toml) — project metadata, dependencies, scripts, and tooling config
- [`uv.lock`](uv.lock) — dependency lock file
- [`.gitignore`](.gitignore) — ignored local/generated files
- [`.python-version`](.python-version) — Python version hint
- [`README.md`](README.md) — consolidated project documentation

Generated or local-only files that should not be committed include:

- [`.venv/`](.gitignore:1)
- [`.uv-cache/`](.gitignore:2)
- [`__pycache__/`](.gitignore:3)
- [`.pytest_cache/`](.gitignore:5)
- [`.ruff_cache/`](.gitignore:6)
- [`.pr-validation-test.log`](.gitignore:7)
- [`.env`](.gitignore:8)

## Workflow and execution flow

### 1. Workflow trigger

The example workflow lives in [`.github/workflows/pr-validation.yml`](.github/workflows/pr-validation.yml).

It runs on these PR events:

- `opened`
- `synchronize`
- `reopened`
- `ready_for_review`

### 2. Reusable action

The workflow calls the composite action in [`action.yml`](action.yml).

The action:

- installs [`uv`](action.yml:19)
- installs Python with [`uv python install`](action.yml:27)
- syncs the validator environment with [`uv sync --frozen --no-dev`](action.yml:32)
- runs the CLI entrypoint [`pr-validation-ci`](action.yml:37)

### 3. Main validation runner

The validator entrypoint is [`validate()`](src/pr_validation_agent/ci/runner.py:153).

It:

- loads config through [`AppConfig.load()`](src/pr_validation_agent/config.py:73)
- loads PR event payload through [`_load_event()`](src/pr_validation_agent/ci/runner.py:20)
- builds a GitHub client through [`GitHubClient.from_env()`](src/pr_validation_agent/github.py:24)
- reads PR metadata through [`load_pr_context_from_event()`](src/pr_validation_agent/github.py:45)
- sets a pending commit status through [`set_status()`](src/pr_validation_agent/github.py:63)

### 4. Merge base branch into PR head in CI

The key merge behavior is implemented in [`merge_base_into_head()`](src/pr_validation_agent/ci/runner.py:114).

It runs git commands to:

- configure the Git identity
- fetch the latest base branch from origin
- merge the base branch into the checked-out PR head

This ensures tests run against the merged CI state that matters to reviewers.

If the merge fails:

- [`render_merge_conflict_comment()`](src/pr_validation_agent/comments.py:74) creates the PR comment
- [`upsert_comment()`](src/pr_validation_agent/github.py:81) updates a single managed bot comment
- [`apply_outcome_label()`](src/pr_validation_agent/github.py:157) applies the merge-conflict label
- [`set_status()`](src/pr_validation_agent/github.py:63) marks validation as failed

### 5. Setup and unit tests

Repository setup commands run through [`run_setup()`](src/pr_validation_agent/ci/runner.py:67).

Unit tests run through [`run_tests()`](src/pr_validation_agent/ci/runner.py:35).

Both return a [`TestRunResult`](src/pr_validation_agent/models.py:16) that contains:

- command
- exit code
- passed
- duration
- stdout
- stderr
- optional log path

### 6. Failure path

If setup fails or tests fail:

- [`render_test_failure_comment()`](src/pr_validation_agent/comments.py:26) updates one PR comment
- the author is mentioned
- the `test-failed` label can be applied
- commit status becomes `failure`
- GitHub branch protection keeps merge blocked

The failure comment points developers to GitHub-native troubleshooting:

- PR Checks tab
- failed workflow run
- step logs
- local reproduction using the same command

### 7. Success path

If merge succeeds, setup succeeds, and tests pass:

- [`render_success_comment()`](src/pr_validation_agent/comments.py:99) posts a success message
- the `ready-for-review` label can be applied
- commit status becomes `success`

Once the check is configured as a required status check in branch protection, GitHub can enable merge.

## Source code structure

The main source package is [`src/pr_validation_agent`](src/pr_validation_agent/__init__.py).

Primary source files:

- [`src/pr_validation_agent/models.py`](src/pr_validation_agent/models.py)
- [`src/pr_validation_agent/config.py`](src/pr_validation_agent/config.py)
- [`src/pr_validation_agent/comments.py`](src/pr_validation_agent/comments.py)
- [`src/pr_validation_agent/github.py`](src/pr_validation_agent/github.py)
- [`src/pr_validation_agent/ci/runner.py`](src/pr_validation_agent/ci/runner.py)

### Shared models

[`src/pr_validation_agent/models.py`](src/pr_validation_agent/models.py) contains the shared models used by the validator.

Important models:

- [`ValidationState`](src/pr_validation_agent/models.py:9) — commit status values sent to GitHub
- [`TestRunResult`](src/pr_validation_agent/models.py:16) — result of a setup or test command
- [`PullRequestContext`](src/pr_validation_agent/models.py:26) — PR metadata extracted from the event payload
- [`ValidationResult`](src/pr_validation_agent/models.py:41) — final result returned by the validator

### Configuration schema

[`src/pr_validation_agent/config.py`](src/pr_validation_agent/config.py) defines the YAML configuration schema.

Important config classes:

- [`StatusConfig`](src/pr_validation_agent/config.py:11) — commit status context name and optional target URL
- [`TestsConfig`](src/pr_validation_agent/config.py:16) — test command and timeout behavior
- [`SetupConfig`](src/pr_validation_agent/config.py:23) — setup commands run before tests
- [`ReviewersConfig`](src/pr_validation_agent/config.py:28) — optional reviewer request settings
- [`LabelsConfig`](src/pr_validation_agent/config.py:34) — optional outcome labels
- [`AutoMergeConfig`](src/pr_validation_agent/config.py:56) — optional auto-merge settings
- [`CommentsConfig`](src/pr_validation_agent/config.py:61) — PR comment marker and comment settings
- [`AppConfig.load()`](src/pr_validation_agent/config.py:73) — load YAML from disk and validate it

### Comment rendering

[`src/pr_validation_agent/comments.py`](src/pr_validation_agent/comments.py) renders the managed PR comments.

Important functions:

- [`_format_log_excerpt()`](src/pr_validation_agent/comments.py:6) — builds a small log excerpt from captured output
- [`render_test_failure_comment()`](src/pr_validation_agent/comments.py:26) — comment for setup or test failure
- [`render_merge_conflict_comment()`](src/pr_validation_agent/comments.py:74) — comment for merge conflicts
- [`render_success_comment()`](src/pr_validation_agent/comments.py:99) — comment for successful validation

### GitHub API integration

[`src/pr_validation_agent/github.py`](src/pr_validation_agent/github.py) wraps GitHub API interactions.

Important methods in [`GitHubClient`](src/pr_validation_agent/github.py:19):

- [`from_env()`](src/pr_validation_agent/github.py:24) — loads `GITHUB_TOKEN`
- [`load_pr_context_from_event()`](src/pr_validation_agent/github.py:45) — builds [`PullRequestContext`](src/pr_validation_agent/models.py:26)
- [`set_status()`](src/pr_validation_agent/github.py:63) — posts commit status for the PR head SHA
- [`upsert_comment()`](src/pr_validation_agent/github.py:81) — maintains a single managed bot comment
- [`request_reviewers()`](src/pr_validation_agent/github.py:107) — optional reviewer handling
- [`ensure_label()`](src/pr_validation_agent/github.py:122) — creates labels if needed
- [`add_labels()`](src/pr_validation_agent/github.py:134) — applies labels
- [`remove_label()`](src/pr_validation_agent/github.py:144) — removes labels
- [`apply_outcome_label()`](src/pr_validation_agent/github.py:157) — manages outcome label transitions
- [`enable_auto_merge()`](src/pr_validation_agent/github.py:168) — optional helper for auto-merge

### Runner orchestration

[`src/pr_validation_agent/ci/runner.py`](src/pr_validation_agent/ci/runner.py) is the main orchestration engine.

Important functions:

- [`_load_event()`](src/pr_validation_agent/ci/runner.py:20) — reads the GitHub event payload
- [`_truncate_log()`](src/pr_validation_agent/ci/runner.py:27) — trims large captured output
- [`run_tests()`](src/pr_validation_agent/ci/runner.py:35) — runs the configured unit-test command
- [`run_setup()`](src/pr_validation_agent/ci/runner.py:67) — runs configured setup commands
- [`merge_base_into_head()`](src/pr_validation_agent/ci/runner.py:114) — merges base into PR head in CI
- [`validate()`](src/pr_validation_agent/ci/runner.py:153) — full validation flow

Current behavior is intentionally simple:

- merge conflict -> fail
- setup failure -> fail
- unit test failure -> fail
- all checks pass -> success

## Configuration

Example config is in [`configs/pr-validation.example.yml`](configs/pr-validation.example.yml).

Main settings:

- [`status.context`](configs/pr-validation.example.yml:4) defines the GitHub status check name
- [`tests.command`](configs/pr-validation.example.yml:8) defines the unit-test command
- [`tests.timeout_seconds`](configs/pr-validation.example.yml:9) controls test timeout
- [`setup.commands`](configs/pr-validation.example.yml:14) defines repository setup commands
- [`labels.*`](configs/pr-validation.example.yml:23) controls optional PR labels
- [`comments.marker`](configs/pr-validation.example.yml:37) controls the maintained PR comment marker

## Branch protection setup

To make this enforceable in any repository or organization:

1. enable the workflow in the target repository
2. configure branch protection for the target branch pattern
3. mark the validation check name as required
4. optionally require reviewer approval in GitHub

Once that is done:

- red check -> merge blocked
- green check -> merge allowed, subject to your approval rules

## Testing

The remaining unit tests are under [`tests`](tests/test_comments.py).

The current validation command used locally is:

- [`uv run pytest ./tests`](pyproject.toml:23)

## Unwanted files removed

The repository cleanup removed redundant or unwanted items such as:

- [`REPO_STRUCTURE_README.md`](REPO_STRUCTURE_README.md)
- [`SRC_README.md`](SRC_README.md)
- [`.DS_Store`](.gitignore)
- [`.env`](.env)

The local [`.env`](.env) file previously contained secrets and should not be kept in the repository. The ignore rule in [`.gitignore`](.gitignore:8) already prevents future commits of that file.

## Summary

This repository is now focused on a clean GitHub-native PR validation model:

- GitHub workflow starts on PR activity
- latest base branch is merged into the PR in CI
- setup and tests run
- GitHub status becomes green or red
- branch protection decides merge availability
- documentation is consolidated into a single [`README.md`](README.md)
