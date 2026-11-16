"""T-D19 — admin bootstrap service (ADR-0061 §3, ADR-0069)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

import pytest
from structlog.testing import capture_logs

from budget_planner.config import Settings
from budget_planner.repositories import users as users_repo
from budget_planner.repositories.users import UserNotFoundError
from budget_planner.services import _passwords, users as users_service
from budget_planner.services.users import (
    DEV_ADMIN_EMAIL,
    DEV_ADMIN_PASSWORD,
    BootstrapAdminMissingEnv,
    PasswordChange,
    SchemaNotMigratedError,
    bootstrap_admin,
    bootstrap_admin_at_startup,
    resolve_bootstrap_credentials,
    set_user_password,
)

ADMIN_EMAIL = "Owner@Example.Test"
ADMIN_PASSWORD = "initial-Pa55word!"  # noqa: S105  # pragma: allowlist secret
OTHER_PASSWORD = "x-other-pw"  # noqa: S105  # pragma: allowlist secret
KEPT_HASH = "keep"


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_passwords, "DEFAULT_ROUNDS", 4)


def _settings(env: str = "test", **kwargs: Any) -> Settings:
    return Settings(_env_file=None, env=env, cookie_secret="x" * 32, **kwargs)  # type: ignore[arg-type]


def _env_settings(env: str = "test") -> Settings:
    return _settings(env, admin_email=ADMIN_EMAIL, admin_initial_password=ADMIN_PASSWORD)


def _user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    assert row is not None
    return row


def _retire_legacy_row(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE users SET email = 'legacy@example.test' WHERE id = 1")


def _add_account(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute(
        "INSERT INTO accounts(user_id, name, currency) VALUES (?, 'Main', 'PLN')", (user_id,)
    )


def _user_audit(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM audit_log WHERE entity_type = 'users' ORDER BY id"))


# --- resolve_bootstrap_credentials -------------------------------------------


def test_resolve_prefers_env_and_forces_rotation() -> None:
    creds = resolve_bootstrap_credentials(_env_settings("dev"))
    assert creds is not None
    assert creds.email == ADMIN_EMAIL.lower()
    assert creds.must_change_password is True
    assert creds.source == "env"
    assert ADMIN_PASSWORD not in repr(creds)


def test_resolve_dev_default_when_env_missing() -> None:
    creds = resolve_bootstrap_credentials(_settings("dev"))
    assert creds is not None
    assert (creds.email, creds.password) == (DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD)
    assert creds.must_change_password is False
    assert creds.source == "dev_default"


@pytest.mark.parametrize("env", ["test", "production"])
def test_resolve_none_outside_dev_without_env(env: str) -> None:
    assert resolve_bootstrap_credentials(_settings(env)) is None


@pytest.mark.parametrize(
    "kwargs",
    [{"admin_email": ADMIN_EMAIL}, {"admin_initial_password": ADMIN_PASSWORD}],
)
def test_resolve_half_configured_raises(kwargs: dict[str, str]) -> None:
    with pytest.raises(BootstrapAdminMissingEnv, match="Both"):
        resolve_bootstrap_credentials(_settings("dev", **kwargs))


def test_settings_reads_planner_prefixed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUDGET_PLANNER_ADMIN_EMAIL", " Ops@Example.Test ")
    monkeypatch.setenv("BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD", ADMIN_PASSWORD)
    cfg = Settings(_env_file=None)
    assert cfg.admin_email == "ops@example.test"
    assert cfg.admin_initial_password is not None
    assert cfg.admin_initial_password.get_secret_value() == ADMIN_PASSWORD


def test_settings_blank_admin_values_are_unset() -> None:
    cfg = _settings(admin_email="  ", admin_initial_password="")
    assert cfg.admin_email is None
    assert cfg.admin_initial_password is None


def test_settings_reject_malformed_admin_email() -> None:
    with pytest.raises(ValueError, match="email"):
        _settings(admin_email="not-an-email")


# --- bootstrap_admin ---------------------------------------------------------


def test_bootstrap_admin_adopts_legacy_row(conn: sqlite3.Connection) -> None:
    outcome = bootstrap_admin(conn, _env_settings())

    assert outcome.action == "promoted"
    assert outcome.legacy_adopted is True
    assert outcome.user_id == 1
    row = _user(conn, 1)
    assert row["email"] == ADMIN_EMAIL.lower()
    assert row["is_admin"] == 1
    assert row["must_change_password"] == 1
    assert _passwords.verify_password(ADMIN_PASSWORD, row["password_hash"])
    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_bootstrap_admin_creates_user_with_system_categories(conn: sqlite3.Connection) -> None:
    _retire_legacy_row(conn)

    outcome = bootstrap_admin(conn, _env_settings())

    assert outcome.action == "created"
    assert outcome.user_id is not None
    row = _user(conn, outcome.user_id)
    assert (row["email"], row["is_admin"], row["must_change_password"]) == (
        ADMIN_EMAIL.lower(),
        1,
        1,
    )
    assert row["name"] == "owner"
    cats = {
        (r["name"], r["direction"], r["is_system"])
        for r in conn.execute("SELECT * FROM categories WHERE user_id = ?", (outcome.user_id,))
    }
    assert cats == {("Transit", "transit", 1), ("Reconciliation", "adjustment", 1)}
    audit = _user_audit(conn)
    assert [r["operation"] for r in audit] == ["create"]
    assert audit[0]["actor_user_id"] is None
    assert audit[0]["entity_id"] == outcome.user_id
    cat_audit = conn.execute(
        "SELECT count(*) FROM audit_log WHERE entity_type = 'categories'"
    ).fetchone()[0]
    assert cat_audit == 2


def test_bootstrap_admin_promotes_existing_user_by_email(conn: sqlite3.Connection) -> None:
    _retire_legacy_row(conn)
    cur = conn.execute(
        "INSERT INTO users(name, email, password_hash) VALUES ('Owner', ?, 'old-hash')",
        (ADMIN_EMAIL.upper(),),
    )
    user_id = int(cur.lastrowid or 0)

    outcome = bootstrap_admin(conn, _env_settings())

    assert outcome.action == "promoted"
    assert outcome.legacy_adopted is False
    assert outcome.user_id == user_id
    row = _user(conn, user_id)
    assert row["email"] == ADMIN_EMAIL.upper()  # unchanged on email match
    assert row["is_admin"] == 1
    assert row["must_change_password"] == 1
    assert _passwords.verify_password(ADMIN_PASSWORD, row["password_hash"])
    audit = _user_audit(conn)
    assert [r["operation"] for r in audit] == ["update"]


def test_bootstrap_admin_noop_when_admin_exists(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE users SET is_admin = 1, password_hash = ? WHERE id = 1", (KEPT_HASH,))

    outcome = bootstrap_admin(conn, _env_settings())

    assert outcome.action == "noop"
    assert outcome.reason == "admin_exists"
    assert _user(conn, 1)["password_hash"] == KEPT_HASH
    assert _user_audit(conn) == []


def test_bootstrap_admin_noop_with_admin_and_missing_env(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE users SET is_admin = 1 WHERE id = 1")
    outcome = bootstrap_admin(conn, _settings("production"))
    assert outcome.action == "noop"


def test_bootstrap_admin_ignores_soft_deleted_admin(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO users(name, email, is_admin, deleted_at) "
        "VALUES ('Gone', 'gone@example.test', 1, '2026-01-01T00:00:00.000Z')"
    )
    outcome = bootstrap_admin(conn, _env_settings())
    assert outcome.action == "promoted"


def test_bootstrap_admin_missing_env_raises_in_production(conn: sqlite3.Connection) -> None:
    with pytest.raises(BootstrapAdminMissingEnv):
        bootstrap_admin(conn, _settings("production"))
    assert _user(conn, 1)["is_admin"] == 0


def test_bootstrap_admin_missing_env_in_test_env_is_noop(conn: sqlite3.Connection) -> None:
    outcome = bootstrap_admin(conn, _settings("test"))
    assert (outcome.action, outcome.reason) == ("noop", "no_credentials")


def test_bootstrap_admin_is_idempotent(conn: sqlite3.Connection) -> None:
    first = bootstrap_admin(conn, _env_settings())
    hash_after_first = _user(conn, 1)["password_hash"]

    second = bootstrap_admin(conn, _env_settings())

    assert first.action == "promoted"
    assert second.action == "noop"
    assert _user(conn, 1)["password_hash"] == hash_after_first
    assert len(_user_audit(conn)) == 1


def test_bootstrap_admin_dev_default_adopts_pristine_legacy_row(
    conn: sqlite3.Connection,
) -> None:
    outcome = bootstrap_admin(conn, _settings("dev"))

    assert outcome.action == "promoted"
    row = _user(conn, 1)
    assert row["email"] == DEV_ADMIN_EMAIL
    assert row["must_change_password"] == 0
    assert _passwords.verify_password(DEV_ADMIN_PASSWORD, row["password_hash"])


def test_bootstrap_admin_dev_default_never_touches_legacy_data(
    conn: sqlite3.Connection,
) -> None:
    _add_account(conn, 1)
    before = [tuple(r) for r in conn.execute("SELECT * FROM users ORDER BY id")]

    with capture_logs() as logs:
        outcome = bootstrap_admin(conn, _settings("dev"))

    assert (outcome.action, outcome.reason) == ("noop", "legacy_data_present")
    assert [tuple(r) for r in conn.execute("SELECT * FROM users ORDER BY id")] == before
    assert conn.execute("SELECT count(*) FROM audit_log").fetchone()[0] == 0
    assert logs[-1]["log_level"] == "warning"


def test_bootstrap_admin_env_adopts_legacy_row_even_with_data(
    conn: sqlite3.Connection,
) -> None:
    _add_account(conn, 1)
    outcome = bootstrap_admin(conn, _env_settings("dev"))
    assert (outcome.action, outcome.user_id, outcome.legacy_adopted) == ("promoted", 1, True)


def test_bootstrap_admin_logs_structured_line_without_secrets(
    conn: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
) -> None:
    with capture_logs() as logs:
        bootstrap_admin(conn, _env_settings())

    entry = logs[-1]
    assert entry["event"] == "admin_bootstrap"
    assert entry["action"] == "promoted"
    assert entry["admin_email"] == ADMIN_EMAIL.lower()
    password_hash = _user(conn, 1)["password_hash"]
    blob = json.dumps(logs, default=str) + capsys.readouterr().out
    assert ADMIN_PASSWORD not in blob
    assert password_hash not in blob
    audit_blob = json.dumps([dict(r) for r in conn.execute("SELECT * FROM audit_log")])
    assert ADMIN_PASSWORD not in audit_blob
    assert password_hash not in audit_blob


def test_bootstrap_admin_rejects_unmigrated_schema(conn: sqlite3.Connection) -> None:
    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    raw.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    with pytest.raises(SchemaNotMigratedError):
        bootstrap_admin(raw, _env_settings("production"))
    outcome = bootstrap_admin(raw, _env_settings("dev"))
    assert (outcome.action, outcome.reason) == ("noop", "schema_not_migrated")
    raw.close()


# --- bootstrap_admin_at_startup ----------------------------------------------


def test_startup_skips_db_in_test_env_without_credentials() -> None:
    def _boom(_: Settings) -> sqlite3.Connection:
        raise AssertionError("must not connect")

    outcome = bootstrap_admin_at_startup(_settings("test"), connect=_boom)
    assert outcome.reason == "no_credentials"


def test_startup_opens_and_closes_connection(conn: sqlite3.Connection) -> None:
    closed: list[bool] = []

    class _Conn:
        def __getattr__(self, name: str) -> Any:
            return getattr(conn, name)

        def close(self) -> None:
            closed.append(True)

    outcome = bootstrap_admin_at_startup(
        _env_settings(),
        connect=lambda _: _Conn(),  # type: ignore[arg-type,return-value]
    )
    assert outcome.action == "promoted"
    assert closed == [True]


# --- set_user_password -------------------------------------------------------


def test_set_user_password_updates_hash_email_and_admin(conn: sqlite3.Connection) -> None:
    user = set_user_password(
        conn,
        1,
        change=PasswordChange(
            password="n3w-secret",  # noqa: S106  # pragma: allowlist secret
            must_change_password=False,
            set_email=" Me@Example.Test ",
            make_admin=True,
        ),
    )
    assert (user.email, user.is_admin, user.must_change_password) == (
        "me@example.test",
        True,
        False,
    )
    row = _user(conn, 1)
    assert _passwords.verify_password("n3w-secret", row["password_hash"])
    audit = _user_audit(conn)
    new_json = json.loads(audit[-1]["new_json"])
    assert new_json["password_changed"] is True
    assert new_json["password_set"] is True
    assert "password_hash" not in new_json
    assert json.loads(audit[-1]["prev_json"])["password_set"] is False


def test_set_user_password_keeps_email_and_admin_when_not_requested(
    conn: sqlite3.Connection,
) -> None:
    conn.execute("UPDATE users SET email = 'keep@example.test', is_admin = 1 WHERE id = 1")
    user = set_user_password(
        conn,
        1,
        change=PasswordChange(password="abc12345", must_change_password=True),  # noqa: S106
    )
    assert (user.email, user.is_admin, user.must_change_password) == (
        "keep@example.test",
        True,
        True,
    )


def test_set_user_password_unknown_user(conn: sqlite3.Connection) -> None:
    with pytest.raises(UserNotFoundError):
        set_user_password(
            conn, 999, change=PasswordChange(password=OTHER_PASSWORD, must_change_password=False)
        )


def test_set_user_password_rolls_back_on_email_collision(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO users(name, email) VALUES ('Other', 'taken@example.test')")
    with pytest.raises(sqlite3.IntegrityError):
        set_user_password(
            conn,
            1,
            change=PasswordChange(
                password=OTHER_PASSWORD,
                must_change_password=False,
                set_email="TAKEN@example.test",
            ),
        )
    assert _user(conn, 1)["password_hash"] is None
    assert _user_audit(conn) == []


def test_set_user_password_rejects_empty_password(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="empty"):
        set_user_password(conn, 1, change=PasswordChange(password="", must_change_password=False))


# --- repository helpers ------------------------------------------------------


def test_find_legacy_owner_none_when_all_users_have_email(conn: sqlite3.Connection) -> None:
    _retire_legacy_row(conn)
    assert users_repo.find_legacy_owner(conn) is None


def test_has_live_admin_flags(conn: sqlite3.Connection) -> None:
    assert users_repo.has_live_admin(conn) is False
    conn.execute("UPDATE users SET is_admin = 1 WHERE id = 1")
    assert users_repo.has_live_admin(conn) is True


def test_service_module_exports() -> None:
    assert "bootstrap_admin" in users_service.__all__
