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
