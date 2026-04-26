from __future__ import annotations

import fnmatch
from pathlib import Path

from pr_validation_agent.config import AppConfig
from pr_validation_agent.models import CoverageResult, FunctionSymbol, TestCoverageFinding


def _is_test_file(path: str, patterns: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _candidate_test_files(cwd: Path, files_changed: list[str], config: AppConfig) -> list[Path]:
    patterns = config.test_detection.test_file_patterns
    candidates = []
    for relative in files_changed:
        if _is_test_file(relative, patterns):
            path = cwd / relative
            if path.exists() and path.is_file():
                candidates.append(path)
    return candidates


def evaluate_new_function_tests(
    *,
    cwd: Path,
    files_changed: list[str],
    new_functions: list[FunctionSymbol],
    config: AppConfig,
) -> CoverageResult:
    if not new_functions:
        return CoverageResult(passed=True, findings=[])
    test_files = _candidate_test_files(cwd, files_changed, config)
    test_contents = {path: _read_text(path) for path in test_files}
    findings: list[TestCoverageFinding] = []
    for symbol in new_functions:
        evidence: list[str] = []
        if not test_files:
            findings.append(
                TestCoverageFinding(
                    symbol=symbol,
                    has_test=False,
                    suggested_tests=[f"Add a unit test covering `{symbol.qualified_name}`."],
                )
            )
            continue
        for path, content in test_contents.items():
            if not config.test_detection.require_symbol_reference or symbol.name in content:
                evidence.append(str(path.relative_to(cwd)))
        findings.append(
            TestCoverageFinding(
                symbol=symbol,
                has_test=bool(evidence),
                evidence=evidence,
                suggested_tests=[]
                if evidence
                else [f"Add a focused unit test that imports and exercises `{symbol.qualified_name}`."],
            )
        )
    return CoverageResult(
        passed=all(finding.has_test for finding in findings),
        findings=findings,
    )
