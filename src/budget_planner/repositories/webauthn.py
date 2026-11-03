"""Passkey (WebAuthn) credential store (ADR-0033 §1, ADR-0067).

Credentials are scoped by ``user_id`` and soft-deleted (``deleted_at``)
rather than removed. ``create_credential`` and ``revoke_credential`` write
an audit row in the same transaction. The payload is a sanitized view
(base64url credential id, no public key), so key material never reaches
``audit_log``. ``update_sign_count`` runs on every passkey login and is
covered by the login audit row the service writes (ADR-0067 §4).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from webauthn.helpers import bytes_to_base64url

from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories._shared import (
    parse_dt,
    parse_dt_required,
    transaction,
    utc_now_iso,
    write_audit,
)

ENTITY_TYPE = "webauthn_credential"
_COLUMNS = (
    "id, user_id, credential_id, public_key, sign_count, transports, label, "
    "created_at, last_used_at, deleted_at"
)
_EMPTY_CTX = RequestCtx.empty()


@dataclass(frozen=True, slots=True, kw_only=True)
class WebAuthnCredential:
    """One registered passkey."""

    id: int
    user_id: int
    credential_id: bytes
    public_key: bytes
    sign_count: int
    transports: tuple[str, ...]
    label: str
    created_at: datetime
    last_used_at: datetime | None
    deleted_at: datetime | None


def audit_view(cred: WebAuthnCredential) -> dict[str, Any]:
    """Return the audit-safe projection of ``cred`` (no public key)."""
    return {
        "id": cred.id,
        "user_id": cred.user_id,
        "credential_id": bytes_to_base64url(cred.credential_id),
        "label": cred.label,
        "transports": list(cred.transports),
        "sign_count": cred.sign_count,
    }


def _split_transports(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(t for t in raw.split(",") if t)


def _hydrate(row: sqlite3.Row) -> WebAuthnCredential:
    return WebAuthnCredential(
        id=row["id"],
        user_id=row["user_id"],
        credential_id=bytes(row["credential_id"]),
        public_key=bytes(row["public_key"]),
        sign_count=row["sign_count"],
        transports=_split_transports(row["transports"]),
        label=row["label"],
        created_at=parse_dt_required(row["created_at"]),
        last_used_at=parse_dt(row["last_used_at"]),
        deleted_at=parse_dt(row["deleted_at"]),
    )


def _get_by_id(conn: sqlite3.Connection, row_id: int) -> WebAuthnCredential | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM webauthn_credentials WHERE id = ?", (row_id,)
    ).fetchone()
    return None if row is None else _hydrate(row)


def list_credentials(
    conn: sqlite3.Connection, user_id: int, *, include_deleted: bool = False
) -> tuple[WebAuthnCredential, ...]:
    """Return ``user_id``'s credentials, oldest first."""
    live = "" if include_deleted else " AND deleted_at IS NULL"
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM webauthn_credentials WHERE user_id = ?{live} ORDER BY id",
        (user_id,),
    ).fetchall()
    return tuple(_hydrate(r) for r in rows)


def get_by_credential_id(
    conn: sqlite3.Connection, credential_id: bytes
) -> WebAuthnCredential | None:
    """Return the live credential whose raw id is ``credential_id``."""
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM webauthn_credentials "
        "WHERE credential_id = ? AND deleted_at IS NULL",
        (credential_id,),
    ).fetchone()
    return None if row is None else _hydrate(row)


def create_credential(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    credential_id: bytes,
    public_key: bytes,
    sign_count: int,
    transports: tuple[str, ...] = (),
    label: str = "",
    request_ctx: RequestCtx = _EMPTY_CTX,
) -> WebAuthnCredential:
    """Insert a credential and its ``create`` audit row atomically.

    Raises ``sqlite3.IntegrityError`` when ``credential_id`` already exists.
    """
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO webauthn_credentials "
            "(user_id, credential_id, public_key, sign_count, transports, label) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, credential_id, public_key, sign_count, ",".join(transports), label),
        )
        created = _get_by_id(conn, cur.lastrowid or 0)
        if created is None:  # pragma: no cover — row was inserted in this tx
            raise RuntimeError("webauthn credential vanished after insert")
        write_audit(
            conn,
            entity_type=ENTITY_TYPE,
            entity_id=created.id,
            operation="create",
            prev=None,
            new=audit_view(created),
            request_ctx=request_ctx,
        )
    return created


def update_sign_count(
    conn: sqlite3.Connection,
    credential_row_id: int,
    sign_count: int,
    *,
    now: datetime | None = None,
) -> None:
    """Persist the authenticator's latest ``sign_count`` and ``last_used_at``."""
    used_at = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    with transaction(conn):
        conn.execute(
            "UPDATE webauthn_credentials SET sign_count = ?, last_used_at = ? "
            "WHERE id = ? AND deleted_at IS NULL",
            (sign_count, used_at, credential_row_id),
        )


def revoke_credential(
    conn: sqlite3.Connection,
    credential_row_id: int,
    *,
    user_id: int | None = None,
    reason: str = "user_request",
    request_ctx: RequestCtx = _EMPTY_CTX,
) -> bool:
    """Soft-delete a live credential and audit it.

    When ``user_id`` is given the credential must belong to that user (so a
    route can safely pass a user-supplied id). Returns ``True`` iff a live
    credential was revoked.
    """
    with transaction(conn):
        current = _get_by_id(conn, credential_row_id)
        if current is None or current.deleted_at is not None:
            return False
        if user_id is not None and current.user_id != user_id:
            return False
        conn.execute(
            "UPDATE webauthn_credentials SET deleted_at = ? WHERE id = ?",
            (utc_now_iso(), credential_row_id),
        )
        write_audit(
            conn,
            entity_type=ENTITY_TYPE,
            entity_id=credential_row_id,
            operation="delete",
            prev={**audit_view(current), "reason": reason},
            new=None,
            request_ctx=request_ctx,
        )
    return True


__all__ = [
    "ENTITY_TYPE",
    "WebAuthnCredential",
    "audit_view",
    "create_credential",
    "get_by_credential_id",
    "list_credentials",
    "revoke_credential",
    "update_sign_count",
]
