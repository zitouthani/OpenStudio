from __future__ import annotations

import csv
import itertools
import json
import os
import queue
import shutil
import signal
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .checkpoint import Checkpoint, atomic_write_text
from .errors import FatalError, PipelineError, RetryableError, SkippableError
from .metrics import Metrics
from .sinks import CsvPartSink, write_dead_letters

Row = Dict[str, Any]
RecordTransform = Callable[[Row], Optional[Row]]

STAGES = ("reader_to_transform", "transform_to_writer")
_END = object()


class _Aborted(Exception):
    pass


@dataclass
class PipelineBatch:
    batch_id: int
    rows: List[Row] = field(default_factory=list)
    rejects: List[Dict[str, Any]] = field(default_factory=list)
    records_in: int = 0
    filtered: int = 0


@dataclass
class RunResult:
    status: str  # "completed" | "cancelled"
    metrics: Metrics
    checkpoint: Checkpoint


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()


class Pipeline:
    """Bounded, resumable, cancellable CSV -> transform -> CSV pipeline.

    See docs/adr/phase3-execution-model.md for the execution model.
    """

    def __init__(
        self,
        input_path: str | os.PathLike,
        output_path: str | os.PathLike,
        work_dir: str | os.PathLike,
        transform: Optional[RecordTransform] = None,
        batch_size: int = 1000,
        queue_maxsize: int = 2,
        max_retries: int = 3,
        backoff_base: float = 0.05,
        backoff_max: float = 2.0,
        delimiter: str = ",",
        sink: Any = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if queue_maxsize < 1:
            raise ValueError("queue_maxsize must be >= 1")
        self.input_path = Path(input_path)
        self.output_path = Path(output_path)
        self.work_dir = Path(work_dir)
        self.transform = transform
        self.batch_size = batch_size
        self.queue_maxsize = queue_maxsize
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.delimiter = delimiter
        self._sleep = sleep
        self.parts_dir = self.work_dir / "parts"
        self.dead_letter_dir = self.work_dir / "dead_letter"
        self.checkpoint_path = self.work_dir / "checkpoint.json"
        self.metrics_path = self.work_dir / "metrics.prom"
        self.sink = sink if sink is not None else CsvPartSink(self.parts_dir)
        self.token = CancelToken()
        self.metrics = Metrics(STAGES)
        self._abort = threading.Event()
        self._errors: List[BaseException] = []
        self._err_lock = threading.Lock()
        self._reader_done = False
        self._checkpoint: Checkpoint

    # -- public API -------------------------------------------------------
    def cancel(self) -> None:
        self.token.cancel()

    def read_dead_letters(self) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        if self.dead_letter_dir.exists():
            for path in sorted(self.dead_letter_dir.glob("batch-*.jsonl")):
                with open(path, encoding="utf-8") as handle:
                    records.extend(json.loads(line) for line in handle)
        return records

    def run(self, resume: bool = False) -> RunResult:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        fingerprint = {
            "input_path": str(self.input_path.resolve()),
            "input_size": self.input_path.stat().st_size,
            "batch_size": self.batch_size,
            "delimiter": self.delimiter,
        }
        checkpoint = Checkpoint.load(self.checkpoint_path) if resume else None
        if checkpoint is None:
            for sub in (self.parts_dir, self.dead_letter_dir):
                shutil.rmtree(sub, ignore_errors=True)
            self.checkpoint_path.unlink(missing_ok=True)
            self.parts_dir.mkdir(parents=True, exist_ok=True)
            checkpoint = Checkpoint(fingerprint=fingerprint)
        else:
            if checkpoint.fingerprint != fingerprint:
                raise PipelineError("Checkpoint does not match this job (input or batch_size changed).")
            for sub in (self.parts_dir, self.dead_letter_dir):
                for stale in sub.glob("*.tmp") if sub.exists() else []:
                    stale.unlink(missing_ok=True)
            if checkpoint.status == "completed":
                return RunResult("completed", self.metrics, checkpoint)
        checkpoint.status = "running"
        self._checkpoint = checkpoint
        m = self.metrics
        m.batches_processed = checkpoint.batches
        m.records_in = checkpoint.records_in
        m.records_out = checkpoint.records_out
        m.records_rejected = checkpoint.records_rejected
        m.records_filtered = checkpoint.records_filtered

        q1: queue.Queue = queue.Queue(maxsize=self.queue_maxsize)
        q2: queue.Queue = queue.Queue(maxsize=self.queue_maxsize)
        threads = [
            threading.Thread(target=self._guard, args=(self._reader, q1, checkpoint.last_committed_batch + 1), name="reader"),
            threading.Thread(target=self._guard, args=(self._transformer, q1, q2), name="transform"),
            threading.Thread(target=self._guard, args=(self._writer, q2), name="writer"),
        ]
        restore = self._install_signal_handlers()
        try:
            for t in threads:
                t.start()
            for t in threads:
                while t.is_alive():
                    t.join(0.1)
        finally:
            restore()

        try:
            if self._errors:
                m.batches_failed += 1
                checkpoint.status = "failed"
                checkpoint.save(self.checkpoint_path)
                raise PipelineError(f"Pipeline aborted: {self._errors[0]!r}") from self._errors[0]
            if self._reader_done:
                self._finalize(checkpoint)
                checkpoint.status = "completed"
                checkpoint.save(self.checkpoint_path)
                for stale in self.parts_dir.glob("part-*.csv"):
                    stale.unlink(missing_ok=True)
                status = "completed"
            else:
                checkpoint.status = "cancelled"
                checkpoint.save(self.checkpoint_path)
                status = "cancelled"
            return RunResult(status, m, checkpoint)
        finally:
            m.finish()
            atomic_write_text(self.metrics_path, m.to_prometheus())

    # -- plumbing ---------------------------------------------------------
    def _install_signal_handlers(self) -> Callable[[], None]:
        if threading.current_thread() is not threading.main_thread():
            return lambda: None
        previous = {}

        def handler(signum: int, frame: Any) -> None:
            self.token.cancel()

        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, handler)

        def restore() -> None:
            for sig, old in previous.items():
                signal.signal(sig, old)

        return restore

    def _guard(self, fn: Callable[..., None], *args: Any) -> None:
        try:
            fn(*args)
        except _Aborted:
            pass
        except BaseException as exc:  # noqa: BLE001 - report any stage failure
            with self._err_lock:
                self._errors.append(exc)
            self._abort.set()

    def _put(self, q: queue.Queue, stage: str, item: Any) -> None:
        while True:
            if self._abort.is_set():
                raise _Aborted
            try:
                q.put(item, timeout=0.02)
                self.metrics.observe_queue(stage, q.qsize())
                return
            except queue.Full:
                continue

    def _get(self, q: queue.Queue, stage: str) -> Any:
        while True:
            if self._abort.is_set():
                raise _Aborted
            try:
                item = q.get(timeout=0.02)
                self.metrics.observe_queue(stage, q.qsize())
                return item
            except queue.Empty:
                continue

    def _retry(self, fn: Callable[[], Any], retry_on: tuple = (RetryableError,)) -> Any:
        attempt = 0
        while True:
            try:
                return fn()
            except retry_on as exc:
                if attempt >= self.max_retries:
                    raise FatalError(f"retries exhausted: {exc!r}") from exc
                attempt += 1
                self.metrics.incr("batches_retried")
                self._sleep(min(self.backoff_max, self.backoff_base * 2 ** (attempt - 1)))

    # -- stages -----------------------------------------------------------
    def _reader(self, out: queue.Queue, start_batch: int) -> None:
        with open(self.input_path, newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle, delimiter=self.delimiter)
            header = next(reader, None)
            if header is None:
                self._reader_done = True
                self._put(out, STAGES[0], _END)
                return
            skip = start_batch * self.batch_size
            consumed = sum(1 for _ in itertools.islice(reader, skip))
            batch_id, index = start_batch, skip
            if consumed <= skip - self.batch_size and start_batch > 0:
                raise FatalError("Input is shorter than the checkpoint expects.")
            while not self.token.is_set():
                chunk = list(itertools.islice(reader, self.batch_size))
                if not chunk:
                    self._reader_done = True
                    break
                batch = PipelineBatch(batch_id=batch_id, records_in=len(chunk))
                for offset, rec in enumerate(chunk):
                    if len(rec) != len(header):
                        batch.rejects.append(
                            {
                                "batch_id": batch_id,
                                "record_index": index + offset,
                                "reason": f"malformed record: expected {len(header)} fields, got {len(rec)}",
                                "record": rec,
                            }
                        )
                    else:
                        batch.rows.append(dict(zip(header, rec)))
                del chunk
                self.metrics.incr("batches_read")
                self._put(out, STAGES[0], batch)
                batch_id += 1
                index += self.batch_size
            self._put(out, STAGES[0], _END)

    def _transform_batch(self, batch: PipelineBatch) -> PipelineBatch:
        if self.transform is None:
            return batch
        rows: List[Row] = []
        rejects = list(batch.rejects)
        for position, row in enumerate(batch.rows):
            try:
                result = self.transform(dict(row))
            except SkippableError as exc:
                rejects.append(
                    {"batch_id": batch.batch_id, "record_index": None, "position_in_batch": position, "reason": str(exc), "record": row}
                )
                continue
            if result is not None:
                rows.append(result)
        return PipelineBatch(
            batch_id=batch.batch_id,
            rows=rows,
            rejects=rejects,
            records_in=batch.records_in,
        )

    def _transformer(self, inp: queue.Queue, out: queue.Queue) -> None:
        while True:
            item = self._get(inp, STAGES[0])
            if item is _END:
                self._put(out, STAGES[1], _END)
                return
            result = self._retry(lambda: self._transform_batch(item))
            result.filtered = result.records_in - len(result.rows) - len(result.rejects)
            self._put(out, STAGES[1], result)

    def _writer(self, inp: queue.Queue) -> None:
        cp = self._checkpoint
        while True:
            item = self._get(inp, STAGES[1])
            if item is _END:
                return
            self._retry(lambda: self.sink.write(item.batch_id, item.rows), (RetryableError, OSError))
            if item.rejects:
                self._retry(
                    lambda: write_dead_letters(self.dead_letter_dir, item.batch_id, item.rejects),
                    (RetryableError, OSError),
                )
            # Commit point: output and dead letters are fully written.
            cp.last_committed_batch = item.batch_id
            cp.batches += 1
            cp.records_in += item.records_in
            cp.records_out += len(item.rows)
            cp.records_rejected += len(item.rejects)
            cp.records_filtered += item.filtered
            self._retry(lambda: cp.save(self.checkpoint_path), (OSError,))
            m = self.metrics
            m.incr("batches_processed")
            m.incr("records_in", item.records_in)
            m.incr("records_out", len(item.rows))
            m.incr("records_rejected", len(item.rejects))
            m.incr("records_filtered", item.filtered)

    # -- finalisation -----------------------------------------------------
    def _finalize(self, cp: Checkpoint) -> None:
        """Assemble the output from committed parts only; safe to repeat."""
        tmp = self.output_path.with_name(self.output_path.name + ".tmp")
        header: Optional[List[str]] = None
        try:
            with open(tmp, "w", newline="", encoding="utf-8") as out_handle:
                writer = csv.writer(out_handle)
                for batch_id in range(cp.last_committed_batch + 1):
                    part = self.sink.part_path(batch_id)
                    with open(part, newline="", encoding="utf-8") as in_handle:
                        reader = csv.reader(in_handle)
                        part_header = next(reader, None)
                        if part_header is None:
                            continue
                        if header is None:
                            header = part_header
                            writer.writerow(header)
                        elif part_header != header:
                            raise FatalError(f"Inconsistent columns in batch {batch_id}")
                        writer.writerows(reader)
                out_handle.flush()
                os.fsync(out_handle.fileno())
            os.replace(tmp, self.output_path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
