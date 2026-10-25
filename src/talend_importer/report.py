from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class MigrationReport:
    """Summarize migration coverage for Talend jobs."""

    supported: List[str] = field(default_factory=list)
    unsupported: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "supported": self.supported,
            "unsupported": self.unsupported,
            "warnings": self.warnings,
        }
