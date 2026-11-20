"""H3: user-enumeration oracles on password login at production bcrypt cost (12).

Compares median latency and response bodies for: existing user + wrong password, unknown email,
passkey-only user (no password hash), soft-deleted user, over-long (>72 byte) password.

Run: uv run python docs/plans/quality-audit/repro/H3/h3_enumeration_timing.py
"""

from __future__ import annotations

import hashlib
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import PW, client, db_exec, make_app, new_db, prime, say  # noqa: E402

db = new_db("timing")
from budget_planner.services import _passwords  # noqa: E402

_passwords.DEFAULT_ROUNDS = 12
pw12 = _passwords.hash_password(PW, rounds=12)
db_exec(db, "UPDATE users SET password_hash=? WHERE id IN (1,2)", (pw12,))
db_exec(db, "UPDATE users SET password_hash=NULL WHERE id=3")  # passkey-only
db_exec(db, "INSERT INTO users(id,name,email,password_hash,is_admin,deleted_at) VALUES (9,'D','gone@x.test',?,0,'2026-01-01T00:00:00.000000Z')", (pw12,))
app, _ = make_app(db, rate_limit_enabled=False)
_passwords.DEFAULT_ROUNDS = 12  # make_app lowers it for tests; production value
c = client(app)
tok = prime(c)


def timed(email, password="wrong-password-xx"):  # pragma: allowlist secret
    t = time.perf_counter()
    r = c.post("/auth/login", data={"email": email, "password": password, "_csrf_token": tok})
    return time.perf_counter() - t, r.status_code, hashlib.sha256(r.content).hexdigest()[:8], len(r.content)


cases = {
    "existing, wrong pw": ("v@x.test", "wrong-password-xx"),
    "unknown email": ("nobody@x.test", "wrong-password-xx"),
    "passkey-only user": ("a@x.test", "wrong-password-xx"),
    "soft-deleted user": ("gone@x.test", "wrong-password-xx"),
    "existing, 100-byte pw": ("v@x.test", "x" * 100),
    "unknown, 100-byte pw": ("nobody@x.test", "x" * 100),
}
for name, (e, p) in cases.items():
    runs = [timed(e, p) for _ in range(8)]
    med = statistics.median(r[0] for r in runs) * 1000
    say(f"{name:24} median {med:7.1f} ms  status {runs[0][1]}  body-hash {runs[0][2]} len {runs[0][3]}")
