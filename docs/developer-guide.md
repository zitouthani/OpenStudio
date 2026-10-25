# Developer Guide

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements/dev.txt
```

## Testing

```bash
pytest
```

## Linting

```bash
ruff check src tests
```

## Phase workflow

- Phase instructions live under `.github/phases/`.
- GitHub Actions workflows are under `.github/workflows/`.
- Keep branch scope narrow and feature-driven.
- Update README and relevant docs whenever the user-facing workflow changes.

## Phase 3 pipeline (`src/pipeline`)

`Pipeline(input, output, work_dir, transform=..., batch_size=...)` runs a bounded, resumable, cancellable
CSV pipeline; `run(resume=True)` continues from the last committed batch and `cancel()` (or SIGINT/SIGTERM)
shuts down cleanly. Phase 2 `execute_graph` is unchanged. See `docs/adr/phase3-execution-model.md`.
Benchmark: `python benchmarks/run_benchmark.py --rows 500000`.

### Known limits of the Phase 3 pipeline

- CSV → CSV only.
- Per-record transforms only (no joins, aggregations or cross-record state).
- Not wired into `ExecutionGraph`; integration is tracked in a separate issue.

### Verification record

Full suite (37 tests, including the slow robustness tests) after the follow-up changes: `37 passed in 70.92s`.
CI runs for the Phase 3 PR (#16) all ended `action_required` (workflow approval pending), so no CI result exists yet:
https://github.com/zitouthani/OpenStudio/actions/runs/40232325922

Hard memory limit (`tests/perf/docker_memory_check.sh`, `docker run --memory=256m --memory-swap=256m`):
input 1,342,333,810 bytes (5.0× the limit), 20,189,691 records out, peak RSS 26,292,224 bytes (25.1 MiB),
`docker inspect` → `OOMKilled=false ExitCode=0 Memory=268435456 MemorySwap=268435456`.

### Metrics after a resume: per-run vs cumulative

- Cumulative (job lifetime, seeded from the checkpoint): `Metrics.records_in/out/rejected/filtered`,
  `batches_processed`; Prometheus `openstudio_<name>_total`.
- Per-run (this process only): `Metrics.run_records_in/out/rejected/filtered`, `run_batches_processed`;
  Prometheus `openstudio_run_<name>_total`. Throughput uses the per-run view.

After a crash/cancel at batch k and a resume, cumulative equals an uninterrupted run and per-run equals
the cumulative minus what the checkpoint already held (`test_metrics_per_run_and_cumulative_after_resume`).

### Phase 2 vs Phase 3 (full `execute_graph` vs `Pipeline`, 500,000 rows, 29.8 MB, 7 alternating runs)

| | median rec/s | min–max rec/s | spread | median peak RSS |
|---|---|---|---|---|
| Phase 2 `execute_graph` (CSVReader → Transform → CSVWriter) | 272,112 | 270,200–272,711 | 0.9% | 229.4 MB |
| Phase 3 `Pipeline` | 160,879 | 154,279–163,160 | 5.5% | 18.6 MB |

Reproduce: `python benchmarks/run_benchmark.py --rows 500000 --runs 7 --write-baseline`
(4-core sandbox; numbers are in `tests/perf/phase2_baseline.json`).

### Perf regression threshold

Phase 3 spread across 7 runs is 5.5% (max drop from median 4.1%), Phase 2 spread 0.9%. The test
(`test_throughput_regression_against_phase3_baseline`) runs both modes 3× interleaved, takes medians and
fails when the Phase 3/Phase 2 throughput ratio is more than 20% below the baseline ratio (0.5912, i.e. floor
0.473). Using the ratio instead of absolute rec/s removes dependence on runner hardware; 20% is ~3.6× the
measured Phase 3 spread, so noise alone should not trip it. The threshold was not loosened from the target.

### Crash recovery coverage

`kill -9` tests: 10 random-timing seeds, plus deterministic kills at: torn checkpoint temp file before fsync,
before the checkpoint rename, before a part-file rename, and before the final output rename (each compared with
an uninterrupted run: row count, sha256, zero duplicate ids, no leftover `.tmp`). `ENOSPC` tests inject
`OSError(ENOSPC)` on fsync during a part write and during final output assembly: no output file and no temp
files remain, and `resume=True` produces the reference row count and sha256. ENOSPC is injected, not a real
full filesystem.
