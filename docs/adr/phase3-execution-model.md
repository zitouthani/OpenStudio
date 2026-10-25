# ADR: Phase 3 execution model

- Status: Accepted
- Date: 2026-10-25

## Context

Phase 2's `execute_graph` converts the entire input iterable to a list before
processing it. On this sandbox, an unmodified one-component pass-through run
over 100,000 generated records took 0.186882 seconds (about 535,098 records per
second) and reached 28,179,290 bytes of peak traced Python allocation on
Python 3.12.3. This is a reproducible `tracemalloc` baseline, not an RSS
measurement or a container memory-limit result.

## Decision

### Delivery and duplicate prevention

Execution uses at-least-once delivery. A deterministic `batch_id` identifies
each batch by its source position, so replaying an uncommitted batch uses the
same identity. Batch-aware sinks must make writes idempotent for that ID:
publishing a batch replaces its prior staged result rather than appending a
second copy. The CSV sink stages each complete batch separately and atomically
publishes the ordered final file. Other components that perform side effects
must provide equivalent idempotence; arbitrary external side effects cannot be
rolled back by the engine.

### Checkpoints and commit boundary

A checkpoint contains a format version, the configured batch size, and the ID
of the last fully committed batch, plus cumulative committed record counters.
It is written via a temporary file and atomic replacement. Resume rejects a
different batch size because it would change batch boundaries. The engine
commits only after every component in the batch has completed successfully,
including downstream writes. If the process stops before that point, resume
replays that batch; deterministic IDs and idempotent batch writes prevent
duplicates. An absent checkpoint starts at the first batch.

The checkpoint does not fingerprint arbitrary input iterables. Callers must
resume with the same stable, ordered source; changing the source can invalidate
the checkpoint and is not detected by the engine.

### Bounded synchronous flow

Input is consumed incrementally in batches with configurable maximum record
count. Stages process one batch at a time in graph order; no stages run
concurrently and the executor does not use inter-stage queues. Memory therefore
depends on the input batch and the largest stage output for that batch, not the
entire job. `BoundedBatchQueue` is a standalone utility and is not used by this
executor.

### Cancellation

SIGINT/SIGTERM and the runtime cancellation API request cancellation. The
executor stops accepting batches, lets the current batch finish (or fail),
commits its checkpoint only after successful downstream writes, and returns
cleanly with the unprocessed input available for resume. It does not interrupt
an in-flight component, because that could leave an untracked partial write.

### Error taxonomy

- **Retryable:** transient component or downstream failures; retry the whole
  batch with bounded exponential backoff and the same `batch_id`.
- **Skippable:** malformed individual records; emit the original record and
  reason to the dead-letter output, then continue valid records in that batch.
- **Fatal:** invalid runtime configuration, checkpoint corruption, or an
  exhausted retry / unrecoverable stage failure; stop execution without
  committing the failed batch.

## Validation figures

The Phase 2 baseline above used a generated input with `id` and `value` keys
and one pass-through component. The Phase 3 CI regression test requires at least
50% of this historical Phase 2 throughput (267,549 records/second) on POSIX
runners. It is skipped on Windows because this Linux-specific baseline is not
portable. The large-stream test requires less than 5,000,000 bytes of traced
Python allocation; this is not a process RSS measurement.

For the large-input check, one million rows of the same shape were streamed in
256-record batches in Docker with `--memory=64m --memory-swap=64m`. This
materialized input would be approximately 268.8 MiB by linear extrapolation
from the Phase 2 allocation profile, or more than four times the container
limit. The run completed at about 642,184 records/second; peak traced Python
allocation was 145,307 bytes, process peak RSS was 20,852 KiB, and cgroup peak
memory was 17,039,360 bytes. The test asserts that the container run completes
and remains below the 64 MiB hard limit. These measurements are environment-
specific and are references, not universal guarantees.

## Consequences

Metrics expose per-run counters and cumulative committed counters restored
from the checkpoint. The engine can resume safely when source ordering is
stable and sinks obey the batch-aware idempotence contract. Generic legacy
components continue to work through their existing `process(rows)` interface,
but side-effecting legacy components cannot provide crash-safe exactly-once
effects without opting into the batch-aware contract.
