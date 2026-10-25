from __future__ import annotations

import csv
from typing import Iterable, List

from src.component_sdk.contracts import ComponentContract


class CSVWriter(ComponentContract):
    """Write rows to disk as CSV files."""

    def __init__(self, path: str) -> None:
        self.path = path

    def process(self, rows: Iterable[dict]) -> List[dict]:
        row_list = list(rows)
        if not row_list:
            return []

        fieldnames = list(row_list[0].keys())
        with open(self.path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(row_list)
        return row_list
