from __future__ import annotations

import sys
import threading
import time
from typing import Dict


def peak_rss_bytes() -> int:
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024


class Metrics:
    """Thread-safe run metrics with Prometheus text export."""

    def __init__(self, stages: tuple[str, ...]) -> None:
        self._lock = threading.Lock()
        self._start = time.monotonic()
        self._end: float | None = None
        self.batches_processed = 0
        self.batches_failed = 0
        self.batches_retried = 0
        self.batches_read = 0
        self.records_in = 0
        self.records_out = 0
        self.records_rejected = 0
        self.records_filtered = 0
        self.queue_depth: Dict[str, int] = {s: 0 for s in stages}
        self.queue_depth_max: Dict[str, int] = {s: 0 for s in stages}

    def incr(self, name: str, amount: int = 1) -> None:
        with self._lock:
            setattr(self, name, getattr(self, name) + amount)

    def observe_queue(self, stage: str, depth: int) -> None:
        with self._lock:
            self.queue_depth[stage] = depth
            if depth > self.queue_depth_max[stage]:
                self.queue_depth_max[stage] = depth

    def finish(self) -> None:
        self._end = time.monotonic()

    @property
    def elapsed_seconds(self) -> float:
        return (self._end or time.monotonic()) - self._start

    @property
    def throughput(self) -> float:
        elapsed = self.elapsed_seconds
        return self.records_out / elapsed if elapsed > 0 else 0.0

    def to_prometheus(self) -> str:
        with self._lock:
            lines = []

            def add(name: str, kind: str, value: float, labels: str = "") -> None:
                if not any(line.startswith(f"# TYPE openstudio_{name} ") for line in lines):
                    lines.append(f"# TYPE openstudio_{name} {kind}")
                lines.append(f"openstudio_{name}{labels} {value}")

            add("batches_processed_total", "counter", self.batches_processed)
            add("batches_failed_total", "counter", self.batches_failed)
            add("batches_retried_total", "counter", self.batches_retried)
            add("records_in_total", "counter", self.records_in)
            add("records_out_total", "counter", self.records_out)
            add("records_rejected_total", "counter", self.records_rejected)
            add("records_filtered_total", "counter", self.records_filtered)
            for stage, depth in self.queue_depth.items():
                add("queue_depth", "gauge", depth, f'{{stage="{stage}"}}')
            for stage, depth in self.queue_depth_max.items():
                add("queue_depth_max", "gauge", depth, f'{{stage="{stage}"}}')
            add("throughput_records_per_second", "gauge", round(self.throughput, 3))
            add("peak_memory_bytes", "gauge", peak_rss_bytes())
            add("elapsed_seconds", "gauge", round(self.elapsed_seconds, 3))
            return "\n".join(lines) + "\n"
