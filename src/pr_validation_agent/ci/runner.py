from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from pr_validation_agent.comments import (
    render_merge_conflict_comment,
    render_success_comment,
    render_test_failure_comment,
)
from pr_validation_agent.config import AppConfig
from pr_validation_agent.github import GitHubClient, GitHubError
from pr_validation_agent.models import PullRequestContext, TestRunResult, ValidationResult, ValidationState
from pr_validation_agent.test_selector import TestSelector


def _load_event() -> dict:
    event_path = os.getenv("GITHUB_EVENT_PATH")
    if not event_path:
        raise RuntimeError("GITHUB_EVENT_PATH is required in GitHub Actions")
    return json.loads(Path(event_path).read_text(encoding="utf-8"))


def _truncate_log(stdout: str, stderr: str, max_bytes: int) -> tuple[str, str]:
    combined = f"{stdout}\n{stderr}"
    if len(combined.encode("utf-8")) <= max_bytes:
        return stdout, stderr
    truncated = combined.encode("utf-8")[-max_bytes:].decode("utf-8", errors="ignore")
    return truncated, ""


def _extract_test_paths(test_command: str) -> list[str]:
    """
    Extract test directory paths from test command.
    
    Args:
        test_command: Test command string (e.g., "pytest tests/")
    
    Returns:
        List of test directory paths
    """
    test_paths = []
    
    # Extract paths from command
    if "pytest" in test_command:
        parts = test_command.split()
        for part in parts:
            if not part.startswith("-") and part not in ["pytest", "uv", "run", "-q", "--maxfail=1"]:
                if "/" in part or part in ["tests", "test"]:
                    test_paths.append(part if part.endswith("/") else part + "/")
    
    # Default to common test directories if not found
    if not test_paths:
        test_paths = ["tests/", "test/"]
    
    return test_paths


def run_tests(config: AppConfig, cwd: Path, test_dir: Path | None = None) -> TestRunResult:
    """
    Run tests with optional custom test directory.
    
    Args:
        config: Application configuration
        cwd: Current working directory
        test_dir: Optional custom test directory (for test selection)
    
    Returns:
        TestRunResult with execution details
    """
    started = time.monotonic()
    
    # Build test command
    if test_dir:
        # Run tests from custom directory
        test_command = config.tests.command.replace("tests/", str(test_dir) + "/")
        test_command = test_command.replace("test/", str(test_dir) + "/")
        # If no path in command, append the test directory
        if "tests" not in test_command and "test" not in test_command:
            test_command = f"{test_command} {test_dir}"
    else:
        test_command = config.tests.command
    
    try:
        result = subprocess.run(
            test_command,
            cwd=cwd,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=config.tests.timeout_seconds,
        )
        exit_code = result.returncode
        stdout, stderr = _truncate_log(result.stdout, result.stderr, config.tests.log_max_bytes)
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = f"Test command timed out after {config.tests.timeout_seconds}s"
    duration = time.monotonic() - started
    log_path = cwd / ".pr-validation-test.log"
    log_path.write_text(f"{stdout}\n{stderr}", encoding="utf-8")
    return TestRunResult(
        command=config.tests.command,
        exit_code=exit_code,
        passed=exit_code == 0,
        duration_seconds=round(duration, 3),
        log_path=str(log_path),
        stdout=stdout,
        stderr=stderr,
    )


def run_setup(config: AppConfig, cwd: Path) -> TestRunResult | None:
    if not config.setup.commands:
        return None
    started = time.monotonic()
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    for command in config.setup.commands:
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                timeout=config.setup.timeout_seconds,
            )
            stdout_parts.append(f"$ {command}\n{result.stdout}")
            stderr_parts.append(result.stderr)
        except subprocess.TimeoutExpired as exc:
            result = subprocess.CompletedProcess(command, 124)
            stdout_parts.append((exc.stdout or "") if isinstance(exc.stdout, str) else "")
            stderr_parts.append(f"Setup command timed out after {config.setup.timeout_seconds}s")
        if result.returncode != 0:
            stdout, stderr = _truncate_log(
                "\n".join(stdout_parts),
                "\n".join(stderr_parts),
                config.tests.log_max_bytes,
            )
            return TestRunResult(
                command=command,
                exit_code=result.returncode,
                passed=False,
                duration_seconds=round(time.monotonic() - started, 3),
                stdout=stdout,
                stderr=stderr,
            )
    return TestRunResult(
        command=" && ".join(config.setup.commands),
        exit_code=0,
        passed=True,
        duration_seconds=round(time.monotonic() - started, 3),
        stdout="\n".join(stdout_parts),
        stderr="\n".join(stderr_parts),
    )


def merge_base_into_head(cwd: Path, pr: PullRequestContext) -> tuple[bool, str]:
    if os.getenv("PR_VALIDATION_SKIP_MERGE", "").lower() in {"1", "true", "yes"}:
        return True, "Merge skipped by PR_VALIDATION_SKIP_MERGE."
    commands = [
        ["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"],
        ["git", "config", "user.name", "github-actions[bot]"],
        ["git", "fetch", "origin", pr.base_ref],
        ["git", "merge", "--no-edit", "--no-ff", f"origin/{pr.base_ref}"],
    ]
    output: list[str] = []
    for command in commands:
        result = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
        output.append(f"$ {' '.join(command)}")
        output.append(result.stdout)
        output.append(result.stderr)
        if result.returncode != 0:
            return False, "\n".join(output)
    return True, "\n".join(output)


def _apply_outcome_label(
    github: GitHubClient,
    pr: PullRequestContext,
    config: AppConfig,
    label: str,
) -> None:
    try:
        github.apply_outcome_label(pr, config, label)
    except GitHubError as exc:
        print(f"Label update failed: {exc}", file=sys.stderr)


def _enable_auto_merge(github: GitHubClient, pr: PullRequestContext, config: AppConfig) -> None:
    try:
        github.enable_auto_merge(pr, config)
    except GitHubError as exc:
        print(f"Auto-merge enablement failed: {exc}", file=sys.stderr)


def validate() -> ValidationResult:
    cwd = Path.cwd()
    config = AppConfig.load(os.getenv("PR_VALIDATION_CONFIG", ".github/pr-validation.yml"))
    github = GitHubClient.from_env()
    pr = github.load_pr_context_from_event(_load_event())

    github.set_status(pr, ValidationState.PENDING, "PR validation started", config)

    # Determine test paths from config
    test_paths = _extract_test_paths(config.tests.command)
    
    # Initialize test selector with intelligent test selection
    test_selector = TestSelector(cwd, test_paths)
    
    # Step 1: Get base branch tests (set A)
    print("Discovering tests from base branch...", file=sys.stderr)
    try:
        base_tests = test_selector.get_base_tests(pr.base_ref)
        print(f"Found {len(base_tests)} tests in base branch", file=sys.stderr)
    except Exception as exc:
        body = f"""{config.comments.marker}
@{pr.author} ⚠️ Failed to discover tests from base branch

Could not analyze test files from `{pr.base_ref}` branch. This is required to ensure test integrity.

Error: {exc}
"""
        github.upsert_comment(pr, config.comments.marker, body)
        github.set_status(pr, ValidationState.ERROR, "Failed to discover base tests", config)
        return ValidationResult(
            state=ValidationState.ERROR,
            reason="Failed to discover base tests",
            phase="setup",
            notify_users=[f"@{pr.author}"],
        )
    
    # Step 2: Get PR branch tests (set B)
    print("Discovering tests from PR branch...", file=sys.stderr)
    pr_tests = test_selector.get_pr_tests()
    print(f"Found {len(pr_tests)} tests in PR branch", file=sys.stderr)
    
    # Step 3: Compute new tests (N = B - A)
    new_tests = test_selector.compute_new_tests(base_tests, pr_tests)
    print(f"Detected {len(new_tests)} new tests in PR", file=sys.stderr)
    
    # Step 4: Build final test set (A ∪ N)
    final_tests = test_selector.build_final_test_set(base_tests, new_tests)
    print(f"Final test set: {len(final_tests)} tests", file=sys.stderr)
    
    # Log test selection details
    if new_tests:
        print("\nNew tests in PR:", file=sys.stderr)
        for test in sorted(new_tests, key=str):
            print(f"  + {test}", file=sys.stderr)
    
    modified_tests = pr_tests & base_tests
    if len(modified_tests) < len(base_tests):
        deleted_count = len(base_tests) - len(modified_tests)
        print(f"\nNote: {deleted_count} base tests were deleted/modified in PR but will still run", file=sys.stderr)
    
    # Step 5: Prepare test environment with correct test files
    print("\nPreparing test environment...", file=sys.stderr)
    try:
        test_dir = test_selector.prepare_test_environment(pr.base_ref, final_tests)
        print(f"Test directory prepared: {test_dir}", file=sys.stderr)
    except Exception as exc:
        body = f"""{config.comments.marker}
@{pr.author} ⚠️ Failed to prepare test environment

Could not prepare test files for execution.

Error: {exc}
"""
        github.upsert_comment(pr, config.comments.marker, body)
        github.set_status(pr, ValidationState.ERROR, "Failed to prepare tests", config)
        return ValidationResult(
            state=ValidationState.ERROR,
            reason="Failed to prepare test environment",
            phase="setup",
            notify_users=[f"@{pr.author}"],
        )
    
    # Run setup and tests on PR branch (with selected tests)
    setup_result = run_setup(config, cwd)
    if setup_result is not None and not setup_result.passed:
        body = render_test_failure_comment(
            marker=config.comments.marker,
            author=pr.author,
            test_result=setup_result,
            phase="setup",
            new_tests=new_tests if new_tests else None,
        )
        github.upsert_comment(pr, config.comments.marker, body)
        _apply_outcome_label(github, pr, config, config.labels.test_failed)
        github.set_status(pr, ValidationState.FAILURE, "Repository setup failed", config)
        return ValidationResult(
            state=ValidationState.FAILURE,
            reason="Repository setup failed",
            phase="setup",
            outcome_label=config.labels.test_failed,
            notify_users=[f"@{pr.author}"],
            test_result=setup_result,
        )

    # Run tests with the prepared test directory
    print(f"\nRunning {len(final_tests)} tests...", file=sys.stderr)
    test_result = run_tests(config, cwd, test_dir)
    
    # Cleanup temp directory
    import shutil
    try:
        shutil.rmtree(test_dir)
    except Exception:
        pass  # Best effort cleanup
    if not test_result.passed:
        body = render_test_failure_comment(
            marker=config.comments.marker,
            author=pr.author,
            test_result=test_result,
            phase="test",
            new_tests=new_tests if new_tests else None,
        )
        github.upsert_comment(pr, config.comments.marker, body)
        _apply_outcome_label(github, pr, config, config.labels.test_failed)
        github.set_status(pr, ValidationState.FAILURE, "Tests failed", config)
        return ValidationResult(
            state=ValidationState.FAILURE,
            reason="Tests failed",
            phase="tests",
            outcome_label=config.labels.test_failed,
            notify_users=[f"@{pr.author}"],
            test_result=test_result,
        )

    # Only merge base branch after tests pass
    merged, merge_log = merge_base_into_head(cwd, pr)
    if not merged:
        body = render_merge_conflict_comment(
            marker=config.comments.marker,
            author=pr.author,
            base_ref=pr.base_ref,
            merge_log=merge_log,
        )
        github.upsert_comment(pr, config.comments.marker, body)
        _apply_outcome_label(github, pr, config, config.labels.merge_conflict)
        github.set_status(pr, ValidationState.FAILURE, "Base branch merge failed", config)
        return ValidationResult(
            state=ValidationState.FAILURE,
            reason="Base branch merge failed",
            phase="merge",
            outcome_label=config.labels.merge_conflict,
            notify_users=[f"@{pr.author}"],
        )

    body = render_success_comment(
        marker=config.comments.marker,
        base_test_count=len(base_tests),
        new_tests=new_tests if new_tests else None,
    )
    github.upsert_comment(pr, config.comments.marker, body)
    _apply_outcome_label(github, pr, config, config.labels.ready_for_review)
    github.set_status(pr, ValidationState.SUCCESS, "All checks passed. Ready for review.", config)
    return ValidationResult(
        state=ValidationState.SUCCESS,
        reason="All checks passed. Ready for review.",
        phase="tests",
        outcome_label=config.labels.ready_for_review,
    )


def main() -> None:
    try:
        result = validate()
        raise SystemExit(0 if result.state == ValidationState.SUCCESS else 1)
    except GitHubError as exc:
        print(f"GitHub integration failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except Exception as exc:
        print(f"PR validation failed unexpectedly: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
