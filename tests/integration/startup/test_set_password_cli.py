"""T-D19 — operator CLI ``budget_planner.cli.set_password`` (ADR-0069 §4)."""

from __future__ import annotations

import io
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from budget_planner.cli import set_password as cli
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.services import _passwords

NEW_PASSWORD = "Op3rator-chosen!"  # noqa: S105  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_passwords, "DEFAULT_ROUNDS", 4)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "cli.sqlite"
    conn = get_connection(Settings(_env_file=None, database_url=f"sqlite:///{path.as_posix()}"))
    try:
        apply_migrations(conn)
        conn.execute("INSERT INTO users(name, email) VALUES ('Bob', 'bob@example.test')")
    finally:
        conn.close()
    return path


@pytest.fixture
def read_conn(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _run(
    argv: list[str], *, prompts: list[str] | None = None, stdin: str = ""
) -> tuple[int, str, str]:
    answers = iter(prompts or [])
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(
        argv,
        stdin=io.StringIO(stdin),
        stdout=out,
        stderr=err,
        prompt=lambda _msg: next(answers),
    )
    return code, out.getvalue(), err.getvalue()


def _user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row: sqlite3.Row | None = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    assert row is not None
    return row


def test_sets_password_for_legacy_user_and_promotes(
    db_path: Path, read_conn: sqlite3.Connection
) -> None:
    code, out, err = _run(
        [f"--db={db_path}", "--user-id=1", "--set-email=Me@Example.Test", "--make-admin"],
        prompts=[NEW_PASSWORD, NEW_PASSWORD],
    )

    assert (code, err) == (0, "")
    assert "id=1" in out
    assert NEW_PASSWORD not in out
    row = _user(read_conn, 1)
    assert (row["email"], row["is_admin"], row["must_change_password"]) == (
        "me@example.test",
        1,
        0,
    )
    assert _passwords.verify_password(NEW_PASSWORD, row["password_hash"])
    audit = read_conn.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'users' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert audit["operation"] == "update"
    assert audit["actor_user_id"] is None
    assert NEW_PASSWORD not in audit["new_json"]
    assert row["password_hash"] not in audit["new_json"]
    assert json.loads(audit["new_json"])["password_changed"] is True


def test_targets_by_email_reads_stdin_and_forces_rotation(
    db_path: Path, read_conn: sqlite3.Connection
) -> None:
    code, _, err = _run(
        [
            f"--db={db_path}",
            "--email=BOB@example.test",
            "--password-stdin",
            "--must-change-password",
        ],
        stdin=NEW_PASSWORD + "\n",
    )

    assert (code, err) == (0, "")
    row = _user(read_conn, 2)
    assert row["must_change_password"] == 1
    assert row["is_admin"] == 0
    assert _passwords.verify_password(NEW_PASSWORD, row["password_hash"])


@pytest.mark.parametrize(
    ("argv_tail", "prompts", "stdin", "message"),
    [
        (["--email=nobody@example.test"], [], "", "no live user"),
        (["--user-id=999"], ["pw", "pw"], "", "no live user"),
        (["--user-id=1"], ["one", "two"], "", "do not match"),
        (["--user-id=1", "--password-stdin"], [], "\n", "must not be empty"),
        (["--user-id=1", "--password-stdin"], [], "x" * 80 + "\n", "72 bytes"),
        (["--user-id=1", "--set-email=bob@example.test"], ["pw", "pw"], "", "already in use"),
        (["--user-id=1", "--set-email=broken"], [], "", "invalid email"),
    ],
)
def test_failures_exit_one_with_message(  # noqa: PLR0917 — pytest parametrize args
    db_path: Path,
    read_conn: sqlite3.Connection,
    argv_tail: list[str],
    prompts: list[str],
    stdin: str,
    message: str,
) -> None:
    code, out, err = _run([f"--db={db_path}", *argv_tail], prompts=prompts, stdin=stdin)

    assert code == 1
    assert out == ""
    assert message in err
    assert _user(read_conn, 1)["password_hash"] is None


def test_missing_db_file_is_an_error(tmp_path: Path) -> None:
    missing = tmp_path / "nope.sqlite"
    code, _, err = _run([f"--db={missing}", "--user-id=1"])
    assert code == 1
    assert "not found" in err
    assert not missing.exists()


def test_unmigrated_db_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO users(id, name) VALUES (1, 'default')")
    conn.commit()
    conn.close()

    code_email, _, err_email = _run([f"--db={path}", "--email=a@b.c"])
    code_id, _, err_id = _run([f"--db={path}", "--user-id=1"], prompts=["pw", "pw"])

    assert (code_email, code_id) == (1, 1)
    assert "not migrated" in err_email
    assert "migrations" in err_id


def test_db_flag_is_required() -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--user-id=1"], stderr=io.StringIO())
    assert excinfo.value.code == 2


def test_target_is_required(db_path: Path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main([f"--db={db_path}"], stderr=io.StringIO())
    assert excinfo.value.code == 2
