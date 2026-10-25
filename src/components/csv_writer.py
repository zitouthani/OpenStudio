from __future__ import annotations

import csv
from collections.abc import Iterable

from src.component_sdk.contracts import ComponentContract


class CSVWriter(ComponentContract):
    """Write rows to disk as CSV files."""

    def __init__(self, path: str) -> None:
        self.path = path

    def process(self, rows: Iterable[dict]) -> list[dict]:
        row_list = list(rows)
        with open(self.path, "w", newline="", encoding="utf-8") as handle:
            if row_list:
                fieldnames = list(row_list[0].keys())
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(row_list)
        return row_list
