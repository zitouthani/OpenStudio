from __future__ import annotations

from typing import Any, Dict


class ComponentRegistry:
    """Simple registry for component discovery."""

    def __init__(self) -> None:
        self._components: Dict[str, Any] = {}

    def register(self, name: str, component: Any) -> None:
        self._components[name] = component

    def get(self, name: str) -> Any:
        return self._components[name]
