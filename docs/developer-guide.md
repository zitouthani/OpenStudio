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
- Keep branch scope narrow and feature-driven.
- Update README and relevant docs whenever the user-facing workflow changes.

## Project progress dashboard

Run the dashboard from the repository root without installing dependencies:

```bash
python -m http.server 8000 --directory web
```

Open <http://localhost:8000> in a browser. Phase and task statuses are stored in that browser's local storage, so they are specific to the browser and device in use.
