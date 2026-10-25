from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, List


def _remove_tmp(path: Path) -> None:
    path.unlink(missing_ok=True)


class CsvPartSink:
    """Idempotent, atomic per-batch CSV sink.

    Output for batch N always goes to ``part-<N>.csv``; the file appears only
    through an atomic rename, so a failed write leaves nothing behind and a
    repeated write replaces (never duplicates) the batch.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def part_path(self, batch_id: int) -> Path:
        return self.directory / f"part-{batch_id:08d}.csv"

    def _write_tmp(self, tmp: Path, rows: List[Dict[str, Any]]) -> None:
        with open(tmp, "w", newline="", encoding="utf-8") as handle:
            if rows:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())

    def write(self, batch_id: int, rows: List[Dict[str, Any]]) -> None:
        final = self.part_path(batch_id)
        tmp = final.with_name(final.name + ".tmp")
        try:
            self._write_tmp(tmp, rows)
            os.replace(tmp, final)
        except BaseException:
            _remove_tmp(tmp)
            raise


def write_dead_letters(directory: Path, batch_id: int, rejects: List[Dict[str, Any]]) -> None:
    """Atomically write the dead-letter records of one batch as JSON lines."""
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / f"batch-{batch_id:08d}.jsonl"
    tmp = final.with_name(final.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            for reject in rejects:
                handle.write(json.dumps(reject, sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, final)
    except BaseException:
        _remove_tmp(tmp)
        raise
