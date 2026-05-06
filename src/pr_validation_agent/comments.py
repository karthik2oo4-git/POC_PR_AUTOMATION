from __future__ import annotations

from typing import Set

from pr_validation_agent.models import TestRunResult
from pr_validation_agent.test_selector import TestIdentifier


def _format_log_excerpt(result: TestRunResult, max_lines: int = 40) -> str:
    output = f"{result.stdout}\n{result.stderr}".strip()
    if not output:
        return ""
    excerpt = "\n".join(output.splitlines()[-max_lines:])
    return f"\n```text\n{excerpt}\n```\n"


def render_test_failure_comment(
    *,
    marker: str,
    author: str,
    test_result: TestRunResult,
    phase: str = "test",
    new_tests: Set[TestIdentifier] | None = None,
) -> str:
    phase_title = "Repository setup failed" if phase == "setup" else "Unit tests failed"
    
    # Build new tests section if provided
    new_tests_section = ""
    if new_tests and len(new_tests) > 0:
        new_tests_section = "\n\n**New tests added in this PR:**\n"
        for test in sorted(new_tests, key=str):
            new_tests_section += f"- `{test}`\n"
    
    return f"""{marker}
@{author} ❌ {phase_title}

GitHub blocked this pull request because the validation workflow returned a failing status.

What to check in GitHub:
- Open the failed workflow run from the PR Checks tab
- Review the failing step logs
- Reproduce locally with `{test_result.command}`
- Push fixes to re-run validation automatically

Command: `{test_result.command}`
Exit code: `{test_result.exit_code}`
Log excerpt:
{_format_log_excerpt(test_result)}{new_tests_section}"""


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


def render_success_comment(
    *,
    marker: str,
    base_test_count: int = 0,
    new_tests: Set[TestIdentifier] | None = None,
) -> str:
    # Build test summary
    test_summary = ""
    if base_test_count > 0:
        test_summary = f"\n\n**Test Summary:**\n- Base branch tests: {base_test_count}"
        
        if new_tests and len(new_tests) > 0:
            test_summary += f"\n- New tests in PR: {len(new_tests)}"
            test_summary += f"\n- Total tests executed: {base_test_count + len(new_tests)}"
            
            test_summary += "\n\n**New tests added in this PR:**\n"
            for test in sorted(new_tests, key=str):
                test_summary += f"- `{test}`\n"
        else:
            test_summary += f"\n- Total tests executed: {base_test_count}"
            test_summary += "\n- No new tests added in this PR"
    
    return f"""{marker}
✅ All configured setup and unit-test checks passed.

GitHub can now allow merge when this workflow is marked as a required status check in branch protection.{test_summary}
"""
