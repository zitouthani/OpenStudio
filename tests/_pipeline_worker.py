"""Subprocess entry point used by the crash-recovery and memory tests."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline import Pipeline, SkippableError  # noqa: E402
from src.pipeline.metrics import peak_rss_bytes  # noqa: E402


def make_transform(delay: float, batch_size: int):
    def transform(row):
        if delay and int(row["id"]) % batch_size == 0:
            time.sleep(delay)
        if int(row["id"]) % 97 == 0:
            raise SkippableError("id divisible by 97")
        row["double"] = str(int(row["amount"]) * 2)
        return row

    return transform


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("work")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    pipeline = Pipeline(
        args.input,
        args.output,
        args.work,
        transform=make_transform(args.delay, args.batch_size),
        batch_size=args.batch_size,
    )
    result = pipeline.run(resume=args.resume)
    print(
        json.dumps(
            {
                "status": result.status,
                "records_out": result.metrics.records_out,
                "peak_rss": peak_rss_bytes(),
                "throughput": result.metrics.throughput,
            }
        )
    )


if __name__ == "__main__":
    main()
