from __future__ import annotations

import ast
import hashlib
from collections.abc import Iterable

from pr_validation_agent.detection.base import FunctionDetector, SourceSnapshot
from pr_validation_agent.models import FunctionKind, FunctionSymbol


class PythonFunctionDetector(FunctionDetector):
    language = "python"
    extensions = (".py",)

    def extract(self, snapshot: SourceSnapshot) -> list[FunctionSymbol]:
        try:
            tree = ast.parse(snapshot.content)
        except SyntaxError:
            return []
        lines = snapshot.content.splitlines()
        symbols: list[FunctionSymbol] = []
        self._walk(tree.body, snapshot.relative_path, lines, [], symbols)
        return symbols

    def _walk(
        self,
        nodes: Iterable[ast.stmt],
        file_path: str,
        lines: list[str],
        parents: list[str],
        symbols: list[FunctionSymbol],
    ) -> None:
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                self._walk(node.body, file_path, lines, [*parents, node.name], symbols)
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = FunctionKind.METHOD if parents else FunctionKind.FUNCTION
                qualified = ".".join([*parents, node.name])
                start_line = node.lineno
                end_line = getattr(node, "end_lineno", node.lineno)
                source = "\n".join(lines[start_line - 1 : end_line])
                symbols.append(
                    FunctionSymbol(
                        name=node.name,
                        qualified_name=qualified,
                        file_path=file_path,
                        language=self.language,
                        start_line=start_line,
                        end_line=end_line,
                        kind=kind,
                        signature=self._signature(node),
                        body_hash=hashlib.sha256(source.encode("utf-8")).hexdigest(),
                    )
                )
                nested_parents = [*parents, node.name]
                self._walk(node.body, file_path, lines, nested_parents, symbols)

    def _signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        args = [arg.arg for arg in node.args.args]
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        args.extend(arg.arg for arg in node.args.kwonlyargs)
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        return f"{prefix}def {node.name}({', '.join(args)})"
