from __future__ import annotations

import csv
from typing import Iterable, List

from src.component_sdk.contracts import ComponentContract


class CSVReader(ComponentContract):
    """Read rows from a CSV file and emit dictionaries."""

    def __init__(self, path: str, delimiter: str = ",") -> None:
        self.path = path
        self.delimiter = delimiter

    def process(self, rows: Iterable[dict]) -> List[dict]:
        with open(self.path, newline="", encoding="utf-8") as handle:
            data = list(csv.DictReader(handle, delimiter=self.delimiter))
        return data
