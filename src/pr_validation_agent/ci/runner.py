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
        cwd: Current working directory (repo root - where source code lives)
        test_dir: Optional custom test directory (for test selection)
                  When provided, pytest will ONLY discover tests from this directory
    
    Returns:
        TestRunResult with execution details
    """
    started = time.monotonic()
    
    # Build test command with proper isolation
    if test_dir:
        # CRITICAL: Ensure pytest ONLY discovers tests from test_dir
        # Strategy:
        # 1. Use absolute path to test directory
        # 2. Set --rootdir to test directory to prevent upward discovery
        # 3. Run pytest from repo root (cwd) so imports work correctly
        # 4. This ensures: tests from test_dir, code from cwd
        
        abs_test_dir = test_dir.resolve()
        
        # Extract base pytest command (remove any existing paths)
        base_command = config.tests.command
        # Remove common test paths from command
        for pattern in ["tests/", "test/", "tests", "test"]:
            base_command = base_command.replace(pattern, "").strip()
        
        # Build isolated test command
        # --rootdir: Sets pytest's root directory (prevents discovery outside test_dir)
        # -v: Verbose output to see which tests are actually running
        # The test directory path must come AFTER pytest command but BEFORE other flags
        if "pytest" in base_command:
            # Insert test directory and rootdir right after pytest command
            parts = base_command.split()
            pytest_idx = next(i for i, p in enumerate(parts) if "pytest" in p)
            # Reconstruct: [before pytest] pytest [test_dir] --rootdir=[test_dir] [other flags]
            test_command = " ".join(parts[:pytest_idx+1]) + \
                          f" {abs_test_dir} --rootdir={abs_test_dir} -v " + \
                          " ".join(parts[pytest_idx+1:])
        else:
            # Non-pytest command, just append directory
            test_command = f"{base_command} {abs_test_dir}"
        
        # Debug: Print the actual command being executed
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"EXECUTING TEST COMMAND:", file=sys.stderr)
        print(f"Command: {test_command}", file=sys.stderr)
        print(f"Working directory: {cwd}", file=sys.stderr)
        print(f"Test directory: {test_dir}", file=sys.stderr)
        print(f"Absolute test directory: {abs_test_dir}", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
    else:
        test_command = config.tests.command
        
        # Debug: Print the actual command being executed
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"EXECUTING TEST COMMAND:", file=sys.stderr)
        print(f"Command: {test_command}", file=sys.stderr)
        print(f"Working directory: {cwd}", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
    
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
        
        # Debug: Print test results
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"TEST RESULTS:", file=sys.stderr)
        print(f"Exit code: {exit_code}", file=sys.stderr)
        print(f"Passed: {exit_code == 0}", file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)
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
    """
    Main validation workflow implementing intelligent test selection.
    
    SECURITY FEATURE: Test Integrity Protection
    ===========================================
    This workflow prevents PRs from hiding bugs by modifying both code AND tests.
    
    How it works (Set Theory):
    1. Discover base tests (Set A) - tests from base branch
    2. Discover PR tests (Set B) - tests from PR branch
    3. Compute new tests (Set N = B - A) - tests added in PR
    4. Build final set (A ∪ N) - run base tests + new tests
    5. Prepare environment:
       - For tests in A: use BASE branch version of test file
       - For tests in N: use PR branch version of test file
    6. Run tests against PR branch source code
    
    Why this works:
    - Base tests (A) use base version → can't be modified to hide bugs
    - New tests (N) use PR version → can test new functionality
    - Even if PR deletes tests, we still run them from base
    - Even if PR modifies tests, we run original version
    
    Example Attack Scenario (PREVENTED):
    - Base: def subtract(a, b): return a - b, test: assert subtract(10, 4) == 6
    - PR: def subtract(a, b): return a * b, test: assert subtract(10, 4) == 40
    - Without protection: Test passes (40 == 40) ✓ BUG HIDDEN!
    - With protection: Test fails (40 != 6) ✗ BUG CAUGHT!
    
    Returns:
        ValidationResult with state, reason, and metadata
    """
    cwd = Path.cwd()
    config = AppConfig.load(os.getenv("PR_VALIDATION_CONFIG", ".github/pr-validation.yml"))
    github = GitHubClient.from_env()
    pr = github.load_pr_context_from_event(_load_event())

    github.set_status(pr, ValidationState.PENDING, "PR validation started", config)

    # Determine test paths from config
    test_paths = _extract_test_paths(config.tests.command)
    
    # Initialize test selector with intelligent test selection
    test_selector = TestSelector(cwd, test_paths)
    
    # ============================================================================
    # STEP 1: Discover base branch tests (Set A)
    # ============================================================================
    print("\n" + "="*60, file=sys.stderr)
    print("STEP 1: Discovering tests from base branch...", file=sys.stderr)
    print("="*60, file=sys.stderr)
    try:
        base_tests = test_selector.get_base_tests(pr.base_ref)
        print(f"✓ Found {len(base_tests)} tests in base branch (Set A)", file=sys.stderr)
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
    
    # ============================================================================
    # STEP 2: Discover PR branch tests (Set B)
    # ============================================================================
    print("\n" + "="*60, file=sys.stderr)
    print("STEP 2: Discovering tests from PR branch...", file=sys.stderr)
    print("="*60, file=sys.stderr)
    pr_tests = test_selector.get_pr_tests()
    print(f"✓ Found {len(pr_tests)} tests in PR branch (Set B)", file=sys.stderr)
    
    # ============================================================================
    # STEP 3: Compute new tests (Set N = B - A)
    # ============================================================================
    print("\n" + "="*60, file=sys.stderr)
    print("STEP 3: Computing new tests...", file=sys.stderr)
    print("="*60, file=sys.stderr)
    new_tests = test_selector.compute_new_tests(base_tests, pr_tests)
    print(f"✓ Detected {len(new_tests)} new tests in PR (Set N = B - A)", file=sys.stderr)
    
    # ============================================================================
    # STEP 4: Build final test set (A ∪ N)
    # ============================================================================
    print("\n" + "="*60, file=sys.stderr)
    print("STEP 4: Building final test set...", file=sys.stderr)
    print("="*60, file=sys.stderr)
    final_tests = test_selector.build_final_test_set(base_tests, new_tests)
    print(f"✓ Final test set: {len(final_tests)} tests (A ∪ N)", file=sys.stderr)
    
    # Log test selection details for transparency
    if new_tests:
        print("\nNew tests in PR (Set N):", file=sys.stderr)
        for test in sorted(new_tests, key=str):
            print(f"  + {test}", file=sys.stderr)
    
    # Check for deleted/modified tests
    modified_tests = pr_tests & base_tests
    if len(modified_tests) < len(base_tests):
        deleted_count = len(base_tests) - len(modified_tests)
        print(f"\n⚠️  Note: {deleted_count} base test(s) were deleted in PR but will still run from base branch", file=sys.stderr)
    
    # ============================================================================
    # STEP 5: Prepare test environment with correct test files
    # ============================================================================
    print("\n" + "="*60, file=sys.stderr)
    print("STEP 5: Preparing test environment...", file=sys.stderr)
    print("="*60, file=sys.stderr)
    try:
        test_dir = test_selector.prepare_test_environment(pr.base_ref, final_tests, base_tests)
        print(f"✓ Test directory prepared: {test_dir}", file=sys.stderr)
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
    
    # ============================================================================
    # STEP 6: Run setup commands (if configured)
    # ============================================================================
    print("\n" + "="*60, file=sys.stderr)
    print("STEP 6: Running setup commands...", file=sys.stderr)
    print("="*60, file=sys.stderr)
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

    # ============================================================================
    # STEP 7: Run tests with prepared test directory
    # ============================================================================
    # CRITICAL: Tests run from temp directory (isolated test files)
    #           but against source code from cwd (PR branch code)
    # This ensures: base test expectations vs PR code behavior
    print("\n" + "="*60, file=sys.stderr)
    print("STEP 7: Running tests...", file=sys.stderr)
    print("="*60, file=sys.stderr)
    print(f"Running {len(final_tests)} tests from isolated directory", file=sys.stderr)
    print(f"Tests: {test_dir}", file=sys.stderr)
    print(f"Code: {cwd}", file=sys.stderr)
    test_result = run_tests(config, cwd, test_dir)
    
    # Cleanup temp directory (best effort)
    import shutil
    try:
        shutil.rmtree(test_dir)
        print(f"✓ Cleaned up temp directory", file=sys.stderr)
    except Exception:
        pass  # Non-critical, temp dir will be cleaned by OS eventually
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
