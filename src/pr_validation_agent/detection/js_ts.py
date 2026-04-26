from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from pr_validation_agent.detection.base import FunctionDetector, SourceSnapshot
from pr_validation_agent.models import FunctionKind, FunctionSymbol


class JavaScriptTypeScriptFunctionDetector(FunctionDetector):
    language = "javascript"
    extensions = (".js", ".jsx", ".ts", ".tsx")

    def extract(self, snapshot: SourceSnapshot) -> list[FunctionSymbol]:
        script_path = Path(__file__).with_name("parse_js_ts.mjs")
        with tempfile.NamedTemporaryFile("w", suffix=Path(snapshot.relative_path).suffix, delete=False) as handle:
            handle.write(snapshot.content)
            temp_path = handle.name
        try:
            result = subprocess.run(
                ["node", str(script_path), temp_path, snapshot.relative_path],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        finally:
            Path(temp_path).unlink(missing_ok=True)
        if result.returncode != 0:
            return []
        try:
            raw_symbols = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []
        lines = snapshot.content.splitlines()
        symbols: list[FunctionSymbol] = []
        for item in raw_symbols:
            start_line = int(item.get("start_line", 1))
            end_line = int(item.get("end_line", start_line))
            source = "\n".join(lines[start_line - 1 : end_line])
            kind = FunctionKind.METHOD if item.get("kind") == "method" else FunctionKind.FUNCTION
            symbols.append(
                FunctionSymbol(
                    name=item["name"],
                    qualified_name=item["qualified_name"],
                    file_path=snapshot.relative_path,
                    language=self.language,
                    start_line=start_line,
                    end_line=end_line,
                    kind=kind,
                    signature=item.get("signature", ""),
                    body_hash=hashlib.sha256(source.encode("utf-8")).hexdigest(),
                )
            )
        return symbols
