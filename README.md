# OpenStudio ETL

OpenStudio ETL is a Python-first data integration platform for designing, validating, and running data pipelines. It is built around a modular execution engine, a versioned job model, and extensible components.

## Vision

This repository provides a maintainable foundation for visual pipeline authoring and reliable data processing. The execution engine is independent from the interface, sensitive data is handled with security and privacy in mind, and features are delivered through incremental, testable phases.

## Product goals

- Visual job authoring with a graph editor.
- Versioned job model stored in JSON and validated before execution.
- A runtime engine that can execute pipelines without the UI.
- Direct, business-friendly component names like CSV Reader, Filter, Transform, and REST API.
- Secure handling of user credentials and local-only storage.
- A documentation-first workflow with per-phase instruction files and GitHub Actions validation.

## Repository layout

```text
.
├── .github/
│   ├── phases/
│   │   ├── phase-0/instruction.md
│   │   ├── phase-1/instruction.md
│   │   ├── phase-2/instruction.md
│   │   ├── phase-3/instruction.md
│   │   ├── phase-4/instruction.md
│   │   └── phase-5/instruction.md
│   └── workflows/
│       ├── ci.yml
│       ├── phase-0.yml
│       ├── phase-1.yml
│       ├── phase-2.yml
│       ├── phase-3.yml
│       ├── phase-4.yml
│       └── phase-5.yml
├── docs/
│   ├── architecture.md
│   ├── developer-guide.md
│   ├── security.md
│   └── release.md
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── docs.txt
├── src/
│   ├── job_model/
│   ├── engine/
│   ├── data_runtime/
│   ├── component_sdk/
│   ├── components/
│   ├── desktop/
│   ├── cli/
│   └── common/
├── web/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── tests/
├── SECURITY.md
├── LICENSE
├── THIRD_PARTY_NOTICES.md
├── pyproject.toml
├── .gitignore
├── requirements.txt
└── README.md
```

## Setup

### Prerequisites

- Python 3.11+
- pip
- Git

### Installation

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements/dev.txt
```

### Running tests

```bash
pytest
```

### Running the CLI skeleton

```bash
python -m src.cli.main --help
```

### Tracking project progress

The project dashboard is a lightweight web interface for following phase and task progress. It requires no additional dependencies:

```bash
python -m http.server 8000 --directory web
```

Then open <http://localhost:8000>. Progress changes are saved in the current browser's local storage and are not shared with other contributors.

## Development phases

The project is organized in six phases:

1. Phase 0 — Audit and scoping
2. Phase 1 — Foundations
3. Phase 2 — Desktop editor
4. Phase 3 — Robust execution
5. Phase 4 — Connectors
6. Phase 5 — Interoperability and release

Each phase contains an `instruction.md` file and matching GitHub workflow automation.

## Security and privacy

This project may process sensitive customer data, credentials, file paths, and external API secrets. Because of that, the platform must:

- avoid hardcoded secrets,
- prompt for credentials locally when needed,
- store credentials securely and locally,
- provide explicit logout or credential reset paths,
- redact sensitive fields in execution logs,
- validate path and file imports before processing.

See `SECURITY.md` and `docs/security.md` for policy details.

## Supply-chain security and releases

GitHub Actions runs the test suite, audits Python dependencies, compiles the
source, and builds the distributions. Version tags (`v*`) trigger a release
workflow that attaches the wheel and source archive to a GitHub Release and
publishes to PyPI using Trusted Publishing. Configure the repository's `pypi`
environment and PyPI trusted publisher before creating the first release tag.

The build provenance workflow attests release build artifacts. Users can verify
a downloaded wheel with GitHub CLI:

```bash
gh attestation verify openstudio_etl-0.1.0-py3-none-any.whl --repo zitouthani/OpenStudio
```

Provenance is one supply-chain control; it does not replace tests, dependency
audits, vulnerability analysis, or source review.

## Documentation

- `README.md` is the entry point for installation and usage.
- `docs/architecture.md` describes module boundaries.
- `docs/developer-guide.md` explains tooling and local workflow.
- `docs/release.md` covers packaging and release validation.

## Contributing

- Keep work scoped to a single feature or phase.
- Prefer one branch per functional slice.
- Add targeted tests for each behavior.
- Update documentation whenever the user-facing workflow changes.
- Use comments where the logic or design decision needs extra explanation.

## Licensing

License and third-party notices are tracked in `LICENSE` and `THIRD_PARTY_NOTICES.md`.
