from __future__ import annotations

from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.components import CSVReader, CSVWriter, FilterComponent, TransformComponent
from src.engine.graph import ExecutionGraph
from src.job_model.job import Component, Job
from src.job_model.validation import validate_job

CSV_READER = "csv_reader"
FILTER = "filter"
TRANSFORM = "transform"
CSV_WRITER = "csv_writer"

COMPONENT_LABELS = {
    CSV_READER: "CSV Reader",
    FILTER: "Filter",
    TRANSFORM: "Transform",
    CSV_WRITER: "CSV Writer",
}

DEFAULT_CONFIGS: dict[str, dict[str, Any]] = {
    CSV_READER: {"path": "", "delimiter": ","},
    FILTER: {"field": "", "operator": "equals", "value": ""},
    TRANSFORM: {"source_column": "", "target_column": "", "multiplier": "1"},
    CSV_WRITER: {"path": ""},
}

FILTER_OPERATORS = ("equals", "not equals", "contains", "greater than", "less than")


def create_component(component_type: str) -> Component:
    """Create a job component with a stable type and unique identifier."""
    if component_type not in COMPONENT_LABELS:
        raise ValueError(f"Unsupported component type: {component_type}")

    return Component(
        id=f"{component_type}_{uuid4().hex[:8]}",
        name=COMPONENT_LABELS[component_type],
        type=component_type,
        config=DEFAULT_CONFIGS[component_type].copy(),
    )


def connect_in_order(components: list[Component]) -> list[tuple[str, str]]:
    """Connect the visual pipeline from top to bottom in component order."""
    return [
        (source.id or source.name, target.id or target.name)
        for source, target in pairwise(components)
    ]


def validate_visual_job(job: Job) -> None:
    """Validate the supported, linear pipeline model used by the first editor."""
    validate_job(job)
    if job.components[0].type != CSV_READER:
        raise ValueError("A runnable visual job must start with a CSV Reader.")
    if job.components[-1].type != CSV_WRITER:
        raise ValueError("A runnable visual job must end with a CSV Writer.")

    for component in job.components:
        if component.type not in COMPONENT_LABELS:
            raise ValueError(f"Unsupported component type: {component.type}")
        if not isinstance(component.config, dict):
            raise TypeError(f"{component.name}: component config must be an object.")

    expected_connections = connect_in_order(job.components)
    if job.connections != expected_connections:
        raise ValueError("Connect each component to the next component in order.")

    for component in job.components:
        if component.type == CSV_READER:
            delimiter = component.config.get("delimiter")
            if not isinstance(delimiter, str) or len(delimiter) != 1:
                raise ValueError(f"{component.name}: delimiter must be one character.")
            path = _configured_string(component, "path")
            if not Path(path).suffix:
                raise ValueError(f"{component.name}: choose a file path with an extension.")
        elif component.type == CSV_WRITER:
            path = _configured_string(component, "path")
            if not Path(path).suffix:
                raise ValueError(f"{component.name}: choose a file path with an extension.")
        elif component.type == FILTER:
            _row_predicate(component)
        elif component.type == TRANSFORM:
            _row_transformer(component)

    input_path = Path(_configured_string(job.components[0], "path")).resolve()
    output_path = Path(_configured_string(job.components[-1], "path")).resolve()
    same_file = input_path == output_path or (
        input_path.exists() and output_path.exists() and input_path.samefile(output_path)
    )
    if same_file:
        raise ValueError("CSV Writer must not overwrite the CSV Reader input file.")


def _configured_string(component: Component, key: str) -> str:
    value = component.config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{component.name}: '{key}' must not be empty.")
    return value.strip()


def _row_predicate(component: Component) -> Callable[[dict[str, Any]], bool]:
    field = _configured_string(component, "field")
    operator = _configured_string(component, "operator")
    value = component.config.get("value", "")
    if not isinstance(value, str):
        raise TypeError(f"{component.name}: 'value' must be text.")
    if operator not in FILTER_OPERATORS:
        raise ValueError(f"{component.name}: unsupported filter operator '{operator}'.")
    if operator in {"greater than", "less than"}:
        try:
            float(value)
        except ValueError as error:
            raise ValueError(
                f"{component.name}: numeric comparison requires a numeric value."
            ) from error

    def predicate(row: dict[str, Any]) -> bool:
        if field not in row:
            raise ValueError(f"{component.name}: input column '{field}' does not exist.")
        actual = row[field]
        if operator == "equals":
            return str(actual) == value
        if operator == "not equals":
            return str(actual) != value
        if operator == "contains":
            return value in str(actual)

        try:
            actual_number = float(actual)
            expected_number = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{component.name}: numeric comparison requires numeric values."
            ) from error
        if operator == "greater than":
            return actual_number > expected_number
        return actual_number < expected_number

    return predicate


def _row_transformer(component: Component) -> Callable[[dict[str, Any]], dict[str, Any]]:
    source = _configured_string(component, "source_column")
    target = _configured_string(component, "target_column")
    raw_multiplier = component.config.get("multiplier", "1")
    try:
        multiplier = float(raw_multiplier)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{component.name}: multiplier must be numeric.") from error

    def transform(row: dict[str, Any]) -> dict[str, Any]:
        if source not in row:
            raise ValueError(f"{component.name}: input column '{source}' does not exist.")
        transformed = row[source]
        if multiplier != 1:
            try:
                transformed = float(transformed) * multiplier
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"{component.name}: column '{source}' must contain numeric values."
                ) from error
            if transformed.is_integer():
                transformed = int(transformed)
        output = row.copy()
        if source != target:
            output.pop(source)
        output[target] = transformed
        return output

    return transform


def build_execution_graph(job: Job) -> ExecutionGraph:
    """Validate a visual job and compile its supported steps for the engine."""
    validate_visual_job(job)
    graph = ExecutionGraph()

    for component in job.components:
        component_id = component.id or component.name
        if component.type == CSV_READER:
            delimiter = component.config.get("delimiter")
            if not isinstance(delimiter, str) or len(delimiter) != 1:
                raise ValueError(f"{component.name}: delimiter must be one character.")
            instance = CSVReader(_configured_string(component, "path"), delimiter)
        elif component.type == FILTER:
            instance = FilterComponent(_row_predicate(component))
        elif component.type == TRANSFORM:
            instance = TransformComponent(_row_transformer(component))
        else:
            instance = CSVWriter(_configured_string(component, "path"))
        graph.add_component(component_id, instance)

    for source, target in job.connections:
        graph.connect(source, target)
    return graph
