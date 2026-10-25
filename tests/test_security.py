from src.common.config import redact_secret


def test_redact_secret_masks_values() -> None:
    assert redact_secret("super-secret") == "[REDACTED]"
    assert redact_secret(None) == "[REDACTED]"
