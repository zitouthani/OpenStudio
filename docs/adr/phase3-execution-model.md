# ADR: Phase 3 execution model (batched, bounded, resumable)

Status: accepted

## Context

Phase 2 (`src.engine.runtime.execute_graph`) loads the whole input into a list
and runs each component over it. Memory grows with input size, any failure
loses all work, and there is no way to cancel or resume. Phase 3 adds a new
streaming runner in `src/pipeline/`. The Phase 2 API is unchanged.

## Data flow

`reader -> transform -> writer`, three threads joined by bounded
`queue.Queue(maxsize=N)` queues. A full queue blocks the producer
(backpressure), so at most `queue_maxsize` batches sit between any two stages
and memory is bounded by roughly `(3 * queue_maxsize + 3) * batch_size` rows.

A batch is `batch_size` consecutive *source records*. Its `batch_id` is its
zero-based position (`record_index // batch_size`), so it is stable across
runs as long as the input and `batch_size` are unchanged. Stages are
single-threaded and FIFO, so batches are committed strictly in order.

## Delivery semantics

At-least-once processing with idempotent writes, which gives exactly-once
*visible* output:

- A batch may be processed more than once (after a crash or retry).
- Sinks write per-batch output to a deterministic name derived from
  `batch_id` (`parts/part-<id>.csv`, `dead_letter/batch-<id>.jsonl`) via
  write-temp, fsync, atomic rename. Re-writing a batch replaces the same file,
  so duplicates cannot occur.
- The final output is assembled only from batches `0..last_committed_batch`,
  so stale output of an uncommitted batch is never included.

## Checkpoint

`checkpoint.json` contains: format version, job fingerprint (input path, input
size, batch size), `last_committed_batch` (-1 = none), cumulative record and
batch counters, and status (`running`, `cancelled`, `completed`). It is written
atomically (temp file, fsync, `os.replace`).

Commit timing: the checkpoint is advanced only **after** the batch's output
and dead-letter files are fully written. A crash between write and commit
causes the batch to be redone and overwritten (idempotent). Resume with a
different fingerprint is refused.

## Cancellation

SIGINT/SIGTERM (when run on the main thread) or `Pipeline.cancel()` set a
cancel token. Then: (1) the reader stops accepting new batches, (2) in-flight
batches drain through transform and writer and are committed, (3) the
checkpoint is persisted with status `cancelled`, (4) `run()` returns normally
with status `cancelled`. `resume=True` continues from the next batch.

## Error taxonomy

| Class | Meaning | Handling |
|-------|---------|----------|
| `RetryableError` (also `OSError` from sinks) | transient | retry the batch with exponential backoff up to `max_retries`; if exhausted, becomes fatal |
| `SkippableError` / malformed input row | bad record | record goes to the dead-letter file with batch id, record index and reason; batch continues |
| `FatalError` / any other exception | bug or unrecoverable | stop the pipeline, roll back the current batch (no partial output), keep the last checkpoint, raise `PipelineError` |

Atomic batch failure: a batch's output becomes visible only through the final
rename, so a failed batch leaves no partial file.

## Metrics

Batches processed/failed/retried, records in/out/rejected/filtered, queue
depth (current and max) per stage, throughput, peak RSS and elapsed time, kept
in memory and exported in Prometheus text format to `<work_dir>/metrics.prom`.
