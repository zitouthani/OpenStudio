from __future__ import annotations

import csv
import errno
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import tracemalloc
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.components.csv_reader import CSVReader
from src.components.csv_writer import CSVWriter
from src.data_runtime.batch import Batch
from src.engine import runtime as engine_runtime
from src.engine.graph import ExecutionGraph
from src.engine.runtime import (
    BadRecordError,
    BatchExecutionError,
    BoundedBatchQueue,
    CancellationToken,
    execute_graph_stream,
)

BASELINE_THROUGHPUT_ROWS_PER_SECOND = 535_098
KILL_SIGNAL = getattr(signal, "SIGKILL", signal.SIGTERM)


class PassThrough:
    def process(self, rows):
        return list(rows)


def test_batches_have_stable_ids_and_respect_configured_size(tmp_path: Path) -> None:
    graph = ExecutionGraph()
    graph.add_component("pass", PassThrough())
    seen: list[Batch] = []

    execute_graph_stream(
        graph,
        ({"value": value} for value in range(7)),
        batch_size=3,
        checkpoint_path=tmp_path / "checkpoint.json",
        on_batch=seen.append,
    )

    assert [batch.batch_id for batch in seen] == [
        "batch-00000000000000000000",
        "batch-00000000000000000001",
        "batch-00000000000000000002",
    ]
    assert [len(batch.rows) for batch in seen] == [3, 3, 1]


def test_csv_reader_streams_into_batch_writer(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    source.write_text("value\none\ntwo\n", encoding="utf-8")
    output = tmp_path / "output.csv"
    graph = ExecutionGraph()
    graph.add_component("writer", CSVWriter(str(output)))

    metrics = execute_graph_stream(
        graph,
        CSVReader(str(source)).iter_rows(),
        batch_size=1,
    )

    assert metrics.records_in == 2
    assert list(csv.DictReader(output.open(encoding="utf-8"))) == [
        {"value": "one"},
        {"value": "two"},
    ]


def test_empty_stream_replaces_output_with_empty_file(tmp_path: Path) -> None:
    output = tmp_path / "output.csv"
    output.write_text("stale data\n", encoding="utf-8")
    graph = ExecutionGraph()
    graph.add_component("writer", CSVWriter(str(output)))

    metrics = execute_graph_stream(graph, [], batch_size=2)

    assert metrics.records_in == 0
    assert output.read_bytes() == b""


def test_bounded_queue_blocks_producer_until_consumer_reads() -> None:
    queue = BoundedBatchQueue(maxsize=1)
    queue.put("first")
    started = threading.Event()
    completed = threading.Event()

    def produce() -> None:
        started.set()
        queue.put("second")
        completed.set()

    producer = threading.Thread(target=produce)
    producer.start()
    assert started.wait(timeout=1)
    time.sleep(0.05)
    assert not completed.is_set()
    assert queue.get() == "first"
    assert completed.wait(timeout=1)
    assert queue.get() == "second"
    producer.join(timeout=1)
    assert not producer.is_alive()


def test_cancel_and_resume_matches_uninterrupted_csv_output(tmp_path: Path) -> None:
    rows = [{"value": value} for value in range(11)]
    reference = tmp_path / "reference.csv"
    interrupted = tmp_path / "interrupted.csv"
    checkpoint = tmp_path / "checkpoint.json"
    token = CancellationToken()
    calls = 0

    def cancel_after_two_batches(batch: Batch) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            token.cancel()

    reference_graph = ExecutionGraph()
    reference_graph.add_component("writer", CSVWriter(str(reference)))
    execute_graph_stream(reference_graph, rows, batch_size=3)

    resumed_graph = ExecutionGraph()
    resumed_graph.add_component("writer", CSVWriter(str(interrupted)))
    cancelled = execute_graph_stream(
        resumed_graph,
        rows,
        batch_size=3,
        checkpoint_path=checkpoint,
        cancel_token=token,
        on_batch=cancel_after_two_batches,
    )

    assert cancelled.cancelled
    assert not interrupted.exists()
    assert json.loads(checkpoint.read_text()) == {
        "batch_size": 3,
        "last_committed_batch": "batch-00000000000000000001",
        "cumulative_metrics": {
            "batches_processed": 2,
            "records_in": 6,
            "records_out": 6,
            "records_rejected": 0,
        },
        "version": 1,
    }

    resumed_graph = ExecutionGraph()
    resumed_graph.add_component("writer", CSVWriter(str(interrupted)))
    result = execute_graph_stream(
        resumed_graph,
        rows,
        batch_size=3,
        checkpoint_path=checkpoint,
        resume=True,
    )

    assert not result.cancelled
    assert interrupted.read_bytes() == reference.read_bytes()
    assert len(list(csv.DictReader(interrupted.open(encoding="utf-8")))) == len(rows)


def test_metrics_report_per_run_and_cumulative_counts_after_resume(tmp_path: Path) -> None:
    rows = [{"value": value} for value in range(5)]
    checkpoint = tmp_path / "checkpoint.json"
    output = tmp_path / "output.csv"
    token = CancellationToken()

    graph = ExecutionGraph()
    graph.add_component("writer", CSVWriter(str(output)))
    cancelled = execute_graph_stream(
        graph,
        rows,
        batch_size=2,
        checkpoint_path=checkpoint,
        cancel_token=token,
        on_batch=lambda batch: token.cancel(),
    )
    assert cancelled.cancelled
    assert cancelled.records_in == 2
    assert cancelled.cumulative_records_in == 2

    graph = ExecutionGraph()
    graph.add_component("writer", CSVWriter(str(output)))
    resumed = execute_graph_stream(
        graph,
        rows,
        batch_size=2,
        checkpoint_path=checkpoint,
        resume=True,
    )

    assert resumed.records_in == 3
    assert resumed.cumulative_records_in == 5
    assert resumed.cumulative_records_out == 5
    assert resumed.cumulative_batches_processed == 3
    prometheus = resumed.to_prometheus()
    assert "openstudio_run_records_in_total 3" in prometheus
    assert "openstudio_records_in_total 5" in prometheus


def test_bad_records_are_dead_lettered_and_valid_rows_are_written(tmp_path: Path) -> None:
    class ValidateRows:
        def process(self, rows):
            output = []
            for row in rows:
                if row["value"] < 0:
                    raise BadRecordError("value must be non-negative")
                output.append(row)
            return output

    output = tmp_path / "output.csv"
    dead_letters = tmp_path / "rejected.jsonl"
    graph = ExecutionGraph()
    graph.add_component("validate", ValidateRows())
    graph.add_component("writer", CSVWriter(str(output)))

    metrics = execute_graph_stream(
        graph,
        [{"value": 1}, {"value": -1}, {"value": 2}],
        batch_size=3,
        dead_letter_path=dead_letters,
    )

    assert list(csv.DictReader(output.open(encoding="utf-8"))) == [
        {"value": "1"},
        {"value": "2"},
    ]
    rejected = [json.loads(line) for line in dead_letters.read_text().splitlines()]
    assert rejected == [{"batch_id": "batch-00000000000000000000", "record": {"value": -1}, "reason": "value must be non-negative"}]
    assert metrics.records_rejected == 1


def test_failed_batch_does_not_publish_partial_output_or_checkpoint(tmp_path: Path) -> None:
    class AlwaysFails:
        def process(self, rows):
            raise OSError("downstream unavailable")

    output = tmp_path / "output.csv"
    checkpoint = tmp_path / "checkpoint.json"
    graph = ExecutionGraph()
    graph.add_component("writer", CSVWriter(str(output)))
    graph.add_component("failure", AlwaysFails())

    with pytest.raises(BatchExecutionError):
        execute_graph_stream(
            graph,
            [{"value": 1}],
            batch_size=1,
            checkpoint_path=checkpoint,
            retries=1,
            retry_backoff=0,
        )

    assert not output.exists()
    assert not checkpoint.exists()
    assert not Path(f"{output}.batches").exists()


def test_output_enospc_cleans_staged_batch_and_can_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output.csv"
    graph = ExecutionGraph()
    graph.add_component("writer", CSVWriter(str(output)))

    def no_space(fd: int) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "fsync", no_space)
    with pytest.raises(BatchExecutionError):
        execute_graph_stream(
            graph,
            [{"value": 1}, {"value": 2}],
            batch_size=2,
            retries=0,
        )
    assert not output.exists()
    assert not list(tmp_path.rglob("*.tmp"))

    monkeypatch.undo()
    graph = ExecutionGraph()
    graph.add_component("writer", CSVWriter(str(output)))
    execute_graph_stream(graph, [{"value": 1}, {"value": 2}], batch_size=2)
    assert list(csv.DictReader(output.open(encoding="utf-8"))) == [
        {"value": "1"},
        {"value": "2"},
    ]


def test_finalize_enospc_keeps_checkpoint_for_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output.csv"
    checkpoint = tmp_path / "checkpoint.json"
    calls = 0
    real_fsync = os.fsync

    def fail_final_output_fsync(fd: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError(errno.ENOSPC, "No space left on device")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_final_output_fsync)
    monkeypatch.setattr(engine_runtime, "_fsync_directory", lambda directory: None)
    graph = ExecutionGraph()
    graph.add_component("writer", CSVWriter(str(output)))
    with pytest.raises(OSError, match="No space left on device"):
        execute_graph_stream(
            graph,
            [{"value": 1}, {"value": 2}],
            batch_size=2,
            checkpoint_path=checkpoint,
            retries=0,
        )
    assert calls == 3
    assert not output.exists()
    assert checkpoint.exists()
    assert not list(tmp_path.glob("*.tmp"))

    monkeypatch.undo()
    graph = ExecutionGraph()
    graph.add_component("writer", CSVWriter(str(output)))
    execute_graph_stream(
        graph,
        [{"value": 1}, {"value": 2}],
        batch_size=2,
        checkpoint_path=checkpoint,
        resume=True,
    )
    assert list(csv.DictReader(output.open(encoding="utf-8"))) == [
        {"value": "1"},
        {"value": "2"},
    ]


def test_resume_rejects_checkpoint_with_different_batch_size(tmp_path: Path) -> None:
    graph = ExecutionGraph()
    graph.add_component("writer", CSVWriter(str(tmp_path / "output.csv")))
    checkpoint = tmp_path / "checkpoint.json"
    token = CancellationToken()
    execute_graph_stream(
        graph,
        [{"value": 1}, {"value": 2}],
        batch_size=2,
        checkpoint_path=checkpoint,
        cancel_token=token,
        on_batch=lambda batch: token.cancel(),
    )

    with pytest.raises(ValueError, match="batch size"):
        execute_graph_stream(
            graph,
            [{"value": 1}, {"value": 2}],
            batch_size=1,
            checkpoint_path=checkpoint,
            resume=True,
        )


def test_retry_rewrites_batch_without_duplicate_csv_records(tmp_path: Path) -> None:
    class FlakyComponent:
        calls = 0

        def process(self, rows):
            self.calls += 1
            if self.calls == 1:
                raise OSError("temporary downstream failure")
            return list(rows)

    output = tmp_path / "output.csv"
    graph = ExecutionGraph()
    graph.add_component("writer", CSVWriter(str(output)))
    graph.add_component("flaky", FlakyComponent())

    metrics = execute_graph_stream(
        graph,
        [{"value": 1}, {"value": 2}],
        batch_size=2,
        retries=1,
        retry_backoff=0,
    )

    assert metrics.batches_retried == 1
    assert list(csv.DictReader(output.open(encoding="utf-8"))) == [
        {"value": "1"},
        {"value": "2"},
    ]


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX process signals")
@pytest.mark.parametrize(
    ("signal_number", "interruption_value"),
    [
        (KILL_SIGNAL, 0),
        (KILL_SIGNAL, 4),
        (KILL_SIGNAL, 8),
        (signal.SIGTERM, 4),
    ],
)
def test_process_interruption_resumes_to_identical_output(
    tmp_path: Path,
    signal_number: int,
    interruption_value: int,
) -> None:
    reference = tmp_path / "reference.csv"
    interrupted = tmp_path / "interrupted.csv"
    checkpoint = tmp_path / "checkpoint.json"
    marker = tmp_path / "in-flight"
    rows = [{"value": value} for value in range(10)]

    graph = ExecutionGraph()
    graph.add_component("writer", CSVWriter(str(reference)))
    execute_graph_stream(graph, rows, batch_size=2)

    child = """
import sys
import time
from pathlib import Path
from src.components.csv_writer import CSVWriter
from src.engine.graph import ExecutionGraph
from src.engine.runtime import execute_graph_stream

class PauseInFlight:
    def process(self, rows):
        if rows[0]["value"] == int(sys.argv[5]):
            Path(sys.argv[3]).touch()
            time.sleep(float(sys.argv[4]))
        return list(rows)

graph = ExecutionGraph()
graph.add_component("writer", CSVWriter(sys.argv[1]))
graph.add_component("pause", PauseInFlight())
execute_graph_stream(
    graph,
    ({"value": value} for value in range(10)),
    batch_size=2,
    checkpoint_path=sys.argv[2],
)
"""
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            child,
            str(interrupted),
            str(checkpoint),
            str(marker),
            "30" if signal_number == KILL_SIGNAL else "0.5",
            str(interruption_value),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        if not marker.exists():
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
            pytest.fail(f"Child did not reach in-flight batch: {stdout}\n{stderr}")
        process.send_signal(signal_number)
        process.wait(timeout=5)
        assert process.returncode in (-KILL_SIGNAL, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

    assert not interrupted.exists()
    resumed_graph = ExecutionGraph()
    resumed_graph.add_component("writer", CSVWriter(str(interrupted)))
    execute_graph_stream(
        resumed_graph,
        rows,
        batch_size=2,
        checkpoint_path=checkpoint,
        resume=True,
    )
    assert interrupted.read_bytes() == reference.read_bytes()


def test_metrics_match_ground_truth_and_report_queue_depth(tmp_path: Path) -> None:
    graph = ExecutionGraph()
    graph.add_component("pass", PassThrough())
    metrics = execute_graph_stream(
        graph,
        ({"value": value} for value in range(5)),
        batch_size=2,
    )

    assert metrics.batches_processed == 3
    assert metrics.batches_failed == 0
    assert metrics.records_in == 5
    assert metrics.records_out == 5
    assert metrics.records_rejected == 0
    assert metrics.queue_depths == {"pass": 0}
    assert metrics.throughput_records_per_second > 0
    assert "openstudio_queue_depth{stage=\"pass\"} 0" in metrics.to_prometheus()
    metrics_path = tmp_path / "metrics.prom"
    metrics.write_prometheus(metrics_path)
    assert metrics_path.read_text() == metrics.to_prometheus()


def test_large_stream_uses_bounded_python_memory(tmp_path: Path) -> None:
    graph = ExecutionGraph()
    graph.add_component("pass", PassThrough())
    tracemalloc.start()
    try:
        metrics = execute_graph_stream(
            graph,
            ({"value": value, "payload": "x" * 100} for value in range(100_000)),
            batch_size=128,
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert metrics.records_in == 100_000
    assert peak < 5_000_000


@pytest.mark.skipif(os.name != "posix", reason="throughput baseline is measured on Linux")
def test_throughput_does_not_regress_below_baseline_threshold() -> None:
    graph = ExecutionGraph()
    graph.add_component("pass", PassThrough())
    metrics = execute_graph_stream(
        graph,
        ({"value": value} for value in range(100_000)),
        batch_size=256,
    )

    assert metrics.throughput_records_per_second >= (
        BASELINE_THROUGHPUT_ROWS_PER_SECOND * 0.5
    )


def test_large_stream_fits_a_hard_docker_memory_limit() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker is not installed")
    daemon = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if daemon.returncode:
        pytest.skip("Docker daemon is not available")

    repository = Path(__file__).resolve().parents[1]
    code = """
from pathlib import Path
from src.engine.graph import ExecutionGraph
from src.engine.runtime import execute_graph_stream

class PassThrough:
    def process(self, rows):
        return list(rows)

graph = ExecutionGraph()
graph.add_component("pass", PassThrough())
metrics = execute_graph_stream(
    graph,
    ({"id": i, "value": f"row-{i}"} for i in range(1_000_000)),
    batch_size=256,
)
peak = int(Path("/sys/fs/cgroup/memory.peak").read_text())
print(f"rows={metrics.records_in} batches={metrics.batches_processed} cgroup_peak_bytes={peak}")
assert peak < 64 * 1024 * 1024
"""
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--memory=64m",
            "--memory-swap=64m",
            "-v",
            f"{repository}:/workspace",
            "-w",
            "/workspace",
            "python:3.12-slim",
            "python",
            "-c",
            code,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "rows=1000000" in result.stdout


@settings(max_examples=20, deadline=None)
@given(
    values=st.lists(st.integers(), max_size=50),
    interruption=st.integers(min_value=0, max_value=20),
)
def test_checkpoint_resume_matches_uninterrupted_for_any_interruption(
    values: list[int], interruption: int
) -> None:
    with TemporaryDirectory() as directory:
        tmp_path = Path(directory)
        rows = [{"value": value} for value in values]
        reference = tmp_path / "reference.csv"
        resumed = tmp_path / "resumed.csv"
        checkpoint = tmp_path / "checkpoint.json"

        graph = ExecutionGraph()
        graph.add_component("writer", CSVWriter(str(reference)))
        execute_graph_stream(graph, rows, batch_size=4)

        token = CancellationToken()
        if interruption == 0:
            token.cancel()
        else:
            processed = 0

            def interrupt(batch: Batch) -> None:
                nonlocal processed
                processed += 1
                if processed == interruption:
                    token.cancel()

            graph = ExecutionGraph()
            graph.add_component("writer", CSVWriter(str(resumed)))
            execute_graph_stream(
                graph,
                rows,
                batch_size=4,
                checkpoint_path=checkpoint,
                cancel_token=token,
                on_batch=interrupt,
            )

        graph = ExecutionGraph()
        graph.add_component("writer", CSVWriter(str(resumed)))
        execute_graph_stream(
            graph,
            rows,
            batch_size=4,
            checkpoint_path=checkpoint,
            resume=True,
        )

        assert resumed.read_bytes() == reference.read_bytes()
