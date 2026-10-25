# Security Guide

## Secret handling

- Never hardcode credentials in source files.
- Prefer local prompt-driven storage.
- Log metadata only; do not log raw tokens or password material.
- Force local-only persistence when credentials are required.

## File and import safety

- Validate job file paths and imported documents.
- Reject unexpected file types before import.
- Parse external definitions minimally and without arbitrary execution.

## Privacy and logging

- Redact secrets in logs and error traces.
- Store business data only when required.
- Keep logs focused on job execution status, not raw values.
