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

## Streaming execution

`execute_graph` remains available for the original whole-input API. For large
jobs, pass a streaming source to `execute_graph_stream` and make a batch-aware
writer the final graph component:

```python
from src.components.csv_reader import CSVReader
from src.components.csv_writer import CSVWriter
from src.engine import ExecutionGraph, execute_graph_stream

graph = ExecutionGraph()
graph.add_component("writer", CSVWriter("output.csv"))
metrics = execute_graph_stream(
    graph,
    CSVReader("input.csv").iter_rows(),
    batch_size=512,
    checkpoint_path="output.checkpoint.json",
    resume=True,
)
metrics.write_prometheus("output.metrics")
```

`CancellationToken.cancel()` requests a clean stop after the in-flight batch;
resume the same stable, ordered source with the same batch size and checkpoint
path. The checkpoint stores the batch size and last committed batch, but does
not fingerprint arbitrary input iterables; the caller must ensure the resumed
source is unchanged. Legacy components continue to work with `process(rows)`.
Components that perform external side effects should implement idempotent
`process_batch(rows, batch_id)` writes to support crash-safe replay.

Execution is synchronous and processes one batch through the graph at a time.
It does not currently use `BoundedBatchQueue` or run stages concurrently; its
memory bound is based on the configured batch and the largest intermediate
stage output. The `BoundedBatchQueue` type is a standalone utility, not an
active runtime queue.

`records_in`, `records_out`, and the other existing counters describe the
current invocation. The `cumulative_*` fields and corresponding
`openstudio_*_total` Prometheus metrics describe batches committed across
resumed invocations. `openstudio_run_*_total` metrics are scoped to the current
invocation. Peak memory in the runtime metrics is traced Python allocation,
not process RSS.

## Linting

```bash
ruff check src tests
```

## Desktop editor

Install the optional GUI dependency and launch the editor:

```bash
python -m pip install -e ".[gui]"
openstudio-etl-gui
```

The editor is intentionally kept in `src/desktop`; job validation and
translation to runtime components live in `src/desktop/pipeline.py` so the
execution engine remains independent of PySide6. See
[`desktop-editor.md`](desktop-editor.md) for supported components and usage.

## Phase workflow

- Phase instructions live under `.github/phases/`.
- GitHub Actions workflows are under `.github/workflows/`.
- Run `Sequential phase validation` from the Actions tab to validate phases 0
  through 5 in order. Each phase starts only after the previous reusable
  workflow succeeds; a failure prevents later phases from running. Individual
  phase workflows remain available for manual runs.
- Keep branch scope narrow and feature-driven.
- Update README and relevant docs whenever the user-facing workflow changes.

## Project progress dashboard

Run the dashboard from the repository root without installing dependencies:

```bash
python -m http.server 8000 --directory web
```

Open <http://localhost:8000> in a browser. Phase and task statuses are stored in that browser's local storage, so they are specific to the browser and device in use.
