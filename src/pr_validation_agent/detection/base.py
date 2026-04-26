from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from pr_validation_agent.models import FunctionSymbol


@dataclass(frozen=True)
class SourceSnapshot:
    relative_path: str
    content: str


class FunctionDetector(ABC):
    language: str
    extensions: tuple[str, ...]

    @abstractmethod
    def extract(self, snapshot: SourceSnapshot) -> list[FunctionSymbol]:
        """Extract functions and methods from one source snapshot."""

    def supports(self, path: str | Path) -> bool:
        return Path(path).suffix in self.extensions
