from __future__ import annotations

import csv

import pytest

from src.desktop.app import OpenStudioApp
from src.desktop.pipeline import (
    CSV_READER,
    CSV_WRITER,
    FILTER,
    TRANSFORM,
    build_execution_graph,
    connect_in_order,
    create_component,
    validate_visual_job,
)
from src.engine.runtime import execute_graph
from src.job_model.job import Job


def make_job(input_path: str, output_path: str) -> Job:
    reader = create_component(CSV_READER)
    reader.config.update(path=input_path, delimiter=",")
    row_filter = create_component(FILTER)
    row_filter.config.update(field="status", operator="equals", value="active")
    transform = create_component(TRANSFORM)
    transform.config.update(
        source_column="amount",
        target_column="amount_doubled",
        multiplier="2",
    )
    writer = create_component(CSV_WRITER)
    writer.config.update(path=output_path)
    components = [reader, row_filter, transform, writer]
    return Job(
        name="Active accounts",
        components=components,
        connections=connect_in_order(components),
    )


def test_visual_job_runs_csv_filter_transform_and_writer(tmp_path) -> None:
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "output.csv"
    input_path.write_text(
        "name,amount,status\nAlice,10,active\nBob,5,inactive\n",
        encoding="utf-8",
    )
    job = make_job(str(input_path), str(output_path))

    rows = execute_graph(build_execution_graph(job), [])

    assert rows == [{"name": "Alice", "status": "active", "amount_doubled": 20}]
    with output_path.open(newline="", encoding="utf-8") as handle:
        assert list(csv.DictReader(handle)) == [
            {"name": "Alice", "status": "active", "amount_doubled": "20"}
        ]


def test_visual_job_requires_ordered_connections(tmp_path) -> None:
    job = make_job(str(tmp_path / "input.csv"), str(tmp_path / "output.csv"))
    job.connections = []

    with pytest.raises(ValueError, match="Connect each component"):
        validate_visual_job(job)


def test_visual_job_cannot_overwrite_input_file(tmp_path) -> None:
    path = str(tmp_path / "same.csv")
    job = make_job(path, path)

    with pytest.raises(ValueError, match="must not overwrite"):
        validate_visual_job(job)


def test_numeric_filter_rejects_non_numeric_expected_value(tmp_path) -> None:
    job = make_job(str(tmp_path / "input.csv"), str(tmp_path / "output.csv"))
    job.components[1].config.update(operator="greater than", value="many")

    with pytest.raises(ValueError, match="requires a numeric value"):
        validate_visual_job(job)


def test_component_ids_are_unique() -> None:
    assert create_component(FILTER).id != create_component(FILTER).id


def test_desktop_shell_can_be_imported_without_gui_dependency() -> None:
    assert OpenStudioApp().render() == "OpenStudio ETL desktop editor."


def test_csv_writer_creates_empty_output_for_zero_rows(tmp_path) -> None:
    job = make_job(str(tmp_path / "input.csv"), str(tmp_path / "output.csv"))
    job.components = [job.components[0], job.components[-1]]
    job.connections = connect_in_order(job.components)
    job.components[0].config["path"] = str(tmp_path / "empty.csv")
    (tmp_path / "empty.csv").write_text("name\n", encoding="utf-8")

    rows = execute_graph(build_execution_graph(job), [])

    assert rows == []
    assert (tmp_path / "output.csv").exists()
    assert (tmp_path / "output.csv").read_text(encoding="utf-8") == ""
