from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable, List


class ComponentContract(ABC):
    """Base contract for all ETL components."""

    @abstractmethod
    def process(self, rows: Iterable[dict]) -> List[dict]:
        raise NotImplementedError
