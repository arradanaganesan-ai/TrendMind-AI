"""Security helpers: logging redaction and user-content sanitization."""

from __future__ import annotations

import re

# Keys whose values must never appear in logs or error messages.
_SECRET_KEY_PATTERN = re.compile(
    r"(api[_-]?key|authorization|token|secret|password|credential)", re.IGNORECASE
)


def redact_secrets(text: str) -> str:
    """Redact `key=value` style secrets from a string before logging."""
    return re.sub(
        r"(?i)\b(api[_-]?key|authorization|token|secret|password|credential)(\s*[=:]\s*)(\S+)",
        r"\1\2[REDACTED]",
        text,
    )


def is_secret_key(key: str) -> bool:
    return bool(_SECRET_KEY_PATTERN.search(key))


def strip_control_chars(text: str, max_length: int = 4000) -> str:
    """Remove control characters (log-injection / terminal escape protection)."""
    cleaned = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ch.isprintable())
    return cleaned[:max_length]


def safe_external_title(text: str, max_length: int = 300) -> str:
    """Normalize a title/snippet coming from an untrusted external source."""
    return strip_control_chars(" ".join(text.split()), max_length)
