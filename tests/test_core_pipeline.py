import csv

from src.components.csv_reader import CSVReader
from src.components.csv_writer import CSVWriter
from src.components.filter import FilterComponent
from src.components.transform import TransformComponent
from src.engine.graph import ExecutionGraph
from src.engine.runtime import execute_graph
from src.job_model.job import Job
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


def test_csv_pipeline_runs_end_to_end(tmp_path) -> None:
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.csv"
    input_path.write_text(
        "name,amount,status\nAlice,10,active\nBob,5,inactive\n",
        encoding="utf-8",
    )

    graph = ExecutionGraph()
    graph.add_component("writer", CSVWriter(str(output_path)))
    graph.add_component(
        "transform",
        TransformComponent(lambda row: {**row, "amount": str(int(row["amount"]) * 2)}),
    )
    graph.add_component("filter", FilterComponent(lambda row: row["status"] == "active"))
    graph.add_component("reader", CSVReader(str(input_path)))
    graph.connect("reader", "filter")
    graph.connect("filter", "transform")
    graph.connect("transform", "writer")

    result = execute_graph(graph, [])

    assert result == [{"name": "Alice", "amount": "20", "status": "active"}]
    with output_path.open(newline="", encoding="utf-8") as handle:
        assert list(csv.DictReader(handle)) == result
