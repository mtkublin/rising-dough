"""Mutation-kill tests for ``services/users`` (T-Q247, ADR-0131).

Pins the exact refusal texts, the structured bootstrap log event, the race-to-error mapping in
``_atomically``, the outcome payloads and that the request context reaches every audit row.
Complements ``test_users.py`` and ``test_users_admin.py``.
"""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest
from structlog.testing import capture_logs

from budget_planner.config import Settings
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import users as users_repo
from budget_planner.services import _passwords, users as users_svc
from budget_planner.services.users import (
    CONCURRENT_CHANGE_MESSAGE,
    DEV_ADMIN_EMAIL,
    DUPLICATE_EMAIL_MESSAGE,
    EMAIL_MAX_LENGTH,
    INVALID_EMAIL_MESSAGE,
    NAME_MAX_LENGTH,
    NAME_TOO_LONG_MESSAGE,
    BootstrapAdminMissingEnv,
    PasswordChange,
    SchemaNotMigratedError,
    UserConflict,
    UserInputError,
    UserNotFound,
)

ADMIN_ID = 1
CTX = RequestCtx(ip="10.1.2.3", user_id=ADMIN_ID, session_id="sess-9", user_agent="pytest-ua")
PASSWORD = "initial-Pa55word!"  # noqa: S105  # pragma: allowlist secret


def _settings(env: str = "test", **kwargs: Any) -> Settings:
    return Settings(
        _env_file=None,
        env=env,  # type: ignore[arg-type]  # reason: literal env name from a str parameter
        cookie_secret="x" * 32,
        webauthn_rp_id="budget.example.test",
        webauthn_origin="https://budget.example.test",
        **kwargs,
    )


def _env_settings(email: str, env: str = "test") -> Settings:
    return _settings(env, admin_email=email, admin_initial_password=PASSWORD)


@pytest.fixture
def admin_conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.execute(
        "UPDATE users SET email = 'root@example.test', is_admin = 1 WHERE id = ?", (ADMIN_ID,)
    )
    return conn


def _draft(email: str, *, admin: bool | None = False, name: str = "") -> users_svc.UserDraft:
    return users_svc.build_draft(email=email, name=name, is_admin=admin)


def _audit(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'users' AND entity_id = ? ORDER BY id",
        (user_id,),
    ).fetchall()


def _assert_ctx(row: sqlite3.Row) -> None:
    assert (row["ip"], row["session_id"], row["user_agent"], row["actor_user_id"]) == (
        "10.1.2.3",
        "sess-9",
        "pytest-ua",
        ADMIN_ID,
    )


# --- credentials / schema ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [{"admin_email": "a@b.test"}, {"admin_initial_password": PASSWORD}],
)
def test_half_configured_env_message(kwargs: dict[str, Any]) -> None:
    with pytest.raises(BootstrapAdminMissingEnv) as err:
        users_svc.resolve_bootstrap_credentials(_settings("production", **kwargs))
    assert str(err.value) == (
        "Both BUDGET_PLANNER_ADMIN_EMAIL and BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD "
        "must be set (only one is)."
    )


def test_unmigrated_schema_message_and_non_production_noop() -> None:
    bare = sqlite3.connect(":memory:")
    bare.row_factory = sqlite3.Row
    bare.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    with pytest.raises(SchemaNotMigratedError) as err:
        users_svc.set_user_password(
            bare, 1, change=PasswordChange(password=PASSWORD, must_change_password=False)
        )
    assert str(err.value) == (
        "users table is missing the multi-user columns — apply migrations "
        "(0012_multi_user.sql) before starting the app."
    )
    with capture_logs() as logs:
        outcome = users_svc.bootstrap_admin(bare, _settings("dev"))
    assert outcome == users_svc.BootstrapOutcome(action="noop", reason="schema_not_migrated")
    assert logs[0]["log_level"] == "warning"
    with pytest.raises(SchemaNotMigratedError):
        users_svc.bootstrap_admin(bare, _settings("production"))


def test_production_without_credentials_message(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE users SET is_admin = 0")
    with pytest.raises(BootstrapAdminMissingEnv) as err:
        users_svc.bootstrap_admin(conn, _settings("production"))
    assert str(err.value) == (
        "No admin exists and BUDGET_PLANNER_ADMIN_EMAIL / "
        "BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD are not set (ADR-0061 §3)."
    )


# --- bootstrap outcomes and the structured log event ---------------------------------------------


def test_created_admin_outcome_hash_name_and_log_event(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE users SET email = 'legacy@example.test', is_admin = 0 WHERE id = 1")
    conn.execute("DELETE FROM users WHERE id != 1")
    conn.execute("UPDATE users SET deleted_at = '2020-01-01T00:00:00+00:00' WHERE id = 1")
    with capture_logs() as logs:
        outcome = users_svc.bootstrap_admin(conn, _env_settings("boss@sub.example.test"))
    assert outcome.action == "created"
    assert outcome.admin_email == "boss@sub.example.test"
    assert outcome.user_id is not None
    row = conn.execute("SELECT * FROM users WHERE id = ?", (outcome.user_id,)).fetchone()
    assert (row["name"], row["is_admin"], row["must_change_password"]) == ("boss", 1, 1)
    assert _passwords.verify_password(PASSWORD, row["password_hash"]) is True
    assert logs == [
        {
            "event": "admin_bootstrap",
            "log_level": "info",
            "action": "created",
            "admin_email": "boss@sub.example.test",
            "user_id": outcome.user_id,
            "source": "env",
            "reason": None,
            "legacy_adopted": False,
        }
    ]


def test_existing_admin_logs_info_and_other_reasons_log_warning(
    conn: sqlite3.Connection,
) -> None:
    conn.execute("UPDATE users SET email = 'root@example.test', is_admin = 1 WHERE id = 1")
    with capture_logs() as logs:
        exists = users_svc.bootstrap_admin(conn, _settings("test"))
    assert exists == users_svc.BootstrapOutcome(action="noop", reason="admin_exists")
    assert [(e["log_level"], e["reason"], e["source"], e["user_id"]) for e in logs] == [
        ("info", "admin_exists", None, None)
    ]
    conn.execute("UPDATE users SET is_admin = 0")
    with capture_logs() as logs2:
        none = users_svc.bootstrap_admin(conn, _settings("test"))
    assert none == users_svc.BootstrapOutcome(action="noop", reason="no_credentials")
    assert [(e["log_level"], e["reason"]) for e in logs2] == [("warning", "no_credentials")]


def test_dev_default_never_overwrites_a_legacy_owner_with_accounts(
    conn: sqlite3.Connection,
) -> None:
    conn.execute("INSERT INTO accounts(user_id, name, currency) VALUES (1, 'Main', 'PLN')")
    conn.execute("UPDATE users SET email = NULL, is_admin = 0 WHERE id = 1")
    with capture_logs() as logs:
        outcome = users_svc.bootstrap_admin(conn, _settings("dev"))
    assert outcome == users_svc.BootstrapOutcome(
        action="noop", user_id=1, admin_email=DEV_ADMIN_EMAIL, reason="legacy_data_present"
    )
    assert [(e["log_level"], e["source"], e["user_id"], e["reason"]) for e in logs] == [
        ("warning", "dev_default", 1, "legacy_data_present")
    ]


def test_promoting_an_existing_user_reports_the_credential_email(
    admin_conn: sqlite3.Connection,
) -> None:
    admin_conn.execute("UPDATE users SET is_admin = 0 WHERE id = 1")
    outcome = users_svc.bootstrap_admin(admin_conn, _env_settings("root@example.test"))
    assert outcome == users_svc.BootstrapOutcome(
        action="promoted", user_id=1, admin_email="root@example.test"
    )
    row = admin_conn.execute("SELECT email, is_admin FROM users WHERE id = 1").fetchone()
    assert (row["email"], row["is_admin"]) == ("root@example.test", 1)


def test_startup_wrapper_reports_noop_without_opening_the_db_and_passes_settings(
    conn: sqlite3.Connection,
) -> None:
    def never(_settings: Settings) -> sqlite3.Connection:
        raise AssertionError("the DB must not be opened")

    outcome = users_svc.bootstrap_admin_at_startup(_settings("test"), connect=never)
    assert outcome == users_svc.BootstrapOutcome(action="noop", reason="no_credentials")

    seen: list[Settings] = []

    class _Handle:
        closed = False

        def __getattr__(self, name: str) -> Any:
            return getattr(conn, name)

        def close(self) -> None:
            _Handle.closed = True

    def connect(settings: Settings) -> sqlite3.Connection:
        seen.append(settings)
        return _Handle()  # type: ignore[return-value]  # reason: delegating handle

    conn.execute("UPDATE users SET email = 'root@example.test', is_admin = 1 WHERE id = 1")
    configured = _env_settings("root@example.test")
    result = users_svc.bootstrap_admin_at_startup(configured, connect=connect)
    assert result == users_svc.BootstrapOutcome(action="noop", reason="admin_exists")
    assert seen == [configured]
    assert _Handle.closed is True


# --- exceptions and validation -------------------------------------------------------------------


def test_exception_texts_and_payloads() -> None:
    not_found = UserNotFound(5)
    assert (str(not_found), not_found.user_id) == ("user 5 not found", 5)
    conflict = UserConflict("nope")
    assert (str(conflict), conflict.message) == ("nope", "nope")
    invalid = UserInputError({"email": "bad", "name": "long"})
    assert str(invalid) == "email: bad; name: long"
    assert invalid.fields == {"email": "bad", "name": "long"}


def test_build_draft_length_boundaries_and_messages() -> None:
    local = "a" * (EMAIL_MAX_LENGTH - len("@x.test"))
    longest = f"{local}@x.test"
    assert len(longest) == EMAIL_MAX_LENGTH
    assert _draft(longest).email == longest
    with pytest.raises(UserInputError) as too_long:
        _draft("a" + longest)
    assert too_long.value.fields == {"email": INVALID_EMAIL_MESSAGE}

    exact = "n" * NAME_MAX_LENGTH
    assert _draft("a@b.test", name=exact).name == exact
    with pytest.raises(UserInputError) as name_err:
        _draft("a@b.test", name=exact + "n")
    assert name_err.value.fields == {"name": NAME_TOO_LONG_MESSAGE}
    with pytest.raises(UserInputError) as both:
        users_svc.build_draft(email="nope", name=exact + "n", is_admin=None)
    assert both.value.fields == {"email": INVALID_EMAIL_MESSAGE, "name": NAME_TOO_LONG_MESSAGE}


def test_build_draft_keeps_the_admin_flag_tristate() -> None:
    assert _draft("a@b.test", admin=None).is_admin is None
    assert _draft("a@b.test", admin=True).is_admin is True
    assert _draft("a@b.test", admin=False).is_admin is False


# --- _atomically mapping -------------------------------------------------------------------------


def test_duplicate_email_race_maps_to_a_field_error(
    admin_conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    users_svc.create_user(admin_conn, ADMIN_ID, _draft("dup@x.test"))
    monkeypatch.setattr(users_repo, "get_by_email_live", lambda *_a, **_k: None)  # lose the race
    with pytest.raises(UserInputError) as err:
        users_svc.create_user(admin_conn, ADMIN_ID, _draft("dup@x.test"))
    assert err.value.fields == {"email": DUPLICATE_EMAIL_MESSAGE}


@pytest.mark.parametrize("text", ["database is locked", "database table is busy", "locked busy"])
def test_writer_lock_wait_maps_to_a_conflict(
    admin_conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise sqlite3.OperationalError(text)

    monkeypatch.setattr(users_repo, "create_user", boom)
    with pytest.raises(UserConflict) as err:
        users_svc.create_user(admin_conn, ADMIN_ID, _draft("new@x.test"))
    assert err.value.message == CONCURRENT_CHANGE_MESSAGE


def test_other_operational_errors_propagate(
    admin_conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise sqlite3.OperationalError("no such table: users")

    monkeypatch.setattr(users_repo, "create_user", boom)
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        users_svc.create_user(admin_conn, ADMIN_ID, _draft("new@x.test"))


# --- roster operations ---------------------------------------------------------------------------


def test_missing_targets_carry_the_requested_id(admin_conn: sqlite3.Connection) -> None:
    user, _ = users_svc.create_user(admin_conn, ADMIN_ID, _draft("gone@x.test"))
    users_svc.soft_delete_user(admin_conn, ADMIN_ID, user.id)
    for call in (
        lambda uid: users_svc.get_live_user(admin_conn, uid),
        lambda uid: users_svc.edit_user(admin_conn, ADMIN_ID, uid, _draft("z@x.test")),
        lambda uid: users_svc.reset_password(admin_conn, ADMIN_ID, uid),
        lambda uid: users_svc.soft_delete_user(admin_conn, ADMIN_ID, uid),
    ):
        for missing in (user.id, 9_999):
            with pytest.raises(UserNotFound) as err:
                call(missing)
            assert err.value.user_id == missing


def test_request_context_reaches_every_audit_row(admin_conn: sqlite3.Connection) -> None:
    user, _ = users_svc.create_user(admin_conn, ADMIN_ID, _draft("ctx@x.test"), request_ctx=CTX)
    _assert_ctx(_audit(admin_conn, user.id)[-1])
    users_svc.edit_user(
        admin_conn, ADMIN_ID, user.id, _draft("ctx2@x.test", name="Cee"), request_ctx=CTX
    )
    _assert_ctx(_audit(admin_conn, user.id)[-1])
    users_svc.reset_password(admin_conn, ADMIN_ID, user.id, request_ctx=CTX)
    _assert_ctx(_audit(admin_conn, user.id)[-1])
    users_svc.soft_delete_user(admin_conn, ADMIN_ID, user.id, request_ctx=CTX)
    _assert_ctx(_audit(admin_conn, user.id)[-1])
