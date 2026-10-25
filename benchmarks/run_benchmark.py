"""Benchmark + peak-RSS profile of Phase 2 (execute_graph) vs Phase 3 (Pipeline).

Each measurement runs in a fresh subprocess so ru_maxrss is per-run.

    python benchmarks/run_benchmark.py --rows 500000 --runs 7 --write-baseline

Phase 2 is a full ``execute_graph`` run (CSVReader -> TransformComponent -> CSVWriter) and Phase 3 a
full ``Pipeline`` run on the same file. Each is repeated ``--runs`` times (runs alternate between the
two modes to share machine noise); median, min, max and relative spread are recorded.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASELINE = ROOT / "tests" / "perf" / "phase2_baseline.json"

CHILD = r"""
import json, sys, time
sys.path.insert(0, sys.argv[1])
mode, src, out, work = sys.argv[2:6]
from src.pipeline.metrics import peak_rss_bytes
def f(row):
    row["double"] = str(int(row["amount"]) * 2)
    return row
start = time.monotonic()
if mode == "phase2":
    from src.components.csv_reader import CSVReader
    from src.components.csv_writer import CSVWriter
    from src.components.transform import TransformComponent
    from src.engine.graph import ExecutionGraph
    from src.engine.runtime import execute_graph
    g = ExecutionGraph()
    g.add_component("r", CSVReader(src)); g.add_component("t", TransformComponent(f)); g.add_component("w", CSVWriter(out))
    n = len(execute_graph(g, []))
else:
    from src.pipeline import Pipeline
    n = Pipeline(src, out, work, transform=f, batch_size=int(sys.argv[6])).run().metrics.records_out
el = time.monotonic() - start
print(json.dumps({"records": n, "seconds": el, "records_per_second": n / el, "peak_rss_mb": peak_rss_bytes() / 2**20}))
"""


def make_input(path: Path, rows: int) -> None:
    sys.path.insert(0, str(ROOT))
    from tests.pipeline_helpers import write_input

    write_input(path, rows, pad=40)


def measure(mode: str, src: Path, tmp: Path, batch_size: int = 1000) -> dict:
    out = subprocess.run(
        [sys.executable, "-c", CHILD, str(ROOT), mode, str(src), str(tmp / f"{mode}.csv"), str(tmp / f"{mode}_work"), str(batch_size)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout.strip().splitlines()[-1])


def summarize(samples: list[dict]) -> dict:
    rps = [x["records_per_second"] for x in samples]
    med = statistics.median(rps)
    return {
        "records": samples[0]["records"],
        "runs": len(samples),
        "records_per_second_runs": [round(v, 1) for v in rps],
        "records_per_second": med,
        "records_per_second_min": min(rps),
        "records_per_second_max": max(rps),
        "spread_pct": round((max(rps) - min(rps)) / med * 100, 1),
        "seconds": statistics.median(x["seconds"] for x in samples),
        "peak_rss_mb": statistics.median(x["peak_rss_mb"] for x in samples),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=500_000)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        src = tmp / "in.csv"
        make_input(src, args.rows)
        samples: dict[str, list[dict]] = {"phase2": [], "phase3": []}
        for _ in range(args.runs):
            for mode in samples:
                samples[mode].append(measure(mode, src, tmp))
        result = {
            "rows": args.rows,
            "input_mb": round(src.stat().st_size / 2**20, 1),
            "phase2": summarize(samples["phase2"]),
            "phase3": summarize(samples["phase3"]),
        }
    print(json.dumps(result, indent=2))
    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
