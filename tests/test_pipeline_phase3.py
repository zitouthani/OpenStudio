from __future__ import annotations

import csv
import tempfile
import threading
import time
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from src.pipeline import (
    CsvPartSink,
    FatalError,
    Pipeline,
    PipelineError,
    RetryableError,
    SkippableError,
)
from tests.pipeline_helpers import fingerprint, read_ids, write_input


def double(row):
    row["double"] = str(int(row["amount"]) * 2)
    return row


def run_reference(tmp_path: Path, src: Path, batch_size: int, transform=double) -> Path:
    out = tmp_path / "ref.csv"
    Pipeline(src, out, tmp_path / "ref_work", transform=transform, batch_size=batch_size).run()
    return out


# ---- batching / metrics -------------------------------------------------
def test_output_matches_input_and_metrics(tmp_path):
    src = write_input(tmp_path / "in.csv", 1050)
    out = tmp_path / "out.csv"
    p = Pipeline(src, out, tmp_path / "w", transform=double, batch_size=100)
    result = p.run()
    assert result.status == "completed"
    assert read_ids(out) == [str(i) for i in range(1, 1051)]
    m = result.metrics
    assert (m.batches_processed, m.records_in, m.records_out, m.records_rejected) == (11, 1050, 1050, 0)
    assert m.throughput > 0
    prom = (tmp_path / "w" / "metrics.prom").read_text()
    assert "openstudio_records_in_total 1050" in prom
    assert 'openstudio_queue_depth{stage="reader_to_transform"}' in prom
    assert "openstudio_peak_memory_bytes" in prom
    assert "openstudio_elapsed_seconds" in prom


def test_empty_input_and_idempotent_rerun(tmp_path):
    src = write_input(tmp_path / "in.csv", 0)
    out = tmp_path / "out.csv"
    assert Pipeline(src, out, tmp_path / "w").run().status == "completed"
    assert out.exists()


# ---- backpressure -------------------------------------------------------
def test_bounded_queues_block_producer_under_slow_consumer(tmp_path):
    src = write_input(tmp_path / "in.csv", 400)
    gate = threading.Event()
    seen = []

    class SlowSink(CsvPartSink):
        def write(self, batch_id, rows):
            seen.append(batch_id)
            gate.wait(5)
            super().write(batch_id, rows)

    p = Pipeline(src, tmp_path / "o.csv", tmp_path / "w", batch_size=10, queue_maxsize=2, sink=SlowSink(tmp_path / "w" / "parts"))
    t = threading.Thread(target=p.run)
    t.start()
    time.sleep(0.5)
    # 40 batches exist; with the writer stuck the reader may only be a bounded
    # number of batches ahead: 1 in writer + 2 + 1 in transform + 2 + 1 in reader.
    assert p.metrics.batches_read <= 2 + 2 + 3
    assert p.metrics.batches_read < 40
    gate.set()
    t.join(30)
    assert p.metrics.batches_read == 40
    assert max(p.metrics.queue_depth_max.values()) <= 2


# ---- fault injection ----------------------------------------------------
def test_malformed_and_skippable_records_dead_lettered(tmp_path):
    src = tmp_path / "in.csv"
    src.write_text("id,name,amount\n1,a,1\n2,b\n3,c,3\n4,d,4,extra\n5,e,5\n")

    def reject_three(row):
        if row["id"] == "3":
            raise SkippableError("three is bad")
        return row

    p = Pipeline(src, tmp_path / "o.csv", tmp_path / "w", transform=reject_three, batch_size=2)
    r = p.run()
    assert read_ids(tmp_path / "o.csv") == ["1", "5"]
    dead = p.read_dead_letters()
    assert sorted((d["batch_id"], d["reason"].split(":")[0]) for d in dead) == [
        (0, "malformed record"),
        (1, "malformed record"),
        (1, "three is bad"),
    ]
    assert [d["record_index"] for d in dead if "malformed" in d["reason"]] == [1, 3]
    m = r.metrics
    assert (m.records_in, m.records_out, m.records_rejected) == (5, 2, 3)


def test_retryable_transform_error_is_retried(tmp_path):
    src = write_input(tmp_path / "in.csv", 30)
    calls = {"n": 0}

    def flaky(row):
        if row["id"] == "15" and calls["n"] < 2:
            calls["n"] += 1
            raise RetryableError("blip")
        return row

    sleeps = []
    p = Pipeline(src, tmp_path / "o.csv", tmp_path / "w", transform=flaky, batch_size=10, sleep=sleeps.append)
    r = p.run()
    assert r.metrics.batches_retried == 2
    assert sleeps == [0.05, 0.1]  # exponential backoff
    assert len(read_ids(tmp_path / "o.csv")) == 30


def test_exception_in_batch_is_fatal_and_leaves_no_partial_output(tmp_path):
    src = write_input(tmp_path / "in.csv", 50)

    def boom(row):
        if row["id"] == "25":
            raise ZeroDivisionError("bug")
        return row

    work = tmp_path / "w"
    p = Pipeline(src, tmp_path / "o.csv", work, transform=boom, batch_size=10)
    with pytest.raises(PipelineError):
        p.run()
    assert not (tmp_path / "o.csv").exists()
    parts = sorted(x.name for x in (work / "parts").iterdir())
    assert set(parts) <= {"part-00000000.csv", "part-00000001.csv"}  # batch 2 (ids 21-30) left nothing
    # fix the bug and resume: result equals the reference
    p2 = Pipeline(src, tmp_path / "o.csv", work, transform=lambda r: r, batch_size=10)
    p2.run(resume=True)
    ref = run_reference(tmp_path, src, 10, transform=lambda r: r)
    assert fingerprint(tmp_path / "o.csv") == fingerprint(ref)


def test_downstream_write_failure_rolls_back_batch(tmp_path):
    src = write_input(tmp_path / "in.csv", 40)
    work = tmp_path / "w"

    class PartialWriteSink(CsvPartSink):
        fail = True

        def _write_tmp(self, tmp, rows):
            super()._write_tmp(tmp, rows[: len(rows) // 2])  # partial data hits disk
            if self.fail and rows and rows[0]["id"] == "21":
                raise OSError("disk full")
            super()._write_tmp(tmp, rows)

    sink = PartialWriteSink(work / "parts")
    p = Pipeline(src, tmp_path / "o.csv", work, batch_size=10, sink=sink, max_retries=2, sleep=lambda s: None)
    with pytest.raises(PipelineError):
        p.run()
    names = sorted(x.name for x in (work / "parts").iterdir())
    assert names == ["part-00000000.csv", "part-00000001.csv"]
    assert not any(n.endswith(".tmp") for n in names)
    assert p.metrics.batches_retried == 2
    assert not (tmp_path / "o.csv").exists()
    sink.fail = False
    Pipeline(src, tmp_path / "o.csv", work, batch_size=10, sink=sink).run(resume=True)
    assert read_ids(tmp_path / "o.csv") == [str(i) for i in range(1, 41)]


def test_checkpoint_mismatch_is_refused(tmp_path):
    src = write_input(tmp_path / "in.csv", 30)
    Pipeline(src, tmp_path / "o.csv", tmp_path / "w", batch_size=10).run()
    with pytest.raises(PipelineError):
        Pipeline(src, tmp_path / "o.csv", tmp_path / "w", batch_size=5).run(resume=True)


# ---- cancellation -------------------------------------------------------
def test_cancel_mid_run_then_resume_equals_reference(tmp_path):
    src = write_input(tmp_path / "in.csv", 1000)
    out = tmp_path / "o.csv"
    holder = {}

    def cancelling(row):
        if row["id"] == "350":
            holder["p"].cancel()
        return double(row)

    p = Pipeline(src, out, tmp_path / "w", transform=cancelling, batch_size=100)
    holder["p"] = p
    r = p.run()
    assert r.status == "cancelled"
    assert not out.exists()
    committed = r.checkpoint.last_committed_batch
    assert 3 <= committed < 9
    assert r.checkpoint.status == "cancelled"
    r2 = Pipeline(src, out, tmp_path / "w", transform=double, batch_size=100).run(resume=True)
    assert r2.status == "completed"
    assert r2.metrics.records_out == 1000
    assert fingerprint(out) == fingerprint(run_reference(tmp_path, src, 100))
    assert len(set(read_ids(out))) == 1000


def test_sigterm_triggers_clean_cancel(tmp_path):
    import os
    import signal

    src = write_input(tmp_path / "in.csv", 2000)

    def slow(row):
        if row["id"] == "100":
            os.kill(os.getpid(), signal.SIGTERM)
        return row

    p = Pipeline(src, tmp_path / "o.csv", tmp_path / "w", transform=slow, batch_size=50)
    r = p.run()
    assert r.status == "cancelled"
    assert r.checkpoint.last_committed_batch < 39


# ---- property based -----------------------------------------------------
@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    n=st.integers(0, 120),
    batch_size=st.integers(1, 17),
    interrupt=st.integers(0, 130),
    mode=st.sampled_from(["cancel", "fatal"]),
)
def test_any_interruption_point_resumes_to_same_result(n, batch_size, interrupt, mode):
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        src = write_input(tmp / "in.csv", n)
        ref = run_reference(tmp, src, batch_size)
        out = tmp / "o.csv"
        holder = {}

        def interrupting(row):
            if int(row["id"]) == interrupt:
                if mode == "cancel":
                    holder["p"].cancel()
                else:
                    raise FatalError("simulated crash")
            return double(row)

        p = Pipeline(src, out, tmp / "w", transform=interrupting, batch_size=batch_size)
        holder["p"] = p
        try:
            p.run()
        except PipelineError:
            pass
        Pipeline(src, out, tmp / "w", transform=double, batch_size=batch_size).run(resume=True)
        assert fingerprint(out) == fingerprint(ref)
        ids = read_ids(out)
        assert ids == [str(i) for i in range(1, n + 1)]


@settings(max_examples=40, deadline=None)
@given(n=st.integers(0, 200), batch_size=st.integers(1, 25))
def test_batch_ids_are_stable_and_contiguous(n, batch_size):
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        src = write_input(tmp / "in.csv", n)
        r = Pipeline(src, tmp / "o.csv", tmp / "w", batch_size=batch_size).run()
        expected_batches = -(-n // batch_size)
        assert r.checkpoint.last_committed_batch == expected_batches - 1
        assert r.checkpoint.batches == expected_batches
