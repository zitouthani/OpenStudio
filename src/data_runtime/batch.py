from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Batch:
    """A batch of rows processed together."""

    rows: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, row: Dict[str, Any]) -> None:
        self.rows.append(row)

    def clear(self) -> None:
        self.rows.clear()
