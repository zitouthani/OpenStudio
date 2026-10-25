# Architecture

This project follows a layered architecture to keep the execution engine separate from the desktop application experience.

## Layers

- `job_model` defines the job model and validation rules.
- `engine` executes the graph and manages runtime state.
- `data_runtime` handles schema and batch semantics.
- `component_sdk` defines component contracts and registry.
- `components` holds native components and connectors.
- `desktop` manages the PySide6 interface.
- `cli` provides a headless execution path.
- `talend_importer` reads Talend job metadata and emits migration reports.

## Design principles

- Keep the engine independent from UI dependencies.
- Prefer explicit contracts over implicit coupling.
- Use versioned jobs and safe validation.
- Add heavy dependencies only when needed and covered by tests.
- Ensure credentials and secrets are never embedded in job definitions.
