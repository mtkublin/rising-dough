"""Fixed-window rate limiting for the auth routes (T-D09, ADR-0072).

Pure policy over :mod:`budget_planner.repositories.rate_limit`:

- A :class:`RateRule` is ``limit`` hits per ``window_seconds``.
- :func:`consume` **counts first, then checks**: every attempt increments
  every rule's current bucket — throttled attempts and successful logins
  included — and the call is denied when any bucket is over its limit.
- Counter keys embed the window (``<scope>:<window>s:<identity>``) so a
  minute bucket and an hour bucket starting at the same instant never share
  a row.
- Stale buckets are pruned opportunistically on every write.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Final

from budget_planner.config import Settings
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import rate_limit as rate_limit_repo
from budget_planner.repositories._shared import transaction, write_audit

AUTH_EVENT_ENTITY: Final = "auth_event"
UNKNOWN_USER_ENTITY_ID: Final = 0
MINUTE: Final = 60
HOUR: Final = 3600
# Buckets older than this are deleted. Must exceed every configured window.
RETENTION: Final = timedelta(days=1)

SCOPE_LOGIN: Final = "login"
SCOPE_LOGIN_IP: Final = "login_ip"
SCOPE_PASSKEY_LOGIN: Final = "passkey_login"
SCOPE_REGISTER: Final = "passkey_register"


@dataclass(frozen=True, slots=True)
class RateRule:
    """At most ``limit`` hits per fixed ``window_seconds`` window."""

    limit: int
    window_seconds: int

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("limit must be >= 1")
        if not 0 < self.window_seconds <= RETENTION.total_seconds():
            raise ValueError("window_seconds must be in (0, RETENTION]")


@dataclass(frozen=True, slots=True)
class RateDecision:
    """Outcome of :func:`consume`. ``retry_after_seconds`` is 0 when allowed."""

    allowed: bool
    retry_after_seconds: int = 0
    scope: str = ""


ALLOWED: Final = RateDecision(allowed=True)


def bucket_start(now: datetime, window_seconds: int) -> datetime:
    """Floor ``now`` (UTC) to the start of its ``window_seconds`` window."""
    epoch = int(now.astimezone(UTC).timestamp())
    return datetime.fromtimestamp(epoch - epoch % window_seconds, tz=UTC)


def counter_key(scope: str, window_seconds: int, identity: str) -> str:
    """Build the opaque ``auth_rate_limit.key`` for one rule."""
    return f"{scope}:{window_seconds}s:{identity}"


def _retry_after(now: datetime, start: datetime, window_seconds: int) -> int:
    remaining = (start + timedelta(seconds=window_seconds) - now).total_seconds()
    return max(1, math.ceil(remaining))


def consume(
    conn: sqlite3.Connection,
    scope: str,
    identity: str,
    rules: Sequence[RateRule],
    *,
    now: datetime,
) -> RateDecision:
    """Record one attempt against every rule; deny if any bucket is now over limit."""
    if not rules:
        return ALLOWED
    retry_after = 0
    with transaction(conn):
        for rule in rules:
            start = bucket_start(now, rule.window_seconds)
            count = rate_limit_repo.hit(
                conn, counter_key(scope, rule.window_seconds, identity), start
            )
            if count > rule.limit:
                retry_after = max(retry_after, _retry_after(now, start, rule.window_seconds))
        rate_limit_repo.prune(conn, now - RETENTION)
    if retry_after:
        return RateDecision(allowed=False, retry_after_seconds=retry_after, scope=scope)
    return ALLOWED


def combine(*decisions: RateDecision) -> RateDecision:
    """Merge decisions: denied if any is denied, with the longest ``Retry-After``."""
    denied = [d for d in decisions if not d.allowed]
    if not denied:
        return ALLOWED
    return max(denied, key=lambda d: d.retry_after_seconds)


def audit_throttled(
    conn: sqlite3.Connection,
    ctx: RequestCtx,
    *,
    scope: str,
    user_id: int | None = None,
    email: str | None = None,
) -> None:
    """Write one ``auth_event`` audit row for a throttled attempt."""
    payload: dict[str, str] = {"event": "rate_limited", "scope": scope}
    if email:
        payload["email"] = email
    with transaction(conn):
        write_audit(
            conn,
            entity_type=AUTH_EVENT_ENTITY,
            entity_id=UNKNOWN_USER_ENTITY_ID if user_id is None else user_id,
            operation="create",
            prev=None,
            new=payload,
            request_ctx=replace(ctx, user_id=user_id),
        )


# ---------------------------------------------------------------------------
# Rule sets from settings (empty when the kill switch is off)
# ---------------------------------------------------------------------------


def _rules(settings: Settings, *pairs: tuple[int, int]) -> tuple[RateRule, ...]:
    if not settings.rate_limit_enabled:
        return ()
    return tuple(RateRule(limit=limit, window_seconds=window) for limit, window in pairs)


def login_rules(settings: Settings) -> tuple[RateRule, ...]:
    """Per IP + email: password login."""
    return _rules(
        settings,
        (settings.rate_limit_login_per_minute, MINUTE),
        (settings.rate_limit_login_per_hour, HOUR),
    )


def login_ip_rules(settings: Settings) -> tuple[RateRule, ...]:
    """Per IP: backstop against spraying many emails from one address."""
    return _rules(settings, (settings.rate_limit_login_ip_per_hour, HOUR))


def passkey_login_rules(settings: Settings) -> tuple[RateRule, ...]:
    """Per IP: usernameless passkey login finish."""
    return _rules(
        settings,
        (settings.rate_limit_passkey_login_per_minute, MINUTE),
        (settings.rate_limit_passkey_login_per_hour, HOUR),
    )


def register_rules(settings: Settings) -> tuple[RateRule, ...]:
    """Per user: passkey registration finish."""
    return _rules(
        settings,
        (settings.rate_limit_register_per_minute, MINUTE),
        (settings.rate_limit_register_per_hour, HOUR),
    )


def normalise_email(email: str) -> str:
    """Case-fold + trim so ``A@x`` and ``a@x `` share one counter."""
    return email.strip().lower()
