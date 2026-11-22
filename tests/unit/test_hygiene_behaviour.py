"""T-Q271: behaviour kept by the hygiene sweep (typed errors, logged sentinels, rollback)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI
from structlog.testing import capture_logs

from budget_planner.db.migrate import _begin_commit
from budget_planner.domain.errors import InvariantError, require_present
from budget_planner.services import replication_health
from budget_planner.web import app as web_app, auth_cookies
from budget_planner.web.entry_forms import EntryCheck


class _BadCloseConnection(sqlite3.Connection):
    def close(self) -> None:
        raise sqlite3.ProgrammingError("boom")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute("CREATE TABLE t (n INTEGER)")
    return conn


def _count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM t").fetchone()[0])


def test_require_present_returns_value_and_raises_invariant_error_on_none() -> None:
    assert require_present(7, "amount") == 7
    with pytest.raises(InvariantError, match="amount is missing"):
        require_present(None, "amount")


def test_begin_commit_commits_on_success() -> None:
    conn = _conn()
    with _begin_commit(conn):
        conn.execute("INSERT INTO t VALUES (1)")
    assert not conn.in_transaction
    assert _count(conn) == 1


def test_begin_commit_rolls_back_and_reraises_the_original_error() -> None:
    conn = _conn()
    with pytest.raises(ZeroDivisionError), _begin_commit(conn):
        conn.execute("INSERT INTO t VALUES (1)")
        raise ZeroDivisionError
    assert not conn.in_transaction
    assert _count(conn) == 0


def test_missing_replication_status_file_is_none_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    missing = str(tmp_path / "status.json")
    with caplog.at_level(logging.DEBUG, logger=replication_health.__name__):
        assert replication_health.read_status_text(missing) is None
    assert [r.getMessage() for r in caplog.records] == [
        f"replication status file absent: {missing}"
    ]


def test_malformed_auth_envelope_is_none_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger=auth_cookies.__name__):
        assert auth_cookies._decode_envelope("secret", "a.a") is None
    assert [r.getMessage() for r in caplog.records] == ["auth envelope is not valid base64"]


def test_close_failure_of_a_parked_connection_is_logged_not_swallowed() -> None:
    conn = sqlite3.connect(":memory:", factory=_BadCloseConnection)
    app = cast(FastAPI, SimpleNamespace(state=SimpleNamespace(pool=conn)))
    with capture_logs() as logs:
        web_app._close_app_connections(app)
    assert [(e["event"], e["attr"], e["error_type"]) for e in logs] == [
        ("app_connection_close_failed", "pool", "ProgrammingError")
    ]


def test_entry_check_valid_values_returns_parsed_date_and_amount() -> None:
    check = EntryCheck(op_date=date(2026, 11, 3), minor=1250)
    assert check.valid_values() == (date(2026, 11, 3), 1250)


def test_entry_check_valid_values_raises_when_amount_missing() -> None:
    with pytest.raises(InvariantError, match="validated amount is missing"):
        EntryCheck(op_date=date(2026, 11, 3)).valid_values()
