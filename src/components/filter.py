from __future__ import annotations

from typing import Callable, Iterable, List

from src.component_sdk.contracts import ComponentContract


class FilterComponent(ComponentContract):
    """Keep rows that pass a predicate."""

    def __init__(self, predicate: Callable[[dict], bool]) -> None:
        self.predicate = predicate

    def process(self, rows: Iterable[dict]) -> List[dict]:
        return [row for row in rows if self.predicate(row)]
