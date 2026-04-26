from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from pr_validation_agent.comments import (
    render_merge_conflict_comment,
    render_missing_tests_comment,
    render_success_comment,
    render_test_failure_comment,
)
from pr_validation_agent.config import AppConfig
from pr_validation_agent.detection.git_diff import changed_files, detect_function_changes, diff_excerpt
from pr_validation_agent.detection.registry import build_detectors
from pr_validation_agent.detection.test_matcher import evaluate_new_function_tests
from pr_validation_agent.github import GitHubClient, GitHubError
from pr_validation_agent.langgraph_client import LangGraphClient
from pr_validation_agent.models import (
    AnalysisRequest,
    AnalysisResponse,
    PullRequestContext,
    TestRunResult,
    ValidationState,
)


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


def run_tests(config: AppConfig, cwd: Path) -> TestRunResult:
    started = time.monotonic()
    try:
        result = subprocess.run(
            config.tests.command,
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


def run_code_review(config: AppConfig, cwd: Path) -> TestRunResult | None:
    if not config.code_review.enabled or not config.code_review.command:
        return None
    started = time.monotonic()
    try:
        result = subprocess.run(
            config.code_review.command,
            cwd=cwd,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=config.code_review.timeout_seconds,
        )
        stdout, stderr = _truncate_log(
            result.stdout,
            result.stderr,
            config.code_review.log_max_bytes,
        )
        exit_code = result.returncode
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = f"Code review command timed out after {config.code_review.timeout_seconds}s"
    return TestRunResult(
        command=config.code_review.command,
        exit_code=exit_code,
        passed=exit_code == 0,
        duration_seconds=round(time.monotonic() - started, 3),
        stdout=stdout,
        stderr=stderr,
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


def _analysis_request(
    *,
    pr: PullRequestContext,
    files: list[str],
    new_functions,
    modified_functions,
    test_result: TestRunResult | None,
    coverage_findings,
    diff_text: str,
) -> AnalysisRequest:
    log_excerpt = ""
    if test_result:
        log_excerpt = f"{test_result.stdout}\n{test_result.stderr}"
    return AnalysisRequest(
        pr=pr,
        files_changed=files,
        new_functions=new_functions,
        modified_functions=modified_functions,
        test_result=test_result,
        coverage_findings=coverage_findings,
        diff_excerpt=diff_text,
        log_excerpt=log_excerpt,
    )


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


def validate() -> int:
    cwd = Path.cwd()
    config = AppConfig.load(os.getenv("PR_VALIDATION_CONFIG", ".github/pr-validation.yml"))
    github = GitHubClient.from_env()
    langgraph = LangGraphClient()
    pr = github.load_pr_context_from_event(_load_event())

    github.set_status(pr, ValidationState.PENDING, "PR validation started", config)

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
        return 1

    base_ref = f"origin/{pr.base_ref}"
    files = changed_files(cwd, base_ref)
    diff_text = diff_excerpt(cwd, base_ref)
    detectors = build_detectors(config)
    function_changes = detect_function_changes(
        cwd=cwd,
        base_ref=base_ref,
        head_ref="HEAD",
        files=files,
        detectors=detectors,
        config=config,
    )
    new_functions = [change.symbol for change in function_changes if change.change_type == "new"]
    modified_functions = [
        change.symbol for change in function_changes if change.change_type == "modified"
    ]

    setup_result = run_setup(config, cwd)
    if setup_result is not None and not setup_result.passed:
        request = _analysis_request(
            pr=pr,
            files=files,
            new_functions=new_functions,
            modified_functions=modified_functions,
            test_result=setup_result,
            coverage_findings=[],
            diff_text=diff_text,
        )
        analysis = langgraph.analyze(request, "failure")
        body = render_test_failure_comment(
            marker=config.comments.marker,
            author=pr.author,
            test_result=setup_result,
            analysis=analysis,
        )
        github.upsert_comment(pr, config.comments.marker, body)
        _apply_outcome_label(github, pr, config, config.labels.test_failed)
        github.set_status(pr, ValidationState.FAILURE, "Repository setup failed", config)
        return 1

    test_result = run_tests(config, cwd)
    if not test_result.passed:
        request = _analysis_request(
            pr=pr,
            files=files,
            new_functions=new_functions,
            modified_functions=modified_functions,
            test_result=test_result,
            coverage_findings=[],
            diff_text=diff_text,
        )
        analysis = langgraph.analyze(request, "failure")
        body = render_test_failure_comment(
            marker=config.comments.marker,
            author=pr.author,
            test_result=test_result,
            analysis=analysis,
        )
        github.upsert_comment(pr, config.comments.marker, body)
        _apply_outcome_label(github, pr, config, config.labels.test_failed)
        github.set_status(pr, ValidationState.FAILURE, "Tests failed", config)
        return 1

    coverage = evaluate_new_function_tests(
        cwd=cwd,
        files_changed=files,
        new_functions=new_functions,
        config=config,
    )
    if not coverage.passed:
        request = _analysis_request(
            pr=pr,
            files=files,
            new_functions=new_functions,
            modified_functions=modified_functions,
            test_result=test_result,
            coverage_findings=coverage.findings,
            diff_text=diff_text,
        )
        analysis = (
            langgraph.analyze(request, "coverage")
            if config.test_detection.allow_llm_coverage_review
            else AnalysisResponse()
        )
        body = render_missing_tests_comment(
            marker=config.comments.marker,
            author=pr.author,
            findings=[finding for finding in coverage.findings if not finding.has_test],
            analysis=analysis,
        )
        github.upsert_comment(pr, config.comments.marker, body)
        _apply_outcome_label(github, pr, config, config.labels.needs_tests)
        github.set_status(pr, ValidationState.FAILURE, "Missing unit tests for new functions", config)
        return 1

    request = _analysis_request(
        pr=pr,
        files=files,
        new_functions=new_functions,
        modified_functions=modified_functions,
        test_result=test_result,
        coverage_findings=coverage.findings,
        diff_text=diff_text,
    )
    analysis = langgraph.analyze(request, "summary")
    code_review_result = run_code_review(config, cwd)
    body = render_success_comment(
        marker=config.comments.marker,
        files_changed=files,
        new_functions=new_functions,
        modified_functions=modified_functions,
        analysis=analysis,
        code_review_result=code_review_result,
    )
    github.upsert_comment(pr, config.comments.marker, body)
    _apply_outcome_label(github, pr, config, config.labels.ready_for_review)
    github.request_reviewers(pr, config)
    _enable_auto_merge(github, pr, config)
    github.set_status(pr, ValidationState.SUCCESS, "All checks passed. Ready for review.", config)
    return 0


def main() -> None:
    try:
        raise SystemExit(validate())
    except GitHubError as exc:
        print(f"GitHub integration failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except Exception as exc:
        print(f"PR validation failed unexpectedly: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
