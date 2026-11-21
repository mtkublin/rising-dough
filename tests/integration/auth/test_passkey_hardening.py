"""T-Q253 (Q-062): single-use challenges, passkey revoke ends its sessions, counter rules."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from webauthn.helpers import bytes_to_base64url

from budget_planner.repositories import sessions as sessions_repo, webauthn as webauthn_repo
from budget_planner.services import auth
from tests.integration.auth.conftest import PASSWORD

pytestmark = pytest.mark.integration

RP = auth.RelyingParty(rp_id="localhost", rp_name="Test", origin="http://localhost:8000")
RAW_ID = b"\x10\x20\x30\x40"
OTHER_ID = b"\x50\x60"
BOB_ID = b"\x70"
AuditRows = Callable[[str], list[sqlite3.Row]]


def _assertion(raw_id: bytes) -> str:
    rid = bytes_to_base64url(raw_id)
    return json.dumps(
        {
            "id": rid,
            "rawId": rid,
            "type": "public-key",
            "response": {"clientDataJSON": "e30", "authenticatorData": "AAAA", "signature": "AQ"},
        }
    )


def _finish(
    conn: sqlite3.Connection, *, challenge: bytes = b"chal", raw_id: bytes = RAW_ID
) -> sessions_repo.IssuedSession | None:
    return auth.authenticate_passkey_finish(
        conn, _assertion(raw_id), challenge=challenge, rp=RP, ip="203.0.113.1", user_agent="ua"
    )


def _verified(count: int) -> Callable[..., SimpleNamespace]:
    return lambda **_: SimpleNamespace(new_sign_count=count)


def _credential(conn: sqlite3.Connection, user_id: int, raw_id: bytes, count: int) -> int:
    return webauthn_repo.create_credential(
        conn, user_id=user_id, credential_id=raw_id, public_key=b"pk", sign_count=count
    ).id


def test_challenge_is_consumed_on_first_use(conn: sqlite3.Connection) -> None:
    assert webauthn_repo.consume_challenge(conn, b"abc") is True
    assert webauthn_repo.consume_challenge(conn, b"abc") is False
    assert webauthn_repo.consume_challenge(conn, b"other") is True


def test_replayed_login_with_counter_zero_opens_no_second_session(
    conn: sqlite3.Connection,
    make_user: Callable[..., int],
    audit_rows: AuditRows,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid = make_user()
    _credential(conn, uid, RAW_ID, 0)
    monkeypatch.setattr(auth, "verify_authentication_response", _verified(0))

    first = _finish(conn)
    replay = _finish(conn)

    assert first is not None
    assert replay is None
    assert len(sessions_repo.list_active_sessions(conn, uid)) == 1
    last = json.loads(audit_rows(auth.AUTH_EVENT_ENTITY)[-1]["new_json"])
    assert last["reason"] == "challenge_replayed"
    assert webauthn_repo.get_by_credential_id(conn, RAW_ID) is not None


def test_replay_with_counter_does_not_revoke_the_passkey(
    conn: sqlite3.Connection, make_user: Callable[..., int], monkeypatch: pytest.MonkeyPatch
) -> None:
    uid = make_user()
    _credential(conn, uid, RAW_ID, 5)
    monkeypatch.setattr(auth, "verify_authentication_response", _verified(6))

    assert _finish(conn) is not None
    assert _finish(conn) is None

    stored = webauthn_repo.get_by_credential_id(conn, RAW_ID)
    assert stored is not None
    assert stored.sign_count == 6


def test_zero_counter_accepted_and_non_increasing_rejected(
    conn: sqlite3.Connection, make_user: Callable[..., int], monkeypatch: pytest.MonkeyPatch
) -> None:
    uid = make_user()
    _credential(conn, uid, RAW_ID, 0)
    monkeypatch.setattr(auth, "verify_authentication_response", _verified(0))
    assert _finish(conn, challenge=b"c1") is not None

    monkeypatch.setattr(auth, "verify_authentication_response", _verified(7))
    assert _finish(conn, challenge=b"c2") is not None
    assert _finish(conn, challenge=b"c3") is None
    assert webauthn_repo.get_by_credential_id(conn, RAW_ID) is None  # revoked


def test_passkey_login_records_credential_on_session(
    conn: sqlite3.Connection, make_user: Callable[..., int], monkeypatch: pytest.MonkeyPatch
) -> None:
    uid = make_user()
    cred = _credential(conn, uid, RAW_ID, 1)
    monkeypatch.setattr(auth, "verify_authentication_response", _verified(2))

    issued = _finish(conn)

    assert issued is not None
    row = conn.execute(
        "SELECT credential_id FROM sessions WHERE id = ?", (issued.session.id,)
    ).fetchone()
    assert row["credential_id"] == cred


def test_revoking_a_passkey_ends_only_its_sessions(
    conn: sqlite3.Connection,
    make_user: Callable[..., int],
    audit_rows: AuditRows,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alice = make_user()
    bob = make_user(email="bob@example.test", name="Bob")
    alice_cred = _credential(conn, alice, RAW_ID, 1)
    _credential(conn, alice, OTHER_ID, 1)
    _credential(conn, bob, BOB_ID, 1)
    monkeypatch.setattr(auth, "verify_authentication_response", _verified(2))
    via_revoked = _finish(conn, challenge=b"a1")
    via_other = _finish(conn, challenge=b"a2", raw_id=OTHER_ID)
    by_password = auth.authenticate_password(
        conn, "alice@example.test", PASSWORD, ip=None, user_agent=None
    )
    bob_session = _finish(conn, challenge=b"b1", raw_id=BOB_ID)
    assert via_revoked and via_other and by_password and bob_session

    assert auth.revoke_passkey(conn, alice, alice_cred) is True

    assert sessions_repo.get_session(conn, via_revoked.token) is None
    assert sessions_repo.get_session(conn, via_other.token) is not None
    assert sessions_repo.get_session(conn, by_password.token) is not None
    assert sessions_repo.get_session(conn, bob_session.token) is not None
    ended = [
        json.loads(r["prev_json"])
        for r in audit_rows(auth.SESSION_ENTITY)
        if r["operation"] == "delete"
    ]
    assert ended[-1]["reason"] == "passkey_revoked"
    assert ended[-1]["sessions"] == [via_revoked.session.handle]


def test_revoking_someone_elses_passkey_ends_nothing(
    conn: sqlite3.Connection, make_user: Callable[..., int], monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = make_user()
    bob = make_user(email="bob@example.test", name="Bob")
    cred = _credential(conn, alice, RAW_ID, 1)
    monkeypatch.setattr(auth, "verify_authentication_response", _verified(2))
    issued = _finish(conn)
    assert issued is not None

    assert auth.revoke_passkey(conn, bob, cred) is False

    assert sessions_repo.get_session(conn, issued.token) is not None


def test_register_finish_replayed_challenge_is_rejected(
    conn: sqlite3.Connection, make_user: Callable[..., int], monkeypatch: pytest.MonkeyPatch
) -> None:
    uid = make_user()
    webauthn_repo.consume_challenge(conn, b"reg")
    parsed: list[Any] = []
    monkeypatch.setattr(
        auth, "parse_registration_credential_json", lambda *a, **_k: parsed.append(a)
    )

    with pytest.raises(auth.PasskeyRegistrationError) as err:
        auth.register_passkey_finish(conn, uid, {}, challenge=b"reg", rp=RP, label="x")

    assert err.value.reason == "challenge_expired"
    assert parsed == []
