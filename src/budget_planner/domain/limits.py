"""Named per-request bounds (T-Q235, Q-035). Documented in requirements section 3.9."""

from __future__ import annotations

PAGE_SIZE_MAX = 500
ID_MAX = 2**63 - 1  # SQLite INTEGER ceiling; larger ids are never valid
NAME_MAX_LENGTH = 120
DESCRIPTION_MAX_LENGTH = 500
MAX_BODY_BYTES = 256 * 1024


def length_error(value: str, *, maximum: int) -> str | None:
    """Return the form error message when ``value`` exceeds ``maximum`` characters."""
    if len(value) > maximum:
        return f"must be at most {maximum} characters"
    return None


def name_error(name: str) -> str | None:
    """Form error for a required, length-bounded display name (or None)."""
    if not name.strip():
        return "name required"
    return length_error(name, maximum=NAME_MAX_LENGTH)
