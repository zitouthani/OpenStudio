# Phase 0: Initial audit and scope

## Product direction

OpenStudio ETL is a Python-first, open-source data integration project. Its
long-term aim is to make ETL jobs easier to understand, build, run, and migrate
without tying users to a single vendor. The first deliverable is a small,
transparent foundation, not a production replacement for established ETL
suites.

## Initial MVP

The initial MVP is limited to:

- versioned JSON job definitions with validation;
- a headless execution engine and a small set of CSV, filter, and transform
  components;
- an optional desktop editor for linear CSV jobs;
- bounded, resumable execution for large CSV jobs;
- tests, contributor documentation, dependency checks, and reproducible release
  artifacts.

Database and API connectors, branching visual graphs, distributed execution,
enterprise credential management, and broad Talend compatibility are later
work. They should be added only with explicit use cases, security review, and
tests.

## Architecture boundaries

- `job_model` owns the versioned job representation and validation.
- `engine` and `data_runtime` execute jobs without importing desktop UI code.
- `component_sdk` defines the contracts used by components.
- `components` contains built-in readers, transforms, and writers.
- `desktop` is an optional PySide6 client; it must not own ETL execution rules.
- `cli` provides a headless entry point.

Job definitions must not contain credentials. Imported definitions and file
paths are untrusted input; importers must inspect static metadata only and must
never execute imported code.

## Initial validation plan

- Unit-test job serialization, validation, graph ordering, and each component.
- Test CSV reader-to-writer flows through the headless engine.
- Test desktop job validation, save/load, and an offscreen smoke run when the
  optional GUI dependency is installed.
- Test streaming execution for batch boundaries, failure handling, cancellation,
  checkpoint/resume, and bounded memory.
- Run the full suite, lint, dependency audit, compilation, and package build in
  CI; test release attestations separately from application behavior.

## Licensing and compatibility review

The repository license and third-party notices are the source of truth for
project licensing. Before adding a dependency or accepting imported assets,
contributors must check its license and record required notices. This document
sets that review process; it is not a legal opinion or a completed audit of
every dependency or every Talend component.

Talend migration is initially read-only and report-oriented. The importer must
identify supported and unsupported metadata and never run imported Java,
scripts, or jobs. Any compatibility claim must be backed by fixtures and
documented coverage.

## Initial backlog

1. Keep the Phase 1 engine and CSV flow small, testable, and usable without Qt.
2. Deliver a linear desktop editor without coupling the UI to the engine.
3. Add bounded, resumable execution while preserving the original engine API.
4. Add connectors only after defining credential storage, network, and retry
   behavior.
5. Expand migration coverage from real, redistributable fixtures and publish
   explicit compatibility reports.

This scope is an initial project boundary. Revisit it when maintainers and users
provide concrete use cases; do not interpret it as a completed production or
security audit.
