from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class Component:
    """A single job step or execution unit."""

    name: str
    type: str
    config: Dict[str, Any] = field(default_factory=dict)
    id: str | None = None


@dataclass
class Job:
    """A versioned ETL job definition."""

    name: str
    version: str = "1.0"
    components: List[Component] = field(default_factory=list)
    connections: List[Tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "components": [
                {
                    "id": component.id or component.name,
                    "name": component.name,
                    "type": component.type,
                    "config": component.config,
                }
                for component in self.components
            ],
            "connections": [
                {"source": source, "target": target}
                for source, target in self.connections
            ],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Job":
        components = [
            Component(
                name=item["name"],
                type=item["type"],
                config=item.get("config", {}),
                id=item.get("id"),
            )
            for item in payload.get("components", [])
        ]
        connections = [
            (conn["source"], conn["target"])
            for conn in payload.get("connections", [])
        ]
        return cls(
            name=payload.get("name", "job"),
            version=payload.get("version", "1.0"),
            components=components,
            connections=connections,
        )
