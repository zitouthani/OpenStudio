# Phase 1 — Foundations

## Goal

Create the initial Python foundation for job modeling, execution graph handling, and core CSV flows.

## Deliverables

- Versioned job model
- Validation layer with schema checks
- Execution graph skeleton
- CSV Reader, Filter, Transform, and CSV Writer plugin stubs
- Unit/integration tests for the core flow

## Acceptance criteria

- Jobs can be created and validated.
- The engine can execute a simple graph without the UI.
- A CSV pipeline can run end-to-end.
- The project keeps a clear separation between engine and UI.

The CSV acceptance check is exercised end-to-end by
`tests/test_core_pipeline.py`.
