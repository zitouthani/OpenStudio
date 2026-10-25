from __future__ import annotations


def redact_secret(value: str | None, placeholder: str = "[REDACTED]") -> str:
    """Mask sensitive credential material before logging."""
    if value is None:
        return placeholder
    if not value:
        return placeholder
    return placeholder
