from __future__ import annotations

import json
import os
import queue
import signal
import tempfile
import threading
import time
import tracemalloc
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.data_runtime.batch import Batch, iter_batches

from .graph import ExecutionGraph


class BadRecordError(ValueError):
    """Indicate that one input record is invalid and may be rejected."""


class BatchExecutionError(RuntimeError):
    """A batch could not complete after the configured retries."""

    def __init__(self, batch_id: str, cause: Exception, metrics: ExecutionMetrics) -> None:
        super().__init__(f"Batch {batch_id} failed: {cause}")
        self.batch_id = batch_id
        self.cause = cause
        self.metrics = metrics


class CancellationToken:
    """Thread-safe cancellation request for a running execution."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class BoundedBatchQueue:
    """A blocking batch queue that always has a finite capacity."""

    def __init__(self, maxsize: int) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be greater than zero")
        self.maxsize = maxsize
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=maxsize)

    def put(self, item: Any, block: bool = True, timeout: float | None = None) -> None:
        self._queue.put(item, block=block, timeout=timeout)

    def get(self, block: bool = True, timeout: float | None = None) -> Any:
        return self._queue.get(block=block, timeout=timeout)

    def qsize(self) -> int:
        return self._queue.qsize()


@dataclass
class ExecutionMetrics:
    batches_processed: int = 0
    batches_failed: int = 0
    batches_retried: int = 0
    records_in: int = 0
    records_out: int = 0
    records_rejected: int = 0
    queue_depths: dict[str, int] = field(default_factory=dict)
    peak_memory_bytes: int = 0
    elapsed_seconds: float = 0.0
    cancelled: bool = False
    cumulative_batches_processed: int = 0
    cumulative_records_in: int = 0
    cumulative_records_out: int = 0
    cumulative_records_rejected: int = 0

    @property
    def throughput_records_per_second(self) -> float:
        if self.elapsed_seconds <= 0:
            return 0.0
        return self.records_in / self.elapsed_seconds

    def to_prometheus(self) -> str:
        lines = [
            f"openstudio_batches_processed {self.batches_processed}",
            f"openstudio_batches_failed {self.batches_failed}",
            f"openstudio_batches_retried {self.batches_retried}",
            f"openstudio_records_in {self.records_in}",
            f"openstudio_records_out {self.records_out}",
            f"openstudio_records_rejected {self.records_rejected}",
            f"openstudio_run_batches_processed_total {self.batches_processed}",
            f"openstudio_run_records_in_total {self.records_in}",
            f"openstudio_run_records_out_total {self.records_out}",
            f"openstudio_run_records_rejected_total {self.records_rejected}",
            f"openstudio_batches_processed_total {self.cumulative_batches_processed}",
            f"openstudio_records_in_total {self.cumulative_records_in}",
            f"openstudio_records_out_total {self.cumulative_records_out}",
            f"openstudio_records_rejected_total {self.cumulative_records_rejected}",
            f"openstudio_throughput_records_per_second {self.throughput_records_per_second}",
            f"openstudio_peak_memory_bytes {self.peak_memory_bytes}",
            f"openstudio_elapsed_seconds {self.elapsed_seconds}",
        ]
        for stage, depth in sorted(self.queue_depths.items()):
            safe_stage = stage.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            lines.append(f'openstudio_queue_depth{{stage="{safe_stage}"}} {depth}')
        return "\n".join(lines) + "\n"

    def write_prometheus(self, path: str | os.PathLike[str]) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(self.to_prometheus())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, destination)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


class _Checkpoint:
    version = 1

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, Any] = {}

    def last_committed_number(self, batch_size: int) -> int:
        if not self.path.exists():
            return -1
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("version") != self.version:
                raise ValueError("Unsupported checkpoint version")
            if data.get("batch_size") != batch_size:
                raise ValueError("Checkpoint batch size does not match this run")
            batch_id = data.get("last_committed_batch")
            if batch_id is None:
                self._data = data
                return -1
            prefix, separator, number = batch_id.rpartition("-")
            if prefix != "batch" or not separator:
                raise ValueError("Invalid committed batch ID")
            self._data = data
            return int(number)
        except (OSError, json.JSONDecodeError, AttributeError, TypeError) as error:
            raise ValueError(f"Invalid checkpoint: {self.path}") from error

    def cumulative_metrics(self) -> dict[str, int]:
        stored = self._data.get("cumulative_metrics", {})
        if not isinstance(stored, dict) or any(
            not isinstance(key, str)
            or not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
            for key, value in stored.items()
        ):
            raise ValueError(f"Invalid cumulative metrics in checkpoint: {self.path}")
        return stored

    def commit(
        self,
        batch_id: str,
        batch_size: int,
        cumulative_metrics: dict[str, int],
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "version": self.version,
                        "batch_size": batch_size,
                        "last_committed_batch": batch_id,
                        "cumulative_metrics": cumulative_metrics,
                    },
                    handle,
                    sort_keys=True,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self.path)
            _fsync_directory(self.path.parent)
            self._data = {
                "version": self.version,
                "batch_size": batch_size,
                "last_committed_batch": batch_id,
                "cumulative_metrics": cumulative_metrics,
            }
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise


def execute_graph(graph: ExecutionGraph, rows: Iterable[dict]) -> list[dict]:
    """Run the legacy whole-input graph API and return all resulting rows."""
    current_rows = list(rows)
    for component_id in graph.ordered_components():
        component = graph.components.get(component_id)
        if component is None:
            continue
        current_rows = component.process(current_rows)
    return current_rows


def execute_graph_stream(
    graph: ExecutionGraph,
    rows: Iterable[dict],
    *,
    batch_size: int = 1000,
    checkpoint_path: str | os.PathLike[str] | None = None,
    resume: bool = False,
    cancel_token: CancellationToken | None = None,
    retries: int = 3,
    retry_backoff: float = 0.1,
    dead_letter_path: str | os.PathLike[str] | None = None,
    on_batch: Callable[[Batch], None] | None = None,
) -> ExecutionMetrics:
    """Execute a graph incrementally; use this entry point for large inputs.

    Batch-aware components may implement ``process_batch(rows, batch_id)`` and
    ``finalize_batches()``. Such writes must be idempotent for a stable batch
    ID. ``on_batch`` is a progress callback and receives completed batch data.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")
    if retries < 0:
        raise ValueError("retries must not be negative")
    if retry_backoff < 0:
        raise ValueError("retry_backoff must not be negative")
    if resume and checkpoint_path is None:
        raise ValueError("resume requires checkpoint_path")

    token = cancel_token or CancellationToken()
    checkpoint = _Checkpoint(Path(checkpoint_path)) if checkpoint_path is not None else None
    last_committed = (
        checkpoint.last_committed_number(batch_size) if resume and checkpoint else -1
    )
    if checkpoint is not None and not resume:
        checkpoint.path.unlink(missing_ok=True)

    component_ids = graph.ordered_components()
    components = [
        (component_id, graph.components[component_id])
        for component_id in component_ids
        if component_id in graph.components
    ]
    metrics = ExecutionMetrics(queue_depths={component_id: 0 for component_id, _ in components})
    if checkpoint is not None and resume:
        cumulative_metrics = checkpoint.cumulative_metrics()
        metrics.cumulative_batches_processed = cumulative_metrics.get("batches_processed", 0)
        metrics.cumulative_records_in = cumulative_metrics.get("records_in", 0)
        metrics.cumulative_records_out = cumulative_metrics.get("records_out", 0)
        metrics.cumulative_records_rejected = cumulative_metrics.get("records_rejected", 0)
    dead_letters = _DeadLetterWriter(Path(dead_letter_path)) if dead_letter_path else None
    for _, component in components:
        begin_batches = getattr(component, "begin_batches", None)
        if callable(begin_batches):
            begin_batches(resume=resume)
    if dead_letters is not None:
        dead_letters.begin(resume=resume)

    owns_tracing = not tracemalloc.is_tracing()
    if owns_tracing:
        tracemalloc.start()
    started = time.perf_counter()
    batch_iterator: Iterator[Batch] = iter_batches(rows, batch_size)

    try:
        with _signal_cancellation(token):
            batch_number = 0
            while not token.cancelled:
                try:
                    batch = next(batch_iterator)
                except StopIteration:
                    break
                current_number = batch_number
                batch_number += 1
                if current_number <= last_committed:
                    continue

                input_count = len(batch.rows)
                rejected: list[dict[str, Any]] = []
                for attempt in range(retries + 1):
                    try:
                        current_rows = batch.rows
                        rejected = []
                        for _, component in components:
                            current_rows, stage_rejected = _process_component(
                                component,
                                current_rows,
                                batch.batch_id,
                            )
                            rejected.extend(stage_rejected)
                        if dead_letters is not None:
                            dead_letters.stage(batch.batch_id, rejected)
                        break
                    except Exception as error:
                        if attempt >= retries:
                            metrics.batches_failed += 1
                            _rollback_batch(components, dead_letters, batch.batch_id, error)
                            raise BatchExecutionError(batch.batch_id, error, metrics) from error
                        metrics.batches_retried += 1
                        if retry_backoff:
                            time.sleep(min(retry_backoff * (2**attempt), 30.0))

                cumulative_metrics = {
                    "batches_processed": metrics.cumulative_batches_processed + 1,
                    "records_in": metrics.cumulative_records_in + input_count,
                    "records_out": metrics.cumulative_records_out + len(current_rows),
                    "records_rejected": metrics.cumulative_records_rejected + len(rejected),
                }
                if checkpoint is not None:
                    checkpoint.commit(batch.batch_id, batch_size, cumulative_metrics)
                metrics.batches_processed += 1
                metrics.records_in += input_count
                metrics.records_out += len(current_rows)
                metrics.records_rejected += len(rejected)
                metrics.cumulative_batches_processed = cumulative_metrics["batches_processed"]
                metrics.cumulative_records_in = cumulative_metrics["records_in"]
                metrics.cumulative_records_out = cumulative_metrics["records_out"]
                metrics.cumulative_records_rejected = cumulative_metrics["records_rejected"]
                batch.rows = current_rows
                if on_batch is not None:
                    on_batch(batch)

            metrics.cancelled = token.cancelled
            if not metrics.cancelled:
                for _, component in components:
                    finalize_batches = getattr(component, "finalize_batches", None)
                    if callable(finalize_batches):
                        finalize_batches()
                if dead_letters is not None:
                    dead_letters.finalize()
    finally:
        metrics.elapsed_seconds = time.perf_counter() - started
        if tracemalloc.is_tracing():
            _, metrics.peak_memory_bytes = tracemalloc.get_traced_memory()
            if owns_tracing:
                tracemalloc.stop()

    return metrics


def _process_component(
    component: Any,
    rows: list[dict],
    batch_id: str,
) -> tuple[list[dict], list[dict[str, Any]]]:
    try:
        process_batch = getattr(component, "process_batch", None)
        if callable(process_batch):
            output = process_batch(rows, batch_id)
        else:
            output = component.process(rows)
        return list(output), []
    except BadRecordError:
        valid_rows: list[dict] = []
        rejected: list[dict[str, Any]] = []
        for row in rows:
            try:
                valid_rows.extend(component.process([row]))
            except BadRecordError as error:
                rejected.append({"record": row, "reason": str(error)})
        return valid_rows, rejected


class _DeadLetterWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.batch_dir = Path(f"{path}.batches")

    def begin(self, resume: bool) -> None:
        if not resume:
            import shutil

            shutil.rmtree(self.batch_dir, ignore_errors=True)
            shutil.rmtree(self._completed_dir, ignore_errors=True)
            self.batch_dir.mkdir(parents=True, exist_ok=True)

    def stage(self, batch_id: str, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        self.batch_dir.mkdir(parents=True, exist_ok=True)
        safe_id = "".join(character if character.isalnum() or character in "-_" else "_" for character in batch_id)
        batch_path = self.batch_dir / f"{safe_id}.jsonl"
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{batch_path.name}.",
            suffix=".tmp",
            dir=self.batch_dir,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for record in records:
                    json.dump({**record, "batch_id": batch_id}, handle, sort_keys=True)
                    handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, batch_path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    def rollback_batch(self, batch_id: str) -> None:
        safe_id = "".join(character if character.isalnum() or character in "-_" else "_" for character in batch_id)
        (self.batch_dir / f"{safe_id}.jsonl").unlink(missing_ok=True)
        try:
            self.batch_dir.rmdir()
        except OSError:
            pass

    def finalize(self) -> None:
        if not self.batch_dir.exists() and self.path.exists():
            return
        batch_paths = sorted(self.batch_dir.glob("*.jsonl"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        try:
            with os.fdopen(fd, "wb") as destination:
                for batch_path in batch_paths:
                    with batch_path.open("rb") as source:
                        while chunk := source.read(64 * 1024):
                            destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temporary_name, self.path)
            import shutil

            os.replace(self.batch_dir, self._completed_dir)
            shutil.rmtree(self._completed_dir)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise

    @property
    def _completed_dir(self) -> Path:
        return Path(f"{self.batch_dir}.complete")


@contextmanager
def _signal_cancellation(token: CancellationToken) -> Iterator[None]:
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    previous_handlers: dict[signal.Signals, Any] = {}

    def request_cancel(signum: int, frame: Any) -> None:
        del signum, frame
        token.cancel()

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, request_cancel)
        yield
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def _fsync_directory(directory: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rollback_batch(
    components: list[tuple[str, Any]],
    dead_letters: _DeadLetterWriter | None,
    batch_id: str,
    error: Exception,
) -> None:
    for _, component in components:
        rollback_batch = getattr(component, "rollback_batch", None)
        if callable(rollback_batch):
            try:
                rollback_batch(batch_id)
            except Exception as rollback_error:  # noqa: BLE001
                error.add_note(f"Batch rollback failed: {rollback_error}")
    if dead_letters is not None:
        try:
            dead_letters.rollback_batch(batch_id)
        except Exception as rollback_error:  # noqa: BLE001
            error.add_note(f"Dead-letter rollback failed: {rollback_error}")
