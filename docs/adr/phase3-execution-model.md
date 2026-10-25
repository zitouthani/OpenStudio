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

A checkpoint contains a format version and the ID of the last fully committed
batch. It is written via a temporary file and atomic replacement. The engine
commits only after every component in the batch has completed successfully,
including downstream writes. If the process stops before that point, resume
replays that batch; deterministic IDs and idempotent batch writes prevent
duplicates. An absent checkpoint starts at the first batch.

### Bounded flow and backpressure

Input is consumed incrementally in batches with configurable maximum record
count. Stages process one batch at a time in graph order, so the engine retains
at most the input batch and current stage output rather than the whole job.
When stages are connected asynchronously, every inter-stage queue must have a
finite `maxsize`; producers block when it is full. The current synchronous
executor uses no inter-stage queues.

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

## Consequences

The engine can resume safely when source ordering is stable and sinks obey the
batch-aware idempotence contract. Generic legacy components continue to work
through their existing `process(rows)` interface, but side-effecting legacy
components cannot provide crash-safe exactly-once effects without opting into
the batch-aware contract. The baseline figures are environment-specific and
must not be treated as a performance threshold.
