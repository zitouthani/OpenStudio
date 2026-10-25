# Security Policy

## Scope

This repository is a software foundation for an ETL platform and may handle sensitive data, credentials, file paths, and external service access.

## Security expectations

- Never commit secrets, credentials, tokens, or API keys.
- Do not hardcode passwords in examples or documentation.
- Use local prompts or secure storage for credentials when required.
- Validate file paths and imported job definitions before execution.
- Treat all data as potentially sensitive and handle it with privacy in mind.
- Clear or logout credentials when they are no longer needed.

## Reporting security issues

Please report suspected vulnerabilities privately to the maintainer or repository security contact. Do not open public issues for sensitive reports.

## Secure defaults

- Prefer local-only credential storage.
- Require explicit user consent before storing credentials.
- Validate connectors, URLs, and file destinations.
- Log execution metadata without exposing raw secret values.
- Ensure imports and job files are parsed in a sandboxed, read-only manner when possible.

## Privacy

- Do not log sensitive fields by default.
- Redact secret values in error traces.
- Avoid exposing raw query strings or tokens in diagnostics.
- Keep operation logs focused on business outcome and error classification instead of secret material.
