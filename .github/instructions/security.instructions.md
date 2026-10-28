---
description: "Apply when designing, implementing, reviewing, or testing security-sensitive code for this ETL platform, including pipeline definitions, connectors, file and network I/O, credentials, data handling, execution, logging, and releases."
applyTo: "**"
---

# Secure Coding Instructions for the ETL Platform

Apply these requirements to every change. Treat pipeline definitions, connector configuration, source data, remote responses, filenames, and user input as untrusted. Prefer secure defaults and explicit validation; never silently weaken a control to make a test or integration pass.

Use [SECURITY.md](../../SECURITY.md) and [docs/security.md](../../docs/security.md) as the repository policy. Keep implementation and tests consistent with them. Do not claim a control exists unless the code enforces it.

## Design and trust boundaries

- Identify the data flows, trust boundaries, sensitive fields, and security impact before changing ingestion, transformation, execution, connector, credential, or export behavior.
- Enforce authorization and validation at the point where a resource is used, not only in the UI or when a job is saved. The execution engine must not trust UI-provided job definitions.
- Use least privilege for filesystem access, connector credentials, network access, and subprocesses. Keep secrets and data scoped to the job and operation that need them.
- Fail closed on invalid, ambiguous, or unsupported security-sensitive input. Return actionable, non-sensitive errors; do not silently skip validation, broaden access, or fall back to insecure behavior.
- Preserve existing security boundaries. Do not introduce arbitrary code execution, plugin loading, shell execution, or dynamic evaluation as a convenience feature.

## Pipeline definitions and input validation

- Parse job definitions with safe, data-only parsers. Validate their schema, types, required fields, bounds, component names, and references before execution; reject unknown or malformed values where they could alter behavior.
- Never use `eval`, `exec`, `pickle`, unsafe YAML loaders, or equivalent mechanisms to deserialize or execute job content or imported data. Do not treat a file extension or successful parse as proof of trust.
- Validate at every boundary: editor/API/CLI input, persisted job files, connector configuration, external records, and data passed between components. Normalize once and validate the normalized value.
- Apply explicit limits to input size, nesting, row and column counts, string lengths, batch sizes, and processing time where untrusted inputs could exhaust resources.
- Make transformations deterministic where practical. Do not let data values become code, expressions, component names, or configuration without a narrowly defined parser and validation.

## Filesystem and archive safety

- Treat paths from jobs, imports, connectors, and data as untrusted. Resolve paths against an explicit permitted root and verify the resolved path remains inside it; account for traversal, absolute paths, symlinks, and platform-specific path forms.
- Avoid time-of-check/time-of-use gaps. Use safe file APIs and atomic writes where available; do not overwrite unrelated files or follow attacker-controlled links.
- Restrict accepted formats and file types. For archives, guard against path traversal, excessive entry counts, oversized expanded content, and decompression bombs.
- Create temporary files securely with restrictive permissions, close and clean them reliably, and never place credentials or sensitive records in predictable shared temporary paths.
- Use explicit overwrite and destination policies. Validate output destinations before writing and preserve existing files unless replacement is clearly intended and authorized.

## Network connectors and injection

- Use TLS with certificate verification enabled. Never disable verification to work around connectivity or test failures.
- Defend URL-fetching connectors against SSRF: allow only required schemes and destinations, reject loopback, private, link-local, and otherwise prohibited addresses as appropriate, and re-check destinations after DNS resolution and redirects. Do not assume URL parsing alone is sufficient.
- Apply connection/read timeouts, response-size limits, redirect limits, and bounded retries. Do not send credentials to a redirected or unapproved origin.
- Parameterize SQL values. Where identifiers cannot be parameterized, select them from a strict allowlist; never concatenate untrusted values into queries or commands.
- Escape or encode output for its actual target context. In particular, prevent CSV/spreadsheet formula injection when exporting untrusted values for spreadsheet use.
- Do not invoke shells for connector operations. If a subprocess is essential, use a fixed executable and argument array, validate each argument, avoid shell interpretation, and restrict environment, working directory, permissions, and runtime.

## Credentials and cryptography

- Never hardcode, commit, log, print, or include secrets in exceptions, test fixtures, snapshots, examples, job files, URLs, or command-line arguments.
- Prefer the repository's secure local credential mechanisms. Keep credentials out of pipeline definitions and ordinary configuration; do not invent a storage mechanism or imply encryption without verifying it.
- Keep secrets in memory only as long as needed. Redact them at every logging and diagnostic boundary, including nested errors and connector responses.
- Use established cryptographic libraries and maintained algorithms; do not implement cryptography. Verify certificates and use secure random generation for security tokens.
- Request the narrowest credential scopes possible. Never reuse a credential across unrelated services or send it to an untrusted destination.

## Data privacy and observability

- Assume records may contain personal, confidential, or regulated data. Collect, copy, retain, and export only what the operation requires.
- Logs and metrics should contain operational metadata, counts, durations, and safe error classifications—not record contents, tokens, passwords, authorization headers, raw payloads, or sensitive query parameters.
- Redact by default and test redaction against realistic nested structures. Avoid logging raw objects or exception text from untrusted services without sanitization.
- Prevent log injection by sanitizing control characters and untrusted fields. Keep diagnostics useful without exposing secrets or customer data.
- Ensure temporary, cached, checkpoint, and failed-output data follow the same access, retention, and cleanup expectations as primary data.

## Safe and reliable execution

- Bound CPU, memory, disk, network, concurrency, and execution time for jobs and components. Use streaming or bounded batches for large data instead of loading unbounded inputs into memory.
- Keep connector and transformation failures isolated to the smallest safe unit. Do not expose partial or corrupt outputs as successful results.
- Make retries bounded and use backoff. Retry writes only when they are idempotent or protected by an explicit deduplication/transaction strategy.
- Use atomic output publication or transactions where supported. Define cleanup and rollback behavior for temporary and partial outputs; do not delete user data as an implicit recovery action.
- Treat job IDs, checkpoints, caches, and output paths as security-sensitive when they can cross users or jobs. Preserve isolation between independent executions.

## Dependencies, tests, and review

- Use maintained, necessary dependencies and follow the repository's lock, audit, and release processes. Do not add a dependency for functionality already provided by the project without a clear need.
- Add focused tests for security boundaries and negative cases, including malformed inputs, traversal, injection, oversized data, secret redaction, redirects, timeouts, and partial failures as relevant to the change.
- Prefer tests that prove a prohibited action is rejected and that secrets/data do not escape. Do not use real credentials or production data in tests.
- Run the narrowest relevant tests and security checks, then broader checks when the change affects shared execution or security controls. Report what actually ran and any gaps.
- Review the final diff for accidental secrets, unsafe defaults, weakened validation, excessive permissions, and unrelated changes. Update security documentation when behavior or guarantees change.
- If a requirement cannot be enforced safely with available architecture, state the limitation and ask for a decision; do not present a best-effort mitigation as a guarantee.
