"""Defensive redaction for text persisted to or returned from audit logs."""

import re
from typing import Any

_NAMED_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|authorization|bearer|token|password)\s*([:=])\s*([^\s,;]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\b(bearer)\s+([A-Za-z0-9._~+/-]{8,})")
_KEY_LIKE_VALUE = re.compile(r"\b(?:sk|api|key)-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE)
_SENSITIVE_KEY_PART = re.compile(r"(?i)(?:api[_-]?key|authorization|bearer|token|password)")


def redact_text(value: str | None) -> str | None:
    """Remove common secret representations while retaining useful audit context."""
    if value is None:
        return None
    # Redact a standalone Bearer value first. Otherwise the named-secret
    # pattern below can consume only the word "Bearer" and leave its token.
    redacted = _BEARER_TOKEN.sub(r"\1 [REDACTED]", value)
    redacted = _NAMED_SECRET.sub(r"\1\2[REDACTED]", redacted)
    return _KEY_LIKE_VALUE.sub("[REDACTED]", redacted)


def redact_json(value: Any) -> Any:
    """Recursively redact values before exposing historical JSON audit data."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if _SENSITIVE_KEY_PART.search(str(key))
            else redact_json(item)
            for key, item in value.items()
        }
    return value
