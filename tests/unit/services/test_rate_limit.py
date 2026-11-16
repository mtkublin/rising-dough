"""T-D09 — fixed-window limiter: bucket maths, count-then-check, pruning (ADR-0072)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from budget_planner.config import Settings
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import rate_limit as repo
from budget_planner.services import rate_limit as svc
from budget_planner.services.rate_limit import RateDecision, RateRule

pytestmark = pytest.mark.unit

T0 = datetime(2026, 11, 3, 12, 0, 10, tzinfo=UTC)
PER_MINUTE = (RateRule(limit=2, window_seconds=60),)


def test_bucket_start_floors_to_window() -> None:
    assert svc.bucket_start(T0, 60) == datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    assert svc.bucket_start(T0, 3600) == datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    assert svc.bucket_start(T0 + timedelta(minutes=59), 3600) == datetime(
        2026, 11, 3, 12, 0, tzinfo=UTC
    )


def test_counter_key_embeds_window() -> None:
    assert svc.counter_key("login", 60, "ip=1") != svc.counter_key("login", 3600, "ip=1")


@pytest.mark.parametrize(("limit", "window"), [(0, 60), (1, 0), (1, 86_401)])
def test_rate_rule_rejects_invalid_values(limit: int, window: int) -> None:
    with pytest.raises(ValueError, match="must be"):
        RateRule(limit=limit, window_seconds=window)


def test_consume_allows_up_to_limit_then_denies(conn: sqlite3.Connection) -> None:
    decisions = [svc.consume(conn, "s", "id", PER_MINUTE, now=T0) for _ in range(3)]
    assert [d.allowed for d in decisions] == [True, True, False]
    denied = decisions[-1]
    assert denied.retry_after_seconds == 50  # 12:00:10 → bucket ends 12:01:00
    assert denied.scope == "s"


def test_throttled_attempts_still_count(conn: sqlite3.Connection) -> None:
    for _ in range(4):
        svc.consume(conn, "s", "id", PER_MINUTE, now=T0)
    start = svc.bucket_start(T0, 60)
    assert repo.get_count(conn, svc.counter_key("s", 60, "id"), start) == 4


def test_window_reset_allows_again(conn: sqlite3.Connection) -> None:
    for _ in range(3):
        svc.consume(conn, "s", "id", PER_MINUTE, now=T0)
    later = T0 + timedelta(seconds=50)
    assert svc.consume(conn, "s", "id", PER_MINUTE, now=later).allowed


def test_identities_and_scopes_do_not_interfere(conn: sqlite3.Connection) -> None:
    for _ in range(3):
        svc.consume(conn, "s", "a", PER_MINUTE, now=T0)
    assert svc.consume(conn, "s", "b", PER_MINUTE, now=T0).allowed
    assert svc.consume(conn, "other", "a", PER_MINUTE, now=T0).allowed


def test_longest_violated_window_wins(conn: sqlite3.Connection) -> None:
    rules = (RateRule(limit=1, window_seconds=60), RateRule(limit=1, window_seconds=3600))
    svc.consume(conn, "s", "id", rules, now=T0)
    denied = svc.consume(conn, "s", "id", rules, now=T0)
    assert not denied.allowed
    assert denied.retry_after_seconds == 3600 - 10


def test_retry_after_is_at_least_one_second(conn: sqlite3.Connection) -> None:
    edge = datetime(2026, 11, 3, 12, 0, 59, 999_000, tzinfo=UTC)
    svc.consume(conn, "s", "id", (RateRule(1, 60),), now=edge)
    assert svc.consume(conn, "s", "id", (RateRule(1, 60),), now=edge).retry_after_seconds == 1


def test_no_rules_is_always_allowed(conn: sqlite3.Connection) -> None:
    assert svc.consume(conn, "s", "id", (), now=T0) is svc.ALLOWED
    assert conn.execute("SELECT COUNT(*) FROM auth_rate_limit").fetchone()[0] == 0


def test_consume_prunes_stale_buckets(conn: sqlite3.Connection) -> None:
    svc.consume(conn, "s", "old", PER_MINUTE, now=T0)
    svc.consume(conn, "s", "new", PER_MINUTE, now=T0 + svc.RETENTION + timedelta(minutes=1))
    keys = [r[0] for r in conn.execute("SELECT key FROM auth_rate_limit").fetchall()]
    assert keys == [svc.counter_key("s", 60, "new")]


def test_repo_prune_returns_rowcount(conn: sqlite3.Connection) -> None:
    repo.hit(conn, "k", T0)
    assert repo.prune(conn, T0) == 0
    assert repo.prune(conn, T0 + timedelta(seconds=1)) == 1
    assert repo.get_count(conn, "k", T0) == 0


def test_combine_picks_longest_denial() -> None:
    short = RateDecision(allowed=False, retry_after_seconds=5, scope="a")
    long = RateDecision(allowed=False, retry_after_seconds=50, scope="b")
    assert svc.combine(svc.ALLOWED, svc.ALLOWED) is svc.ALLOWED
    assert svc.combine(short, svc.ALLOWED, long) == long


def test_rule_builders_follow_settings() -> None:
    s = Settings(
        _env_file=None,
        rate_limit_login_per_minute=3,
        rate_limit_login_per_hour=9,
        rate_limit_login_ip_per_hour=50,
        rate_limit_passkey_login_per_minute=4,
        rate_limit_passkey_login_per_hour=8,
        rate_limit_register_per_minute=2,
        rate_limit_register_per_hour=6,
    )
    assert svc.login_rules(s) == (RateRule(3, 60), RateRule(9, 3600))
    assert svc.login_ip_rules(s) == (RateRule(50, 3600),)
    assert svc.passkey_login_rules(s) == (RateRule(4, 60), RateRule(8, 3600))
    assert svc.register_rules(s) == (RateRule(2, 60), RateRule(6, 3600))


def test_kill_switch_yields_no_rules() -> None:
    s = Settings(_env_file=None, rate_limit_enabled=False)
    assert svc.login_rules(s) == ()
    assert svc.login_ip_rules(s) == ()
    assert svc.passkey_login_rules(s) == ()
    assert svc.register_rules(s) == ()


def test_default_limits_match_adr() -> None:
    s = Settings(_env_file=None)
    assert svc.login_rules(s) == (RateRule(5, 60), RateRule(20, 3600))
    assert svc.login_ip_rules(s) == (RateRule(100, 3600),)


def test_normalise_email() -> None:
    assert svc.normalise_email("  Owner@Example.TEST ") == "owner@example.test"


def test_audit_throttled_writes_auth_event(conn: sqlite3.Connection) -> None:
    ctx = RequestCtx(ip="10.0.0.1", user_id=None, session_id=None, user_agent="ua")
    svc.audit_throttled(conn, ctx, scope="login", email="a@b.test")
    svc.audit_throttled(conn, ctx, scope="passkey_register", user_id=1)
    rows = conn.execute(
        "SELECT entity_type, entity_id, operation, new_json, ip, user_id FROM audit_log "
        "WHERE entity_type = 'auth_event' ORDER BY id"
    ).fetchall()
    assert [(r[0], r[1], r[2], r[4], r[5]) for r in rows] == [
        ("auth_event", 0, "create", "10.0.0.1", None),
        ("auth_event", 1, "create", "10.0.0.1", 1),
    ]
    assert json.loads(rows[0][3]) == {
        "event": "rate_limited",
        "scope": "login",
        "email": "a@b.test",
    }
    assert json.loads(rows[1][3]) == {"event": "rate_limited", "scope": "passkey_register"}
