from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

CHECKPOINT_VERSION = 1


def atomic_write_text(path: Path, text: str) -> None:
    """Write text so readers see either the old or the new content, never a partial file."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


@dataclass
class Checkpoint:
    fingerprint: Dict[str, Any]
    last_committed_batch: int = -1
    batches: int = 0
    records_in: int = 0
    records_out: int = 0
    records_rejected: int = 0
    records_filtered: int = 0
    status: str = "running"
    version: int = CHECKPOINT_VERSION
    extra: Dict[str, Any] = field(default_factory=dict)

    def save(self, path: Path) -> None:
        atomic_write_text(path, json.dumps(asdict(self), sort_keys=True))

    @staticmethod
    def load(path: Path) -> Optional["Checkpoint"]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if data.get("version") != CHECKPOINT_VERSION:
            raise ValueError(f"Unsupported checkpoint version: {data.get('version')}")
        return Checkpoint(**data)
