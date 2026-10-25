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
path. Legacy components continue to work with `process(rows)`. Components that
perform external side effects should implement idempotent
`process_batch(rows, batch_id)` writes to support crash-safe replay.

## Linting

```bash
ruff check src tests
```

## Phase workflow

- Phase instructions live under `.github/phases/`.
- GitHub Actions workflows are under `.github/workflows/`.
- Keep branch scope narrow and feature-driven.
- Update README and relevant docs whenever the user-facing workflow changes.
