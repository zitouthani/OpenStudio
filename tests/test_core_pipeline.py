from src.components.csv_writer import CSVWriter
from src.components.filter import FilterComponent
from src.components.transform import TransformComponent
from src.engine.graph import ExecutionGraph
from src.engine.runtime import execute_graph
from src.job_model.job import Component, Job
from src.job_model.validation import validate_job


def test_job_validation_requires_name_and_components() -> None:
    job = Job(name="", components=[])
    try:
        validate_job(job)
    except ValueError:
        return
    raise AssertionError("Expected validation failure for an empty job.")


def test_pipeline_executes_successfully() -> None:
    rows = [
        {"name": "Alice", "amount": 10, "status": "active"},
        {"name": "Bob", "amount": 5, "status": "inactive"},
    ]

    graph = ExecutionGraph()
    graph.add_component("filter", FilterComponent(lambda row: row["status"] == "active"))
    graph.add_component("transform", TransformComponent(lambda row: {**row, "amount": row["amount"] * 2}))
    graph.add_component("writer", CSVWriter("output.csv"))

    result = execute_graph(graph, rows)

    assert result == [{"name": "Alice", "amount": 20, "status": "active"}]
