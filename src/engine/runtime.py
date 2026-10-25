from __future__ import annotations

from typing import Any, Iterable, List

from .graph import ExecutionGraph


def execute_graph(graph: ExecutionGraph, rows: Iterable[dict]) -> List[dict]:
    """Run a simple graph pipeline using the component contracts."""
    current_rows = list(rows)
    for component_id in graph.ordered_components():
        component = graph.components.get(component_id)
        if component is None:
            continue
        current_rows = component.process(current_rows)
    return current_rows
