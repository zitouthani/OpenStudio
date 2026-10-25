"""Large-input memory, kill -9 crash recovery and CI performance regression tests."""
from __future__ import annotations

import json
import os
import random
import resource
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.pipeline import Pipeline
from tests._pipeline_worker import make_transform
from tests.pipeline_helpers import fingerprint, read_ids, write_input

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "tests" / "_pipeline_worker.py"

MEMORY_LIMIT_MB = 80  # hard address-space cap enforced with RLIMIT_AS
DATASET_FACTOR = 2  # dataset is at least this many times the memory limit
PEAK_RSS_TARGET_MB = 60


def worker(*args: str, limit_mb: int | None = None, **kw) -> subprocess.CompletedProcess:
    def limit() -> None:
        if limit_mb:
            cap = limit_mb * 2**20
            resource.setrlimit(resource.RLIMIT_AS, (cap, cap))

    return subprocess.run(
        [sys.executable, str(WORKER), *args], capture_output=True, text=True, preexec_fn=limit, **kw
    )


def test_large_input_runs_under_hard_memory_limit(tmp_path):
    src = tmp_path / "big.csv"
    write_input(src, 1_000, pad=0)
    # grow the file to DATASET_FACTOR x the memory limit
    target = DATASET_FACTOR * MEMORY_LIMIT_MB * 2**20
    with open(src, "a", encoding="utf-8") as handle:
        i = 1_001
        while src.stat().st_size < target:
            handle.write("".join(f"{j},name{j}{'x' * 40},{j % 1000}\r\n" for j in range(i, i + 50_000)))
            handle.flush()
            i += 50_000
    total = i - 1 if src.stat().st_size >= target else 1000
    out = tmp_path / "out.csv"
    proc = worker(str(src), str(out), str(tmp_path / "w"), "--batch-size", "1000", limit_mb=MEMORY_LIMIT_MB)
    assert proc.returncode == 0, proc.stderr[-2000:]
    stats = json.loads(proc.stdout.strip().splitlines()[-1])
    assert src.stat().st_size >= DATASET_FACTOR * MEMORY_LIMIT_MB * 2**20
    assert stats["peak_rss"] / 2**20 <= PEAK_RSS_TARGET_MB
    assert stats["status"] == "completed"
    # 1/97 of the ids are dead-lettered by the worker transform
    rejected = total // 97
    assert stats["records_out"] == total - rejected
    # Phase 2 cannot do this under the same cap
    from_phase2 = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "from src.components.csv_reader import CSVReader;"
            "CSVReader(sys.argv[2]).process([])",
            str(ROOT),
            str(src),
        ],
        capture_output=True,
        preexec_fn=lambda: resource.setrlimit(
            resource.RLIMIT_AS, (MEMORY_LIMIT_MB * 2**20, MEMORY_LIMIT_MB * 2**20)
        ),
    )
    assert from_phase2.returncode != 0


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_kill9_crash_recovery_matches_uninterrupted_run(tmp_path, seed):
    rng = random.Random(seed)
    rows, batch = 20_000, 200
    src = write_input(tmp_path / "in.csv", rows)
    ref_out = tmp_path / "ref.csv"
    Pipeline(src, ref_out, tmp_path / "ref_w", transform=make_transform(0, batch), batch_size=batch).run()
    ref = fingerprint(ref_out)

    out, work = tmp_path / "out.csv", tmp_path / "w"
    kills = 0
    for attempt in range(3):
        args = [sys.executable, str(WORKER), str(src), str(out), str(work), "--batch-size", str(batch), "--delay", "0.01"]
        if attempt:
            args.append("--resume")
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(rng.uniform(0.4, 1.0))
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGKILL)
            kills += 1
        proc.wait()
    assert kills >= 1
    final = worker(str(src), str(out), str(work), "--batch-size", str(batch), "--resume")
    assert final.returncode == 0, final.stderr[-2000:]
    assert fingerprint(out) == ref
    ids = read_ids(out)
    assert len(ids) == len(set(ids)) == ref[0]
    dead = sorted(p.read_text() for p in (work / "dead_letter").glob("*.jsonl"))
    ref_dead = sorted(p.read_text() for p in (tmp_path / "ref_w" / "dead_letter").glob("*.jsonl"))
    assert dead == ref_dead


def test_throughput_regression_against_phase2_baseline(tmp_path):
    baseline = json.loads((ROOT / "tests" / "perf" / "phase2_baseline.json").read_text())
    src = write_input(tmp_path / "in.csv", 100_000, pad=40)
    p = Pipeline(src, tmp_path / "o.csv", tmp_path / "w", transform=make_transform(0, 1000), batch_size=1000)
    m = p.run().metrics
    # Phase 3 trades speed for bounded memory; fail only on a gross regression
    # (CI runners are noisy): at least 25% of recorded Phase 2 throughput.
    assert m.throughput >= 0.25 * baseline["phase2"]["records_per_second"]
    assert baseline["phase3"]["peak_rss_mb"] < baseline["phase2"]["peak_rss_mb"]
