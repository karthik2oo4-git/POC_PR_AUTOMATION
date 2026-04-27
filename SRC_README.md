# Source Code Guide for [`src/pr_validation_agent`](src/pr_validation_agent/__init__.py)

This document explains the implementation under [`src/pr_validation_agent`](src/pr_validation_agent/__init__.py) after the simplification to GitHub-native setup and unit-test gating.

## Big picture

The source package now centers on a simple validation model:

1. load pull request context from GitHub
2. merge the latest base branch into the PR head in CI
3. run repository setup commands
4. run unit tests
5. publish GitHub-native pass/fail status
6. optionally maintain one PR comment and outcome labels

The most important execution path is in [`validate()`](src/pr_validation_agent/ci/runner.py:157).

## Package layout

Main source areas:

- [`src/pr_validation_agent/models.py`](src/pr_validation_agent/models.py)
- [`src/pr_validation_agent/config.py`](src/pr_validation_agent/config.py)
- [`src/pr_validation_agent/comments.py`](src/pr_validation_agent/comments.py)
- [`src/pr_validation_agent/github.py`](src/pr_validation_agent/github.py)
- [`src/pr_validation_agent/ci/runner.py`](src/pr_validation_agent/ci/runner.py)

The package has been cleaned down to the GitHub-native validation path only.

## [`src/pr_validation_agent/models.py`](src/pr_validation_agent/models.py)

This file contains the shared data models used by the validator.

Important models:

### [`ValidationState`](src/pr_validation_agent/models.py:9)

Represents commit status values sent to GitHub:

- `success`
- `failure`
- `error`
- `pending`

### [`TestRunResult`](src/pr_validation_agent/models.py:16)

This is one of the most important models in the current design.

It stores the result of a setup or test command:

- command
- exit code
- passed
- duration
- log path
- stdout
- stderr

### [`PullRequestContext`](src/pr_validation_agent/models.py:26)

Represents PR metadata extracted from the GitHub event payload, including:

- owner
- repo
- PR number
- author
- head SHA
- base SHA
- head ref
- base ref
- PR URL
- requested reviewers
- requested teams

### [`ValidationResult`](src/pr_validation_agent/models.py:41)

Represents the final result returned by the validator.

Current core fields:

- state
- reason
- phase
- outcome label
- users to notify
- test result

## [`src/pr_validation_agent/config.py`](src/pr_validation_agent/config.py)

This file defines the YAML configuration schema.

Main config sections:

### [`StatusConfig`](src/pr_validation_agent/config.py:11)

Controls the commit status context name and optional target URL.

### [`TestsConfig`](src/pr_validation_agent/config.py:16)

Controls the unit-test command and timeout behavior.

### [`SetupConfig`](src/pr_validation_agent/config.py:23)

Defines commands that run before tests.

### [`ReviewersConfig`](src/pr_validation_agent/config.py:40)

Still exists, though the simplified default flow does not depend on automatic reviewer requests.

### [`LabelsConfig`](src/pr_validation_agent/config.py:46)

Controls optional labels such as failure, success, and merge conflict outcomes.

The helper [`outcome_labels()`](src/pr_validation_agent/config.py:55) returns all configured outcome labels so stale labels can be removed.

### [`CodeReviewConfig`](src/pr_validation_agent/config.py:73) and [`AutoMergeConfig`](src/pr_validation_agent/config.py:68)

These remain available in config, but they are not central to the simplified two-flow requirement.

### [`CommentsConfig`](src/pr_validation_agent/config.py:80)

Defines the PR comment marker and comment-related settings.

### [`AppConfig.load()`](src/pr_validation_agent/config.py:99)

Loads YAML from disk and returns validated configuration, or defaults if the config file does not exist.

## [`src/pr_validation_agent/comments.py`](src/pr_validation_agent/comments.py)

This file renders the managed PR comments.

### [`_format_log_excerpt()`](src/pr_validation_agent/comments.py:6)

Builds a small log excerpt from captured command output.

### [`render_test_failure_comment()`](src/pr_validation_agent/comments.py:13)

Renders the failure comment for either setup or unit-test failure.

The comment now points developers to GitHub-native troubleshooting:

- open the failed workflow run
- inspect step logs
- reproduce locally with the same command

### [`render_merge_conflict_comment()`](src/pr_validation_agent/comments.py:38)

Renders the comment used when the base branch cannot be merged into the PR branch in CI.

### [`render_success_comment()`](src/pr_validation_agent/comments.py:54)

Renders the success comment that explains all configured setup and unit-test checks passed.

## [`src/pr_validation_agent/github.py`](src/pr_validation_agent/github.py)

This file wraps GitHub API interactions.

### [`GitHubClient`](src/pr_validation_agent/github.py:19)

Main API client.

Important methods:

- [`from_env()`](src/pr_validation_agent/github.py:24) loads `GITHUB_TOKEN`
- [`load_pr_context_from_event()`](src/pr_validation_agent/github.py:45) builds [`PullRequestContext`](src/pr_validation_agent/models.py:60)
- [`set_status()`](src/pr_validation_agent/github.py:63) posts commit status for the PR head SHA
- [`upsert_comment()`](src/pr_validation_agent/github.py:81) maintains a single managed bot comment
- [`request_reviewers()`](src/pr_validation_agent/github.py:107) supports optional reviewer handling when enabled in configuration
- [`ensure_label()`](src/pr_validation_agent/github.py:122) creates labels if needed
- [`add_labels()`](src/pr_validation_agent/github.py:134) applies labels
- [`remove_label()`](src/pr_validation_agent/github.py:144) removes labels
- [`apply_outcome_label()`](src/pr_validation_agent/github.py:157) manages outcome label transitions
- [`enable_auto_merge()`](src/pr_validation_agent/github.py:168) remains available but is not required for the simplified flow

## [`src/pr_validation_agent/ci/runner.py`](src/pr_validation_agent/ci/runner.py)

This file is the main orchestration engine.

### [`_load_event()`](src/pr_validation_agent/ci/runner.py:19)

Reads the GitHub event payload from `GITHUB_EVENT_PATH`.

### [`_truncate_log()`](src/pr_validation_agent/ci/runner.py:26)

Prevents logs from becoming too large by trimming captured output.

### [`run_tests()`](src/pr_validation_agent/ci/runner.py:34)

Runs the configured unit-test command with timeout handling and output capture.

It also writes [`.pr-validation-test.log`](.gitignore:7) in the working directory for debugging.

### [`run_setup()`](src/pr_validation_agent/ci/runner.py:66)

Runs configured setup commands before the tests.

### [`merge_base_into_head()`](src/pr_validation_agent/ci/runner.py:83)

This is the function that makes the validator reflect real PR merge conditions.

It:

- configures the git user
- fetches the latest base branch from origin
- merges the base branch into the checked-out PR head

That ensures setup and unit tests run against the merged state that matters to reviewers.

### [`_apply_outcome_label()`](src/pr_validation_agent/ci/runner.py:102)

Safely applies labels without crashing the run if label updates fail.

### [`_enable_auto_merge()`](src/pr_validation_agent/ci/runner.py:114)

Still exists as an optional helper, though it is not used in the simplified success path.

### [`validate()`](src/pr_validation_agent/ci/runner.py:157)

This is the primary runtime flow.

It performs:

1. load config
2. create GitHub client
3. load PR context
4. set pending status
5. merge base into head
6. run setup
7. run tests
8. comment and label on failure if needed
9. set success or failure status
10. return [`ValidationResult`](src/pr_validation_agent/models.py:75)

Current behavior is intentionally simple:

- merge conflict -> fail
- setup failure -> fail
- unit test failure -> fail
- all checks pass -> success

## Summary

The main source code now supports a straightforward PR validation contract:

- GitHub workflow starts on PR activity
- latest base branch is merged into the PR in CI
- setup and tests run
- GitHub status becomes green or red
- branch protection decides merge availability