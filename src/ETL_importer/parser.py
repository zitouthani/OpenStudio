from __future__ import annotations

from pathlib import Path
from typing import Dict, List


def parse_talend_files(paths: List[str]) -> Dict[str, List[str]]:
    """Parse Talend files without executing external code."""
    parsed: Dict[str, List[str]] = {}
    for raw_path in paths:
        path = Path(raw_path)
        parsed[str(path)] = [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    return parsed
