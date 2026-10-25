from __future__ import annotations


class PipelineError(Exception):
    """Raised by Pipeline.run when the run aborted with a fatal error."""


class RetryableError(Exception):
    """Transient failure; the batch is retried with backoff."""


class SkippableError(Exception):
    """Bad record; the record is dead-lettered and processing continues."""


class FatalError(Exception):
    """Unrecoverable failure; the run stops and the current batch is rolled back."""
