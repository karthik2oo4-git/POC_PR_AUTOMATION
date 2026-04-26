from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

from pr_validation_agent.config import AppConfig, LanguageConfig
from pr_validation_agent.detection.base import FunctionDetector, SourceSnapshot
from pr_validation_agent.models import FunctionChange, FunctionSymbol


def run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def changed_files(cwd: Path, base_ref: str, head_ref: str = "HEAD") -> list[str]:
    output = run_git(["diff", "--name-only", f"{base_ref}...{head_ref}"], cwd)
    return [line.strip() for line in output.splitlines() if line.strip()]


def diff_excerpt(cwd: Path, base_ref: str, head_ref: str = "HEAD", max_bytes: int = 80_000) -> str:
    output = run_git(["diff", "--unified=80", f"{base_ref}...{head_ref}"], cwd)
    return output[:max_bytes]


def file_at_ref(cwd: Path, git_ref: str, relative_path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{git_ref}:{relative_path}"],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""


def _matches(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _language_config(config: AppConfig, detector: FunctionDetector) -> LanguageConfig | None:
    return config.languages.get(detector.language)


def _is_included(path: str, detector: FunctionDetector, config: AppConfig) -> bool:
    lang_config = _language_config(config, detector)
    if lang_config is None:
        return detector.supports(path)
    if lang_config.include and not _matches(path, lang_config.include):
        return False
    if lang_config.exclude and _matches(path, lang_config.exclude):
        return False
    return detector.supports(path)


def _by_qualified_name(symbols: list[FunctionSymbol]) -> dict[str, FunctionSymbol]:
    return {symbol.qualified_name: symbol for symbol in symbols}


def detect_function_changes(
    *,
    cwd: Path,
    base_ref: str,
    head_ref: str,
    files: list[str],
    detectors: list[FunctionDetector],
    config: AppConfig,
) -> list[FunctionChange]:
    changes: list[FunctionChange] = []
    for file_path in files:
        detector = next(
            (candidate for candidate in detectors if _is_included(file_path, candidate, config)),
            None,
        )
        if detector is None:
            continue
        base_content = file_at_ref(cwd, base_ref, file_path)
        head_content = file_at_ref(cwd, head_ref, file_path)
        if not head_content:
            continue
        base_symbols = _by_qualified_name(
            detector.extract(SourceSnapshot(relative_path=file_path, content=base_content))
        )
        head_symbols = _by_qualified_name(
            detector.extract(SourceSnapshot(relative_path=file_path, content=head_content))
        )
        for qualified_name, head_symbol in head_symbols.items():
            base_symbol = base_symbols.get(qualified_name)
            if base_symbol is None:
                changes.append(FunctionChange(symbol=head_symbol, change_type="new"))
            elif base_symbol.body_hash != head_symbol.body_hash:
                changes.append(FunctionChange(symbol=head_symbol, change_type="modified"))
    return changes
