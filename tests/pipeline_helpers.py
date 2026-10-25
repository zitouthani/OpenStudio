from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import List, Tuple


def write_input(path: Path, rows: int, pad: int = 0) -> Path:
    filler = "x" * pad
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "name", "amount"])
        for i in range(1, rows + 1):
            writer.writerow([i, f"name{i}{filler}", i % 1000])
    return path


def read_ids(path: Path) -> List[str]:
    with open(path, newline="", encoding="utf-8") as handle:
        return [row["id"] for row in csv.DictReader(handle)]


def fingerprint(path: Path) -> Tuple[int, str]:
    """Return (row count, sha256) of an output file."""
    digest = hashlib.sha256()
    count = 0
    with open(path, "rb") as handle:
        for line in handle:
            digest.update(line)
            count += 1
    return count - 1, digest.hexdigest()
