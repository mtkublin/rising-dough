"""Shared harness for the H3 repros. Scratch DBs under /tmp/audit-H3-*.sqlite only.

Users: 1 = admin (adm@x.test), 2 = victim V (v@x.test), 3 = attacker A (a@x.test).
Password for all: PW. App is built in-process with env=test (__Host- cookies, Secure,
TestClient base_url https://testserver). Never touches data/budget.sqlite.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import struct
import subprocess
import sys
from pathlib import Path

PW = "correct-horse-battery"
RP_ID = "testserver"
ORIGIN = "https://testserver"
SESSION = "__Host-session"
CSRF = "__Host-csrf"


def new_db(name: str) -> Path:
    db = Path(f"/tmp/audit-H3-{name}.sqlite")
    for suffix in ("", "-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    assert "budget.sqlite" not in str(db)
    os.environ["BUDGET_DATABASE_URL"] = f"sqlite:///{db}"
    subprocess.run(
        [sys.executable, "-m", "budget_planner.db.startup_migrate"], check=True, capture_output=True
    )
    from budget_planner.services import _passwords

    pw = _passwords.hash_password(PW, rounds=4)
    c = sqlite3.connect(db)
    c.execute("UPDATE users SET email='adm@x.test', password_hash=?, is_admin=1 WHERE id=1", (pw,))
    for uid, nm in ((2, "V"), (3, "A")):
        c.execute(
            "INSERT INTO users(id,name,email,password_hash,is_admin) VALUES (?,?,?,?,0)",
            (uid, nm, f"{nm.lower()}@x.test", pw),
        )
    c.commit()
    c.close()
    return db


def make_app(db: Path, **overrides):
    from budget_planner.config import Settings
    from budget_planner.services import _passwords
    from budget_planner.web.app import create_app

    _passwords.DEFAULT_ROUNDS = 4
    s = Settings(
        _env_file=None,
        database_url=f"sqlite:///{db}",
        env="test",
        webauthn_rp_id=RP_ID,
        webauthn_origin=ORIGIN,
        **overrides,
    )
    return create_app(s), s


def client(app):
    from fastapi.testclient import TestClient

    return TestClient(app, base_url=ORIGIN, raise_server_exceptions=False, follow_redirects=False)


def challenge_cookie_name(settings) -> str:
    from budget_planner.web.auth_cookies import challenge_cookie_name as f

    return f(settings)


def prime(cl) -> str:
    """GET login page so the CSRF cookie exists; return the token."""
    cl.get("/auth/login")
    return cl.cookies.get(CSRF)


def login(cl, email="v@x.test", password=PW, nxt="/"):
    tok = prime(cl)
    return cl.post(
        "/auth/login",
        data={"email": email, "password": password, "next": nxt, "_csrf_token": tok},
    )


def hdr(cl, **extra):
    return {"X-CSRF-Token": cl.cookies.get(CSRF), **extra}


def db_exec(db: Path, sql: str, args=()):
    c = sqlite3.connect(db)
    try:
        rows = c.execute(sql, args).fetchall()
        c.commit()
        return rows
    finally:
        c.close()


# --- software authenticator (ES256, "none" attestation) -------------------------------
def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class SoftKey:
    def __init__(self, cred_id: bytes | None = None):
        from cryptography.hazmat.primitives.asymmetric import ec

        self.priv = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = cred_id or os.urandom(32)
        self.counter = 0

    def _cose(self) -> bytes:
        import cbor2

        n = self.priv.public_key().public_numbers()
        return cbor2.dumps(
            {1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, "big"), -3: n.y.to_bytes(32, "big")}
        )

    def create(self, options: dict) -> dict:
        import cbor2

        rp = hashlib.sha256(options["rp"]["id"].encode()).digest()
        auth = rp + bytes([0x45]) + struct.pack(">I", self.counter) + bytes(16)
        auth += struct.pack(">H", len(self.cred_id)) + self.cred_id + self._cose()
        att = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth})
        cd = json.dumps(
            {"type": "webauthn.create", "challenge": options["challenge"], "origin": ORIGIN, "crossOrigin": False}
        ).encode()
        return {
            "id": b64u(self.cred_id),
            "rawId": b64u(self.cred_id),
            "type": "public-key",
            "response": {"clientDataJSON": b64u(cd), "attestationObject": b64u(att), "transports": ["internal"]},
            "clientExtensionResults": {},
        }

    def get(self, options: dict, *, bump: bool = True) -> dict:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec

        if bump:
            self.counter += 1
        rp = hashlib.sha256(options["rpId"].encode()).digest()
        auth = rp + bytes([0x05]) + struct.pack(">I", self.counter)
        cd = json.dumps(
            {"type": "webauthn.get", "challenge": options["challenge"], "origin": ORIGIN, "crossOrigin": False}
        ).encode()
        sig = self.priv.sign(auth + hashlib.sha256(cd).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "id": b64u(self.cred_id),
            "rawId": b64u(self.cred_id),
            "type": "public-key",
            "response": {"clientDataJSON": b64u(cd), "authenticatorData": b64u(auth), "signature": b64u(sig)},
            "clientExtensionResults": {},
        }


def fresh_reauth(cl, nxt="/"):
    """Password re-auth for the client's session; rotates the cookie (TestClient jar follows)."""
    return cl.post(
        "/auth/reauth", data={"password": PW, "next": nxt, "_csrf_token": cl.cookies.get(CSRF)}
    )


def register_key(cl, key: SoftKey, label="k"):
    r = cl.post("/auth/register/begin", headers=hdr(cl))
    assert r.status_code == 200, (r.status_code, r.text[:200])
    cred = key.create(r.json())
    return cl.post("/auth/register/finish", headers=hdr(cl), json={"label": label, "credential": cred})


def say(*a):
    print(*a, flush=True)
