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
