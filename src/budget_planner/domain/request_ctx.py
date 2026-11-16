"""Per-request forensic context carried through to the audit log (T-D14).

The web layer builds a :class:`RequestCtx` from the inbound
``fastapi.Request`` via :func:`budget_planner.web.deps.get_request_ctx`
and threads it into service calls. Services pass it down to
:func:`budget_planner.repositories._shared.write_audit`, which writes
the four columns added by migration ``0013_audit_request_ctx.sql``
onto every mutation's audit row.

The dataclass is frozen + slots per project convention (ADR-0021):
immutable, cheap to pass, trivially copyable. All fields are optional
because:

* historical rows (pre-T-D14) and system-bootstrap writes have no
  originating HTTP request;
* ``user_id`` stays ``None`` until the auth bootstrap (T-D02) wires a
  session user onto ``request.state``;
* ``session_id`` is likewise session-dependent;
* ``ip`` and ``user_agent`` are opportunistic — a reverse proxy may
  strip ``user-agent`` and ``request.client`` is ``None`` for ASGI
  test transports.

Use :meth:`RequestCtx.empty` as the default sentinel in call sites
that have not yet been plumbed through to receive a real context —
``write_audit`` treats an empty context the same as pre-T-D14 behaviour
(every new column written as NULL).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RequestCtx:
    """Immutable snapshot of the inbound request's forensic metadata."""

    ip: str | None
    user_id: int | None
    session_id: str | None
    user_agent: str | None

    @classmethod
    def empty(cls) -> RequestCtx:
        """Return a context with every field cleared.

        Used as the default value on :func:`write_audit` so existing
        call sites keep working without being retrofitted — the four
        new ``audit_log`` columns land as NULL, matching pre-T-D14
        behaviour.
        """
        return cls(ip=None, user_id=None, session_id=None, user_agent=None)


__all__ = ["RequestCtx"]
