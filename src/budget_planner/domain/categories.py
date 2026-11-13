"""Category entity + DTOs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from budget_planner.domain.enums import Direction

HEX_COLOR_RE = re.compile(r"^#[0-9a-f]{6}$")


def normalise_color(raw: str | None) -> str | None:
    """Return ``raw`` normalised to lowercase hex, or ``None`` if blank.

    Mirrors the SQL CHECK on ``categories.color``. Raises :class:`ValueError`
    if ``raw`` is a non-blank string that doesn't match the 6-digit hex form.
    """
    if raw is None:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    candidate = trimmed.lower()
    if not HEX_COLOR_RE.match(candidate):
        raise ValueError(f"invalid color {raw!r}; expected 6-digit hex like #a3c2ff")
    return candidate


@dataclass(frozen=True, slots=True, kw_only=True)
class Category:
    """Persisted category row."""

    id: int
    user_id: int
    name: str
    direction: Direction
    is_system: bool
    color: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class NewCategory:
    """Insertable fields for a new category."""

    name: str
    direction: Direction
    is_system: bool = False
    color: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PatchCategory:
    """Partial update DTO.

    `direction` is omitted intentionally — once a category has transactions,
    changing direction would silently flip balances. Enforced in the service
    layer.

    `clear_color=True` is the sentinel for "reset to direction default"
    (sets ``color = NULL``). When ``clear_color`` is True, ``color`` is
    ignored. When ``clear_color`` is False, a non-None ``color`` is applied
    and a ``None`` ``color`` means "no change" (consistent with ``name``).
    """

    name: str | None = None
    color: str | None = None
    clear_color: bool = False

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.name is not None:
            out["name"] = self.name
        if self.clear_color:
            out["color"] = None
        elif self.color is not None:
            out["color"] = self.color
        return out
