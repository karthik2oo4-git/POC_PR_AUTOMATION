from __future__ import annotations

from pr_validation_agent.models import AnalysisResponse, FunctionSymbol, TestCoverageFinding, TestRunResult


def _format_symbols(symbols: list[FunctionSymbol]) -> str:
    if not symbols:
        return "- None"
    return "\n".join(
        f"- `{symbol.qualified_name}` in `{symbol.file_path}:{symbol.start_line}`"
        for symbol in symbols
    )


def _format_files(files: list[str]) -> str:
    if not files:
        return "- None"
    return "\n".join(f"- `{file_path}`" for file_path in files)


def _format_findings(findings: list[TestCoverageFinding]) -> str:
    if not findings:
        return "- None"
    return "\n".join(
        f"- `{finding.symbol.qualified_name}` in `{finding.symbol.file_path}:{finding.symbol.start_line}`"
        for finding in findings
    )


def _format_suggestions(findings: list[TestCoverageFinding]) -> str:
    suggestions: list[str] = []
    for finding in findings:
        if finding.suggested_tests:
            joined = "; ".join(finding.suggested_tests)
            suggestions.append(f"- `{finding.symbol.qualified_name}`: {joined}")
    return "\n".join(suggestions) if suggestions else "- Add tests that exercise the new public behavior."


def _format_code_review(result: TestRunResult | None) -> str:
    if result is None:
        return ""
    status = "Passed" if result.passed else f"Completed with exit code {result.exit_code}"
    output = f"{result.stdout}\n{result.stderr}".strip()
    if output:
        excerpt = "\n".join(output.splitlines()[-40:])
        details = f"\n\n```text\n{excerpt}\n```"
    else:
        details = ""
    return f"\nOptional Code Review:\n{status}{details}\n"


def render_test_failure_comment(
    *,
    marker: str,
    author: str,
    test_result: TestRunResult,
    analysis: AnalysisResponse | None,
    phase: str = "test",
) -> str:
    failure = analysis.failure_analysis if analysis else None
    failed_tests = failure.failing_tests if failure else []
    failed_tests_block = "\n".join(f"- `{test}`" for test in failed_tests) or "- See logs"
    root_cause = failure.root_cause if failure and failure.root_cause else "Unable to infer root cause."
    suggested_fix = (
        failure.suggested_fix
        if failure and failure.suggested_fix
        else "Inspect the failing tests and update the PR before requesting review."
    )
    phase_title = "Repository setup failures detected" if phase == "setup" else "Test failures detected"
    return f"""{marker}
@{author} ❌ {phase_title}

Failed Checks:
{failed_tests_block}

🤖 Analysis:
{root_cause}

💡 Suggested Fix:
{suggested_fix}

Command: `{test_result.command}`
Exit code: `{test_result.exit_code}`
"""


def render_merge_conflict_comment(*, marker: str, author: str, base_ref: str, merge_log: str) -> str:
    excerpt = "\n".join(merge_log.splitlines()[-80:])
    return f"""{marker}
@{author} ❌ Merge conflict detected

The PR branch could not merge `{base_ref}` in CI. Resolve the conflict locally, push the updated branch, and the validation will run again.

Merge output:

```text
{excerpt}
```
"""


def render_missing_tests_comment(
    *,
    marker: str,
    author: str,
    findings: list[TestCoverageFinding],
    analysis: AnalysisResponse | None,
) -> str:
    coverage_analysis = analysis.coverage_analysis if analysis else None
    analyzed_findings = coverage_analysis.missing_tests if coverage_analysis else findings
    notes = coverage_analysis.notes if coverage_analysis and coverage_analysis.notes else "Add or update tests covering the new behavior before requesting review again."
    return f"""{marker}
@{author} ❌ Missing unit tests for new functions

Newly added functions:
{_format_findings(analyzed_findings)}

💡 Suggested Test Cases:
{_format_suggestions(analyzed_findings)}

Notes:
{notes}
"""


def render_success_comment(
    *,
    marker: str,
    files_changed: list[str],
    new_functions: list[FunctionSymbol],
    modified_functions: list[FunctionSymbol],
    analysis: AnalysisResponse | None,
    code_review_result: TestRunResult | None = None,
    reviewer_mentions: list[str] | None = None,
) -> str:
    summary = analysis.summary if analysis else None
    high_level_summary = (
        summary.high_level_summary
        if summary and summary.high_level_summary
        else "This PR passed validation and is ready for human review."
    )
    risks = summary.risk_insights if summary else []
    notes = summary.notes if summary else []
    risk_block = "\n".join(f"- {risk}" for risk in risks) if risks else "- None"
    notes_block = "\n".join(f"- {note}" for note in notes) if notes else "- None"
    reviewer_block = " ".join(reviewer_mentions or [])
    reviewer_line = f"\nReviewer Notification:\n{reviewer_block}\n" if reviewer_block else ""
    return f"""{marker}
✅ All checks passed. Ready for review.
{reviewer_line}
📌 Changes in this PR:

Files Modified:
{_format_files(files_changed)}

➕ New Functions:
{_format_symbols(new_functions)}

✏️ Updated Functions:
{_format_symbols(modified_functions)}

🧠 Summary:
{high_level_summary}

⚠️ Notes:
{risk_block}

Additional Notes:
{notes_block}
{_format_code_review(code_review_result)}
"""
