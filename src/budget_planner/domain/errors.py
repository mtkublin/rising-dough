"""Domain-level exception types.

Routers raise these from the HTTP boundary; `web.errors` maps them to HTTP
responses. Keeping the hierarchy small on purpose — see T-051 plan.

A fifth catch-all (`Exception`) is handled generically in `web.errors`;
any uncaught error becomes a 500 with a correlation id.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValidationError(Exception):
    """Field-level validation failure. 422 on the wire.

    `fields` maps form field name → user-facing message.
    """

    fields: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return "; ".join(f"{k}: {v}" for k, v in self.fields.items()) or "validation error"


@dataclass(frozen=True)
class NotFoundError(Exception):
    """Entity missing or soft-deleted. 404 on the wire."""

    entity: str
    entity_id: int | str

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.entity} {self.entity_id} not found"


class ConflictError(Exception):
    """Conflicting state (unique constraint, protected row, same-currency transit…).

    409 on the wire. A plain exception, not a frozen dataclass: a frozen
    dataclass exception cannot carry ``__traceback__`` and raises
    ``FrozenInstanceError`` once it propagates (T-Q230 is the first service to
    raise it).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:  # pragma: no cover
        return self.message


@dataclass(frozen=True)
class ServiceError(Exception):
    """Generic server-side failure. 500 on the wire. Message is user-safe only."""

    message: str = "something went wrong"

    def __str__(self) -> str:  # pragma: no cover
        return self.message


class InvariantError(RuntimeError):
    """A state the surrounding code guarantees was found violated. 500 on the wire (T-Q271).

    Replaces ``assert`` in ``src``: it survives ``python -O`` and names what was missing.
    """


def require_present[T](value: T | None, what: str) -> T:
    """Return ``value``, or raise :class:`InvariantError` naming ``what`` when it is ``None``."""
    if value is None:
        raise InvariantError(f"{what} is missing")
    return value
