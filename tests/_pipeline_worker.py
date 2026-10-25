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


def install_kill(spec: str) -> None:
    """SIGKILL this process at the Nth hit of a fault point, e.g. ``checkpoint-write:5``.

    Points: ``checkpoint-write`` (tmp checkpoint half written, before fsync), ``checkpoint-rename``
    (before os.replace of checkpoint.json), ``part-rename`` (before os.replace of a part file),
    ``final-rename`` (before os.replace of the final output).
    """
    import os
    import signal

    point, _, nth = spec.partition(":")
    remaining = [int(nth or 1)]
    real_replace, real_fsync = os.replace, os.fsync

    def hit() -> None:
        remaining[0] -= 1
        if remaining[0] == 0:
            os.kill(os.getpid(), signal.SIGKILL)

    def replace(src, dst, *a, **kw):
        name = os.path.basename(str(dst))
        if (
            (point == "checkpoint-rename" and name == "checkpoint.json")
            or (point == "part-rename" and name.startswith("part-"))
            or (point == "final-rename" and name.endswith(".csv") and not name.startswith("part-"))
        ):
            hit()
        return real_replace(src, dst, *a, **kw)

    def fsync(fd):
        if point == "checkpoint-write" and os.readlink(f"/proc/self/fd/{fd}").endswith("checkpoint.json.tmp"):
            if remaining[0] == 1:
                os.ftruncate(fd, os.fstat(fd).st_size // 2)  # leave a torn temp file behind
            hit()
        return real_fsync(fd)

    os.replace, os.fsync = replace, fsync


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("work")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--kill-at")
    args = parser.parse_args()
    if args.kill_at:
        install_kill(args.kill_at)
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
