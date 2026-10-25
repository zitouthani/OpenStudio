from __future__ import annotations

from typing import Callable, Iterable, List

from src.component_sdk.contracts import ComponentContract


class TransformComponent(ComponentContract):
    """Apply a transformation to every row."""

    def __init__(self, transformer: Callable[[dict], dict]) -> None:
        self.transformer = transformer

    def process(self, rows: Iterable[dict]) -> List[dict]:
        return [self.transformer(row) for row in rows]
