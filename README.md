# PR Validation Agent

A reusable GitHub pull request validation system focused on one job: run setup plus unit tests on pull requests and let GitHub branch protection decide whether merge is allowed.

## What this project does

This repository provides a portable PR validation flow that works across repositories and organizations:

- a pull request is opened, synchronized, reopened, or marked ready for review
- GitHub Actions starts automatically
- the workflow checks out the PR head commit
- the validator merges the latest base branch into the PR branch inside CI
- repository setup commands run
- unit tests run
- if setup or tests fail, the workflow fails and merge stays blocked
- if setup and tests pass, the workflow succeeds and merge can be allowed by branch protection

This directly matches the two required flows:

1. PR raised -> GitHub workflow starts -> unit tests run -> all tests pass -> allow merge
2. PR raised -> GitHub workflow starts -> unit tests run -> any test fails -> GitHub shows failed checks/logs and merge is blocked

## Why this is enough

GitHub already provides the important native behavior needed for this use case:

- failed workflows show red status on the PR
- required status checks block the merge button
- Actions logs show which step failed
- rerunning happens automatically when new commits are pushed
- branch protection makes the rule enforceable for teams and organizations

Because of that, this project no longer depends on LLM-generated analysis for merge decisions.

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

## Core flow

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

- installs [`uv`](action.yml:22)
- installs Python with [`uv python install`](action.yml:30)
- syncs the validator environment with [`uv sync --frozen --no-dev`](action.yml:35)
- runs the CLI entrypoint [`pr-validation-ci`](action.yml:40)

### 3. PR context and GitHub status

The validator entrypoint is [`validate()`](src/pr_validation_agent/ci/runner.py:157).

It:

- loads config through [`AppConfig.load()`](src/pr_validation_agent/config.py:99)
- loads PR event payload through [`_load_event()`](src/pr_validation_agent/ci/runner.py:19)
- builds a GitHub client through [`GitHubClient.from_env()`](src/pr_validation_agent/github.py:24)
- reads PR metadata through [`load_pr_context_from_event()`](src/pr_validation_agent/github.py:45)
- sets a pending commit status through [`set_status()`](src/pr_validation_agent/github.py:63)

### 4. Merge base branch into PR head in CI

The key behavior is implemented in [`merge_base_into_head()`](src/pr_validation_agent/ci/runner.py:83).

It runs:

- [`git fetch origin <base_ref>`](src/pr_validation_agent/ci/runner.py:89)
- [`git merge --no-edit --no-ff origin/<base_ref>`](src/pr_validation_agent/ci/runner.py:90)

This ensures the tests run against the PR branch in merged CI state, not in isolation.

If that merge fails:

- [`render_merge_conflict_comment()`](src/pr_validation_agent/comments.py:38) creates the PR comment
- [`upsert_comment()`](src/pr_validation_agent/github.py:81) updates a single managed bot comment
- [`apply_outcome_label()`](src/pr_validation_agent/github.py:157) applies the merge-conflict label
- [`set_status()`](src/pr_validation_agent/github.py:63) marks the validation as failed

### 5. Setup and unit tests

Repository setup commands run through [`run_setup()`](src/pr_validation_agent/ci/runner.py:66).

Unit tests run through [`run_tests()`](src/pr_validation_agent/ci/runner.py:34).

Both return a [`TestRunResult`](src/pr_validation_agent/models.py:38) containing:

- command
- exit code
- passed
- duration
- stdout
- stderr
- optional log path

### 6. Failure path

If setup fails or tests fail:

- [`render_test_failure_comment()`](src/pr_validation_agent/comments.py:13) updates one PR comment
- the author is mentioned
- the `test-failed` label can be applied
- commit status becomes `failure`
- GitHub branch protection keeps merge blocked

The failure comment intentionally points developers to GitHub-native tools:

- PR Checks tab
- failed workflow run
- step logs
- local reproduction using the same command

### 7. Success path

If merge succeeds, setup succeeds, and tests pass:

- [`render_success_comment()`](src/pr_validation_agent/comments.py:54) posts a success message
- the `ready-for-review` label can be applied
- commit status becomes `success`

Once this check is configured as a required status check in branch protection, GitHub can enable merge.

## What GitHub provides for failed unit tests

When unit tests fail, GitHub already gives several useful options:

- failed status on the PR
- merge button blocked when the check is required
- detailed Actions logs
- per-step failure visibility
- workflow re-run support
- commit-by-commit history of validation outcomes

This is the recommended handling model for this project.

## Configuration

Example config is in [`configs/pr-validation.example.yml`](configs/pr-validation.example.yml).

Main settings:

- [`status.context`](configs/pr-validation.example.yml:4) defines the GitHub status check name
- [`tests.command`](configs/pr-validation.example.yml:8) defines the unit-test command
- [`tests.timeout_seconds`](configs/pr-validation.example.yml:9) controls test timeout
- [`setup.commands`](configs/pr-validation.example.yml:14) defines repository setup commands
- [`labels.*`](configs/pr-validation.example.yml:24) controls optional PR labels
- [`comments.marker`](configs/pr-validation.example.yml:43) controls the maintained PR comment marker

## Repository structure

Key files:

- [`action.yml`](action.yml) — reusable composite GitHub Action
- [`.github/workflows/pr-validation.yml`](.github/workflows/pr-validation.yml) — example PR workflow
- [`configs/pr-validation.example.yml`](configs/pr-validation.example.yml) — example repository config
- [`src/pr_validation_agent/ci/runner.py`](src/pr_validation_agent/ci/runner.py) — main validation orchestration
- [`src/pr_validation_agent/github.py`](src/pr_validation_agent/github.py) — GitHub API integration
- [`src/pr_validation_agent/comments.py`](src/pr_validation_agent/comments.py) — PR comment rendering
- [`src/pr_validation_agent/config.py`](src/pr_validation_agent/config.py) — YAML config schema
- [`src/pr_validation_agent/models.py`](src/pr_validation_agent/models.py) — shared models

## Branch protection setup

To make this enforceable in any repository or organization:

1. enable the workflow in the target repository
2. configure branch protection for the target branch pattern
3. mark the validation check name as required
4. optionally require reviewer approval in GitHub

Once that is done:

- red check -> merge blocked
- green check -> merge allowed, subject to your approval rules

## Summary

This project is now centered on GitHub-native PR gating:

- merge decisions come from setup/test pass or fail
- GitHub branch protection is the enforcement layer
- no LLM output is required for merge control
- the design stays reusable across teams and organizations
