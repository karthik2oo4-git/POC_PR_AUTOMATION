from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True, slots=True)
class LanguageRule:
    language: str
    source_roots: tuple[str, ...]
    test_patterns: tuple[str, ...]


RULES: dict[str, LanguageRule] = {
    ".py": LanguageRule(
        language="python",
        source_roots=("src",),
        test_patterns=("tests/**/{module_path}/test_{stem}.py", "tests/**/{module_path}/{stem}_test.py"),
    ),
    ".ts": LanguageRule(
        language="typescript",
        source_roots=("src",),
        test_patterns=("tests/**/{module_path}/{stem}.test.ts", "tests/**/{module_path}/{stem}.spec.ts"),
    ),
    ".js": LanguageRule(
        language="javascript",
        source_roots=("src",),
        test_patterns=("tests/**/{module_path}/{stem}.test.js", "tests/**/{module_path}/{stem}.spec.js"),
    ),
    ".java": LanguageRule(
        language="java",
        source_roots=("src/main/java",),
        test_patterns=("src/test/java/**/{stem}Test.java",),
    ),
    ".go": LanguageRule(
        language="go",
        source_roots=("pkg",),
        test_patterns=("{parent}/{stem}_test.go",),
    ),
    ".kt": LanguageRule(
        language="kotlin",
        source_roots=("src/main/kotlin",),
        test_patterns=("src/test/kotlin/**/{stem}Test.kt",),
    ),
    ".cs": LanguageRule(
        language="csharp",
        source_roots=("Services", "src"),
        test_patterns=("Tests/**/{stem}Tests.cs",),
    ),
}


def is_generated_or_ignored(path: str) -> bool:
    ignored_prefixes = ("dist/", "build/", "generated/", ".github/")
    ignored_names = ("Dockerfile",)
    return path.startswith(ignored_prefixes) or path in ignored_names or path.endswith((".md", ".yaml", ".yml", ".tf"))


def is_test_file(path: str) -> bool:
    return "/tests/" in f"/{path}" or path.startswith("tests/") or path.endswith(
        ("_test.py", ".test.ts", ".spec.ts", ".test.js", ".spec.js", "_test.go", "Test.java", "Test.kt", "Tests.cs")
    )


def expected_test_patterns(path: str) -> list[str]:
    source_path = PurePosixPath(path)
    rule = RULES.get(source_path.suffix)
    if rule is None or is_generated_or_ignored(path) or is_test_file(path):
        return []

    relative_parts = source_path.parts
    for root in rule.source_roots:
        root_parts = PurePosixPath(root).parts
        if relative_parts[: len(root_parts)] == root_parts:
            module_parts = relative_parts[len(root_parts) : -1]
            module_path = "/".join(module_parts)
            parent = str(source_path.parent)
            stem = source_path.stem
            return [
                pattern.format(module_path=module_path, stem=stem, parent=parent).replace("//", "/")
                for pattern in rule.test_patterns
            ]
    return []

# Made with Bob
