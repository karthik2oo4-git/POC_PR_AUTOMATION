# Repository Structure Guide

This document explains the top-level layout of the repository after the simplification to GitHub-native pull request validation.

## Top-level view

Main items at the repository root:

- [`.github`](.github)
- [`configs`](configs/pr-validation.example.yml)
- [`src`](src/pr_validation_agent/__init__.py)
- [`tests`](tests/test_comments.py)
- [`action.yml`](action.yml)
- [`Dockerfile`](Dockerfile)
- [`pyproject.toml`](pyproject.toml)
- [`uv.lock`](uv.lock)
- [`.gitignore`](.gitignore)
- [`.python-version`](.python-version)
- [`README.md`](README.md)

How to think about them:

- [`.github`](.github) contains GitHub Actions workflow definitions
- [`action.yml`](action.yml) exposes this repository as a reusable composite action
- [`configs`](configs/pr-validation.example.yml) provides example validator configuration
- [`src`](src/pr_validation_agent/__init__.py) contains the Python implementation
- [`tests`](tests/test_comments.py) contains unit tests for the validator
- [`pyproject.toml`](pyproject.toml) defines dependencies, scripts, and tool configuration
- [`uv.lock`](uv.lock) pins dependency versions
- [`Dockerfile`](Dockerfile) remains available for packaging, though the core merge-gating path is GitHub-native
- [`README.md`](README.md) explains the end-to-end usage model

## Generated and local-only folders

Common local/generated folders:

- [`.venv`](.gitignore:1)
- [`.uv-cache`](.gitignore:2)
- [`__pycache__`](.gitignore:3)
- [`.pytest_cache`](.gitignore:5)
- [`.ruff_cache`](.gitignore:6)
- [`.pr-validation-test.log`](.gitignore:7)
- [`.env`](.gitignore:8)

These should not be committed because they are machine-generated, environment-specific, or may contain secrets.

## Understanding [`pyproject.toml`](pyproject.toml)

[`pyproject.toml`](pyproject.toml) is the main Python project definition.

Important sections:

### [`[project]`](pyproject.toml:1)

Defines metadata such as:

- [`name`](pyproject.toml:2)
- [`version`](pyproject.toml:3)
- [`description`](pyproject.toml:4)
- [`requires-python`](pyproject.toml:5)

### [`dependencies`](pyproject.toml:6)

Runtime dependencies currently include packages such as:

- [`httpx`](pyproject.toml:7) for GitHub API access
- [`pydantic`](pyproject.toml:8) for typed models
- [`pyyaml`](pyproject.toml:9) for YAML config loading

The dependency set is intentionally small because the project now focuses only on GitHub-native setup and test gating.

### [`[dependency-groups]`](pyproject.toml:18)

Development dependencies such as:

- [`pytest`](pyproject.toml:20)
- [`ruff`](pyproject.toml:21)

### [`[project.scripts]`](pyproject.toml:24)

CLI entrypoints:

- [`pr-validation-ci`](pyproject.toml:18) runs the CI validator

## Understanding [`action.yml`](action.yml)

[`action.yml`](action.yml) defines the reusable GitHub composite action.

It is the main reusable entrypoint for other repositories.

Important parts:

- [`config-path`](action.yml:4) selects the repository config file
- [`python-version`](action.yml:8) selects Python runtime
- [`uv-version`](action.yml:12) pins `uv`
- [`astral-sh/setup-uv@v7`](action.yml:20) installs `uv`
- [`uv python install`](action.yml:27) installs Python
- [`uv sync --frozen --no-dev`](action.yml:32) installs validator dependencies
- [`pr-validation-ci`](action.yml:40) launches the validation runner

The action is fully focused on GitHub-native validation and does not require any external analysis service.

## Understanding [`.github/workflows/pr-validation.yml`](.github/workflows/pr-validation.yml)

This workflow is the example PR validation workflow.

Key behavior:

- triggers on pull request lifecycle events through [`pull_request`](.github/workflows/pr-validation.yml:4)
- uses concurrency control through [`concurrency`](.github/workflows/pr-validation.yml:14)
- checks out the PR head with [`actions/checkout@v4`](.github/workflows/pr-validation.yml:26)
- calls the local action through [`uses: ./`](.github/workflows/pr-validation.yml:32)
- passes [`GITHUB_TOKEN`](.github/workflows/pr-validation.yml:39) so statuses, labels, and comments can be updated

The job name is now [`PR Unit Test Validation`](.github/workflows/pr-validation.yml:20), matching the simplified unit-test-focused behavior.

## Understanding [`configs/pr-validation.example.yml`](configs/pr-validation.example.yml)

This file shows how a consuming repository can configure the validator.

Important sections:

- [`status`](configs/pr-validation.example.yml:3) defines the GitHub status check context
- [`tests`](configs/pr-validation.example.yml:7) defines the unit-test command and timeout
- [`setup`](configs/pr-validation.example.yml:13) defines pre-test setup commands
- [`reviewers`](configs/pr-validation.example.yml:18) remains present but defaults to disabled auto-request behavior
- [`labels`](configs/pr-validation.example.yml:22) controls optional outcome labels
- [`comments`](configs/pr-validation.example.yml:41) controls the bot comment marker

Notably, the example config no longer depends on AST-based test coverage review for the main required flow.

## Why this structure is reusable across organizations

This layout is reusable because:

- repositories only need a workflow plus a config file
- GitHub Actions provides the execution layer
- branch protection provides the merge gate
- the validator remains repository-agnostic
- teams can change the setup command and test command without changing core code

That makes the solution portable for many organizations using GitHub.