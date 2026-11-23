"""T-UR32 - first-run setup service (ADR-0134 section 9)."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from typing import Any

import pytest
from structlog.testing import capture_logs

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.services import setup as setup_service
from budget_planner.services.setup import (
    MSG_CONFIRM_MISMATCH,
    SetupClosedError,
    SetupDraft,
    check_token,
    complete_setup,
    hash_token,
    is_open,
)
from budget_planner.services.users import UserInputError
from tests.auth_support import FAKE_HASHER, TEST_PASSWORD

TOKEN = "-".join(("tok", "unit", "test", "value"))
TOKEN_HASH = hash_token(TOKEN)
TOO_SHORT = "short"
OTHER_CONFIRM = TOKEN + "-x"
BLANK = "  "
NOT_HEX = "nothex"
WRONG_VALUE = "nope"
MISMATCH = "different-password"
PW_X = "pw-x"
PASSWORD = TEST_PASSWORD


def _settings(**kwargs: Any) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        cookie_secret="x" * 32,
        webauthn_rp_id="budget.example.test",
        webauthn_origin="https://budget.example.test",
        **kwargs,
    )


def _draft(**kw: str) -> SetupDraft:
    base = {
        "email": "Boss@Example.Test",
        "name": "Boss",
        "password": PASSWORD,
        "password_confirm": PASSWORD,
    }
    return SetupDraft(**{**base, **kw})


def _open_settings() -> Settings:
    return _settings(planner_setup_token_hash=TOKEN_HASH)


_COUNT_SQL = {
    "users": "SELECT COUNT(*) FROM users",
    "setup_token_consumed": "SELECT COUNT(*) FROM setup_token_consumed",
}


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(_COUNT_SQL[table]).fetchone()[0])


def test_hash_is_lowercase_sha256_hex() -> None:
    assert hash_token("abc") == hashlib.sha256(b"abc").hexdigest()
    assert len(hash_token("abc")) == 64


def test_setting_normalises_and_rejects_bad_hash() -> None:
    assert (
        _settings(planner_setup_token_hash=TOKEN_HASH.upper()).planner_setup_token_hash
        == TOKEN_HASH
    )
    assert _settings(planner_setup_token_hash=BLANK).planner_setup_token_hash is None
    assert _settings().planner_setup_token_hash is None
    with pytest.raises(ValueError, match="sha256"):
        _settings(planner_setup_token_hash=NOT_HEX)


def test_open_with_hash_and_empty_instance(conn: sqlite3.Connection) -> None:
    assert is_open(conn, _open_settings()) is True


def test_closed_without_hash(conn: sqlite3.Connection) -> None:
    assert is_open(conn, _settings()) is False
    assert check_token(conn, _settings(), TOKEN) is False


def test_closed_when_bootstrap_admin_configured(conn: sqlite3.Connection) -> None:
    both = _settings(
        planner_setup_token_hash=TOKEN_HASH,
        admin_email="a@example.test",
        admin_initial_password=PW_X,
    )
    assert is_open(conn, both) is False
    half = _settings(planner_setup_token_hash=TOKEN_HASH, admin_email="a@example.test")
    assert is_open(conn, half) is False


def test_closed_in_dev_env_because_dev_bootstrap_applies(conn: sqlite3.Connection) -> None:
    dev = Settings(
        _env_file=None,
        env="dev",
        cookie_secret="x" * 32,
        planner_setup_token_hash=TOKEN_HASH,
    )
    assert is_open(conn, dev) is False


def test_closed_when_a_user_exists(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO users(name, email, password_hash, is_admin) "
        "VALUES ('U', 'u@example.test', 'h', 0)"
    )
    assert is_open(conn, _open_settings()) is False
    assert check_token(conn, _open_settings(), TOKEN) is False


def test_closed_when_marker_present(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO setup_token_consumed(id, consumed_at) "
        "VALUES (1, '2026-01-01T00:00:00.000000Z')"
    )
    assert is_open(conn, _open_settings()) is False


def test_check_token_right_and_wrong(conn: sqlite3.Connection) -> None:
    settings = _open_settings()
    assert check_token(conn, settings, TOKEN) is True
    assert check_token(conn, settings, TOKEN + "x") is False
    assert check_token(conn, settings, "") is False


def test_complete_setup_creates_admin_and_marker_atomically(conn: sqlite3.Connection) -> None:
    admin = complete_setup(conn, _open_settings(), token=TOKEN, draft=_draft(), hasher=FAKE_HASHER)
    row = conn.execute("SELECT * FROM users WHERE id = ?", (admin.id,)).fetchone()
    assert row["email"] == "boss@example.test"
    assert row["name"] == "Boss"
    assert row["is_admin"] == 1
    assert row["must_change_password"] == 0
    assert row["password_hash"] == FAKE_HASHER.hash(PASSWORD)
    marker = conn.execute("SELECT * FROM setup_token_consumed").fetchall()
    assert [(m["id"], m["consumed_at"]) for m in marker] == [(1, clock.iso_utc(clock.utc_now()))]
    audit = conn.execute(
        "SELECT operation, entity_id, new_json FROM audit_log WHERE entity_type = 'setup_token'"
    ).fetchall()
    assert len(audit) == 1
    assert (audit[0]["operation"], audit[0]["entity_id"]) == ("create", 1)
    assert json.loads(audit[0]["new_json"]) == {
        "consumed_at": clock.iso_utc(clock.utc_now()),
        "user_id": admin.id,
    }
    assert is_open(conn, _open_settings()) is False


def test_second_setup_with_same_token_is_refused(conn: sqlite3.Connection) -> None:
    complete_setup(conn, _open_settings(), token=TOKEN, draft=_draft(), hasher=FAKE_HASHER)
    users_before = _count(conn, "users")
    with pytest.raises(SetupClosedError):
        complete_setup(
            conn,
            _open_settings(),
            token=TOKEN,
            draft=_draft(email="second@example.test"),
            hasher=FAKE_HASHER,
        )
    assert _count(conn, "users") == users_before
    assert _count(conn, "setup_token_consumed") == 1


def test_wrong_token_changes_nothing(conn: sqlite3.Connection) -> None:
    users_before = _count(conn, "users")
    with pytest.raises(SetupClosedError):
        complete_setup(
            conn, _open_settings(), token=WRONG_VALUE, draft=_draft(), hasher=FAKE_HASHER
        )
    assert _count(conn, "users") == users_before
    assert _count(conn, "setup_token_consumed") == 0


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        ({"email": "not-an-email"}, {"email"}),
        ({"password": TOO_SHORT, "password_confirm": TOO_SHORT}, {"password"}),
        ({"password_confirm": OTHER_CONFIRM}, {"password_confirm"}),
    ],
)
def test_invalid_input_leaves_token_unconsumed(
    conn: sqlite3.Connection, kw: dict[str, str], expected: set[str]
) -> None:
    users_before = _count(conn, "users")
    with pytest.raises(UserInputError) as info:
        complete_setup(conn, _open_settings(), token=TOKEN, draft=_draft(**kw), hasher=FAKE_HASHER)
    assert set(info.value.fields) == expected
    assert _count(conn, "users") == users_before
    assert _count(conn, "setup_token_consumed") == 0
    assert is_open(conn, _open_settings()) is True


def test_mismatch_message(conn: sqlite3.Connection) -> None:
    with pytest.raises(UserInputError) as info:
        complete_setup(
            conn,
            _open_settings(),
            token=TOKEN,
            draft=_draft(password_confirm=MISMATCH),
            hasher=FAKE_HASHER,
        )
    assert info.value.fields == {"password_confirm": MSG_CONFIRM_MISMATCH}


def test_token_and_hash_never_logged(
    conn: sqlite3.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _open_settings()
    with caplog.at_level(logging.DEBUG), capture_logs() as captured:
        is_open(conn, settings)
        check_token(conn, settings, TOKEN)
        with pytest.raises(SetupClosedError):
            complete_setup(
                conn, settings, token="wrong-" + TOKEN, draft=_draft(), hasher=FAKE_HASHER
            )
        complete_setup(conn, settings, token=TOKEN, draft=_draft(), hasher=FAKE_HASHER)
    assert [e["event"] for e in captured] == ["setup_rejected", "setup_completed"]
    blob = repr(captured) + "\n".join(r.getMessage() + repr(r.__dict__) for r in caplog.records)
    assert TOKEN not in blob
    assert TOKEN_HASH not in blob
    assert setup_service.hash_token("wrong-" + TOKEN) not in blob
