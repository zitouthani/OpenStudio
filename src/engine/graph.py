from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ExecutionGraph:
    """A lightweight execution graph for ETL jobs."""

    components: Dict[str, Any] = field(default_factory=dict)
    edges: List[tuple[str, str]] = field(default_factory=list)

    def add_component(self, component_id: str, component: Any) -> None:
        self.components[component_id] = component

    def connect(self, source: str, target: str) -> None:
        self.edges.append((source, target))

    def ordered_components(self) -> List[str]:
        order: List[str] = []
        for component_id in self.components:
            if component_id not in {target for _, target in self.edges}:
                order.append(component_id)
        for source, target in self.edges:
            if source in self.components and target in self.components:
                if source not in order:
                    order.append(source)
                if target not in order:
                    order.append(target)
        return order
