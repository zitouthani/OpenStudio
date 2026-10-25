# OpenStudio ETL

OpenStudio ETL is a Python-first, Talend-inspired data integration platform designed for visual job authoring, secure local credential handling, and extensible data processing.

## Vision

This repository is structured as a maintainable ETL foundation for a future desktop application inspired by Talend Big Data Open Studio. The goal is to keep the execution engine independent from the interface, respect security/privacy constraints for sensitive data, and use a phased, testable process for feature delivery.

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
│   ├── talend-importer.md
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
│   ├── talend_importer/
│   └── common/
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

## Development phases

The project is organized in six phases:

1. Phase 0 — Audit and scoping
2. Phase 1 — Foundations
3. Phase 2 — Desktop editor
4. Phase 3 — Robust execution
5. Phase 4 — Connectors
6. Phase 5 — Talend migration and release

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

## Documentation

- `README.md` is the entry point for installation and usage.
- `docs/architecture.md` describes module boundaries.
- `docs/developer-guide.md` explains tooling and local workflow.
- `docs/talend-importer.md` describes migration safety and reporting.
- `docs/release.md` covers packaging and release validation.

## Contributing

- Keep work scoped to a single feature or phase.
- Prefer one branch per functional slice.
- Add targeted tests for each behavior.
- Update documentation whenever the user-facing workflow changes.
- Use comments where the logic or design decision needs extra explanation.

## Licensing

License and third-party notices are tracked in `LICENSE` and `THIRD_PARTY_NOTICES.md`.
