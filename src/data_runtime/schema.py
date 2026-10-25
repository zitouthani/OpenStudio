from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Schema:
    """Represents a validated row schema."""

    fields: List[str] = field(default_factory=list)
    types: Dict[str, str] = field(default_factory=dict)

    def validate(self, row: Dict[str, Any]) -> None:
        missing = [field_name for field_name in self.fields if field_name not in row]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")
