from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from itertools import islice
from typing import Any


@dataclass
class Batch:
    """A batch of rows processed together."""

    rows: list[dict[str, Any]] = field(default_factory=list)
    batch_id: str = ""

    def add(self, row: dict[str, Any]) -> None:
        self.rows.append(row)

    def clear(self) -> None:
        self.rows.clear()


def iter_batches(rows: Iterable[dict[str, Any]], batch_size: int) -> Iterator[Batch]:
    """Yield bounded batches with IDs that are stable for a stable input order."""
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")

    iterator = iter(rows)
    batch_number = 0
    while batch_rows := list(islice(iterator, batch_size)):
        yield Batch(
            rows=batch_rows,
            batch_id=f"batch-{batch_number:020d}",
        )
        batch_number += 1
