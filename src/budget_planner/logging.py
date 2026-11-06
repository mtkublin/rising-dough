"""Structured JSON logging for the app (T-D06).

Rising Dough v3 ships to a Scaleway VM where ``journalctl`` is the only
log sink. A JSON renderer plus a ``request_id`` contextvar makes ``jq``
triage realistic without pulling in a log aggregator (deferred to v3.1).

Public surface:

- :func:`configure` — idempotent, wires structlog + stdlib logging to a
  JSON renderer with ISO-8601 timestamps.
- :func:`get_logger` — thin passthrough so callers do not import
  ``structlog`` directly.
- :func:`bind_request_id` / :func:`clear_request_id` — helpers for the
  per-request contextvar; the middleware is the real caller.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger


_CONFIGURED = False

# T-D59 / ADR-0078 §5: keys whose values never reach a log line.
REDACTED = "[redacted]"
_DENY_EXACT = frozenset({"description", "name", "memo", "formula", "q", "search", "email"})
_DENY_PREFIXES = ("amount", "note", "password", "token", "secret")
_DENY_SUFFIXES = ("_json",)
_PATH_ARG = 2  # index of the request path in uvicorn.access log args


def _is_sensitive_key(key: object) -> bool:
    if not isinstance(key, str):
        return False
    k = key.lower()
    return k in _DENY_EXACT or k.startswith(_DENY_PREFIXES) or k.endswith(_DENY_SUFFIXES)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: (REDACTED if _is_sensitive_key(k) else _redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    return value


def redact_sensitive(_logger: Any, _method: str, event_dict: Any) -> Any:
    """structlog processor: replace value-bearing keys with ``[redacted]``.

    Case-insensitive, prefix/suffix aware, recursive into dicts and lists.
    Returns a new dict; the input is not mutated.
    """
    return _redact(dict(event_dict))


class _StripQueryFilter(logging.Filter):
    """Drop the query string from ``uvicorn.access`` request paths."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        idx = _PATH_ARG
        if not (isinstance(args, tuple) and len(args) > idx):
            return True
        path = args[idx]
        if isinstance(path, str):
            record.args = (*args[:idx], path.split("?", 1)[0], *args[idx + 1 :])
        return True


def _processors() -> list[Any]:
    """Shared processor chain. Order matters.

    ``merge_contextvars`` picks up ``request_id`` (and any other
    contextvar) bound by the middleware. ``TimeStamper`` emits an ISO-8601
    UTC timestamp. ``JSONRenderer`` is last so the output is a single
    JSON object per log line.
    """
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_sensitive,
        structlog.processors.JSONRenderer(),
    ]


def configure() -> None:
    """Configure structlog + stdlib root logger.

    Idempotent — safe to call from ``create_app`` and from tests. The
    stdlib root logger is pointed at the same JSON renderer so uvicorn
    access logs and third-party libraries land in the same stream.
    """
    global _CONFIGURED  # noqa: PLW0603 — module-level idempotence flag
    if _CONFIGURED:
        return

    structlog.configure(
        processors=_processors(),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging through the same JSON renderer. Uvicorn uses
    # three loggers: ``uvicorn``, ``uvicorn.error``, ``uvicorn.access``.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                redact_sensitive,
            ],
            processor=structlog.processors.JSONRenderer(),
        )
    )
    handler._bp_configured = True  # type: ignore[attr-defined]

    root = logging.getLogger()
    # Replace any pre-existing stdout handler we installed earlier so the
    # function stays idempotent even when called repeatedly in tests.
    root.handlers = [h for h in root.handlers if not getattr(h, "_bp_configured", False)]
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Uvicorn silences propagation by default; flip it so the structured
    # formatter owns the output pipeline.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    logging.getLogger("uvicorn.access").addFilter(_StripQueryFilter())

    _CONFIGURED = True


def get_logger(name: str | None = None) -> BoundLogger:
    """Return a structlog-bound logger; thin passthrough for callers."""
    return structlog.stdlib.get_logger(name) if name else structlog.stdlib.get_logger()


def bind_request_id(request_id: str) -> None:
    """Bind ``request_id`` to the current contextvar scope."""
    structlog.contextvars.bind_contextvars(request_id=request_id)


def clear_request_id() -> None:
    """Clear every bound contextvar — called after a request completes."""
    structlog.contextvars.clear_contextvars()
