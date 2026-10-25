"""Benchmark + peak-RSS profile of Phase 2 (execute_graph) vs Phase 3 (Pipeline).

Each measurement runs in a fresh subprocess so ru_maxrss is per-run.

    python benchmarks/run_benchmark.py --rows 500000 --write-baseline
"""
from __future__ import annotations

import argparse
import json
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=500_000)
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        src = tmp / "in.csv"
        make_input(src, args.rows)
        result = {
            "rows": args.rows,
            "input_mb": round(src.stat().st_size / 2**20, 1),
            "phase2": measure("phase2", src, tmp),
            "phase3": measure("phase3", src, tmp),
        }
    print(json.dumps(result, indent=2))
    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
