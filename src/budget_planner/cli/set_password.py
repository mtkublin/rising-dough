"""Operator CLI: set a user's password (ADR-0069 §4, T-D19).

Usage::

    python -m budget_planner.cli.set_password --db=<path> --email=<email>
    python -m budget_planner.cli.set_password --db=<path> --user-id=1 \\
        --set-email=me@example.com --make-admin

The password is read twice via ``getpass`` (or once from stdin with
``--password-stdin``), bcrypt-hashed, and stored with an ``audit_log`` row.
``--db`` is mandatory: there is deliberately no default database, so the
tool can never hit ``data/budget.sqlite`` by accident.

Exit codes: 0 success, 1 runtime failure (user not found, bad password,
email collision, unmigrated DB), 2 usage error (argparse).
"""

from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.repositories import auth_users as auth_users_repo
from budget_planner.repositories.users import UserNotFoundError
from budget_planner.services import users as users_service

PasswordPrompt = Callable[[str], str]


class CliError(Exception):
    """User-facing failure; message is printed to stderr."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="set_password",
        description="Set a user's password (operator tool, ADR-0069 §4).",
    )
    parser.add_argument("--db", required=True, type=Path, help="Path to the SQLite DB file.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--email", help="Target user by email (case-insensitive).")
    target.add_argument("--user-id", type=int, help="Target user by id.")
    parser.add_argument("--set-email", help="Also set the user's email.")
    parser.add_argument("--make-admin", action="store_true", help="Also set is_admin = 1.")
    parser.add_argument(
        "--must-change-password",
        action="store_true",
        help="Force a password change at next login.",
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read the password from the first line of stdin instead of prompting.",
    )
    return parser


def _read_password(*, from_stdin: bool, stdin: TextIO, prompt: PasswordPrompt) -> str:
    if from_stdin:
        password = stdin.readline().rstrip("\r\n")
    else:
        password = prompt("New password: ")
        if prompt("Repeat password: ") != password:
            raise CliError("passwords do not match")
    if not password:
        raise CliError("password must not be empty")
    return password


def _resolve_user_id(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    if args.user_id is not None:
        return int(args.user_id)
    user = auth_users_repo.find_live_by_email(conn, str(args.email))
    if user is None:
        raise CliError(f"no live user with email {args.email!r}")
    return user.id


def _validate_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalised = value.strip().lower()
    local, _, domain = normalised.partition("@")
    if not local or not domain:
        raise CliError(f"invalid email {value!r}")
    return normalised


def _run(
    args: argparse.Namespace, *, stdin: TextIO, stdout: TextIO, prompt: PasswordPrompt
) -> None:
    db_path: Path = args.db
    if not db_path.is_file():
        raise CliError(f"database file not found: {db_path}")
    set_email = _validate_email(args.set_email)
    settings = Settings(_env_file=None, env="test", database_url=f"sqlite:///{db_path.as_posix()}")
    conn = get_connection(settings)
    try:
        try:
            user_id = _resolve_user_id(conn, args)
        except sqlite3.OperationalError as exc:
            raise CliError(f"database is not migrated: {exc}") from exc
        password = _read_password(from_stdin=args.password_stdin, stdin=stdin, prompt=prompt)
        change = users_service.PasswordChange(
            password=password,
            must_change_password=args.must_change_password,
            set_email=set_email,
            make_admin=args.make_admin,
        )
        try:
            user = users_service.set_user_password(conn, user_id, change=change)
        except UserNotFoundError as exc:
            raise CliError(str(exc)) from exc
        except users_service.SchemaNotMigratedError as exc:
            raise CliError(str(exc)) from exc
        except sqlite3.IntegrityError as exc:
            raise CliError(f"email already in use by another live user: {exc}") from exc
        except ValueError as exc:
            raise CliError(str(exc)) from exc
    finally:
        conn.close()
    stdout.write(
        f"password updated for user id={user.id} email={user.email} "
        f"is_admin={int(user.is_admin)} must_change_password={int(user.must_change_password)}\n"
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    prompt: PasswordPrompt = getpass.getpass,
) -> int:
    args = _build_parser().parse_args(argv)
    err = stderr or sys.stderr
    try:
        _run(args, stdin=stdin or sys.stdin, stdout=stdout or sys.stdout, prompt=prompt)
    except CliError as exc:
        err.write(f"set_password: error: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised via main() in tests
    raise SystemExit(main())
