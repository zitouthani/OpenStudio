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

Full suite (20 tests, including the slow robustness tests) on the merged Phase 3 code: `20 passed in 56.84s`.
CI runs for the Phase 3 PR (#16) all ended `action_required` (workflow approval pending), so no CI result exists yet:
https://github.com/zitouthani/OpenStudio/actions/runs/40232325922

Hard memory limit (`tests/perf/docker_memory_check.sh`, `docker run --memory=256m --memory-swap=256m`):
input 1,342,333,810 bytes (5.0× the limit), 20,189,691 records out, peak RSS 26,292,224 bytes (25.1 MiB),
`docker inspect` → `OOMKilled=false ExitCode=0 Memory=268435456 MemorySwap=268435456`.
