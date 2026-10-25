# Desktop editor

## Status

The first desktop editor is a phase-2 prototype. It supports linear CSV jobs;
branching graphs, database connectors, background execution, and advanced
monitoring are not implemented yet.

## Install and launch

Install the optional GUI extra from the repository root:

```bash
python -m pip install -e ".[gui]"
openstudio-etl-gui
```

Alternatively, launch it with:

```bash
python -m src.desktop.app
```

## Build a job

1. Add a CSV Reader and set its file path and delimiter.
2. Add optional Filter or Transform steps and configure their properties.
3. Add a CSV Writer and set a different output file path.
4. Use Move up / Move down to order steps. Connections are generated in order.
5. Validate, save the job as JSON, or run it.

The editor supports filter operators `equals`, `not equals`, `contains`,
`greater than`, and `less than`. Transform renames a column and can multiply
numeric values. The output panel displays at most 50 result rows as a local
preview; the writer writes the full result to the configured output file.

## Job and runtime boundaries

Jobs use the existing versioned `Job` and `Component` model. The editor's
`pipeline.py` validates its supported linear format and compiles it to the
existing `ExecutionGraph`. PySide6 is an optional dependency and is not
imported by the headless CLI or engine.

Treat source and output data as sensitive. The editor does not upload pipeline
data, but the preview is visible on screen and output files are written to the
path configured by the user. Do not put credentials or secret values in job
configuration.
