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
import re
import sys
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger


# T-D59 / ADR-0078 §5: keys whose values never reach a log line.
REDACTED = "[redacted]"
_DENY_EXACT = frozenset({"description", "name", "memo", "formula", "q", "search", "email"})
_DENY_PREFIXES = ("amount", "note", "password", "token", "secret")
_DENY_SUFFIXES = ("_json",)
#: ``"GET /path?query HTTP/1.1"`` request line of a uvicorn.access message.
_REQUEST_LINE_QUERY = re.compile(r"(\"[A-Z]+ [^\s?\"]*)\?[^\s\"]*( HTTP/)")


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


def strip_access_query(
    _logger: object, _method: str, event_dict: Mapping[str, object]
) -> Mapping[str, object]:
    """structlog foreign-record processor: drop the query string from ``uvicorn.access`` paths.

    Works on the already-formatted message (structlog clears ``record.args`` before
    the pre-chain runs), so the record is never mutated; returns a new dict.
    """
    record = event_dict.get("_record")
    message = event_dict.get("event")
    if not isinstance(record, logging.LogRecord) or record.name != "uvicorn.access":
        return event_dict
    if not isinstance(message, str):
        return event_dict
    return {**event_dict, "event": _REQUEST_LINE_QUERY.sub(r"\1\2", message)}


#: Final ``Type: message`` line(s) of a formatted traceback (T-Q254): the message
#: may carry amounts, names or SQL parameters, so only the type name is kept.
_EXC_HEADER_PREFIXES = ("Traceback", "During handling", "The above exception", "...")
_EXC_TYPE_LINE = re.compile(r"^([A-Za-z_][\w.]*)(: .*)?$")


def _scrub_traceback(text: str) -> str:
    out: list[str] = []
    dropping = False
    for line in text.split("\n"):
        if not line or line[0] in " \t" or line.startswith(_EXC_HEADER_PREFIXES):
            dropping = False
            out.append(line)
            continue
        if dropping:
            continue
        match = _EXC_TYPE_LINE.match(line)
        if match is None:
            out.append(line)
            continue
        out.append(f"{match.group(1)}: {REDACTED}" if match.group(2) is not None else line)
        dropping = match.group(2) is not None
    return "\n".join(out)


def scrub_exception_text(
    _logger: object, _method: str, event_dict: Mapping[str, object]
) -> Mapping[str, object]:
    """structlog processor: keep exception types and frames, drop exception messages.

    Runs after ``format_exc_info``; returns a new dict, never mutates the input.
    """
    text = event_dict.get("exception")
    if not isinstance(text, str):
        return event_dict
    return {**event_dict, "exception": _scrub_traceback(text)}


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
        scrub_exception_text,
        redact_sensitive,
        structlog.processors.JSONRenderer(),
    ]


def _is_our_handler(handler: logging.Handler) -> bool:
    return isinstance(handler.formatter, structlog.stdlib.ProcessorFormatter)


def configure() -> None:
    """Configure structlog + stdlib root logger.

    Idempotent — safe to call from ``create_app`` and from tests. The
    stdlib root logger is pointed at the same JSON renderer so uvicorn
    access logs and third-party libraries land in the same stream.
    """
    # Idempotence state is the installed handler itself (its structlog formatter
    # is the marker), not a module-level flag (T-Q263).
    if any(_is_our_handler(h) for h in logging.getLogger().handlers):
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
                strip_access_query,
                structlog.processors.format_exc_info,
                scrub_exception_text,
                redact_sensitive,
            ],
            processor=structlog.processors.JSONRenderer(),
        )
    )

    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Uvicorn silences propagation by default; flip it so the structured
    # formatter owns the output pipeline.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True


def get_logger(name: str | None = None) -> BoundLogger:
    """Return a structlog-bound logger; thin passthrough for callers."""
    return structlog.stdlib.get_logger(name) if name else structlog.stdlib.get_logger()


def bind_request_id(request_id: str) -> None:
    """Bind ``request_id`` to the current contextvar scope."""
    structlog.contextvars.bind_contextvars(request_id=request_id)


def clear_request_id() -> None:
    """Clear every bound contextvar — called after a request completes."""
    structlog.contextvars.clear_contextvars()
