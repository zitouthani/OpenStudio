from __future__ import annotations

import csv
from collections.abc import Iterable

from src.component_sdk.contracts import ComponentContract


class CSVReader(ComponentContract):
    """Read rows from a CSV file and emit dictionaries."""

    def __init__(self, path: str, delimiter: str = ",") -> None:
        self.path = path
        self.delimiter = delimiter

    def process(self, rows: Iterable[dict]) -> list[dict]:
        return list(self.iter_rows())

    def iter_rows(self) -> Iterable[dict]:
        """Yield CSV records incrementally for bounded pipeline execution."""
        with open(self.path, newline="", encoding="utf-8") as handle:
            yield from csv.DictReader(handle, delimiter=self.delimiter)
