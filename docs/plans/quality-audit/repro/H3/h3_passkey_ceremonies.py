"""H3: passkey ceremony edge cases with a software ES256 authenticator.

Goals: challenge replay (login), sign-count regression side effects, cross-user credential
registration / reauth, purpose and user binding of the challenge cookie, revoked credential,
sessions surviving passkey removal.

Run: uv run python docs/plans/quality-audit/repro/H3/h3_passkey_ceremonies.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import *  # noqa: E402,F403
from _common import SESSION, SoftKey, challenge_cookie_name, client, db_exec, hdr, login, make_app, new_db, prime, register_key, say, fresh_reauth  # noqa: E402

db = new_db("passkey")
# Limits raised: this script is about ceremony logic, not throttling (see h3_rate_limit.py).
BIG = {
    f"rate_limit_{k}": 500
    for k in (
        "reauth_per_minute", "reauth_per_hour", "register_per_minute", "register_per_hour",
        "login_per_minute", "login_per_hour", "login_ip_per_hour",
        "passkey_login_per_minute", "passkey_login_per_hour",
    )
}
app, settings = make_app(db, **BIG)
CC = challenge_cookie_name(settings)


def signed_in(email: str):
    cl = client(app)
    r = login(cl, email)
    assert r.status_code == 303, r.status_code
    assert fresh_reauth(cl).status_code == 303
    return cl


def passkey_login_begin(cl):
    r = cl.post("/auth/login/begin", headers=hdr(cl))
    return r.json(), cl.cookies.get(CC)


def n_sessions(uid):
    return db_exec(db, "SELECT count(*) FROM sessions WHERE user_id=? AND revoked_at IS NULL", (uid,))[0][0]


# ---- P1: replay of (challenge cookie, assertion) with a zero-counter (synced passkey) --------
say("== P1 replay of a captured passkey login with sign_count=0 authenticator")
v = signed_in("v@x.test")
k0 = SoftKey()
r = register_key(v, k0, "synced")
say("register ->", r.status_code, r.text[:80])
victim_browser = client(app)
prime(victim_browser)
opts, cookie = passkey_login_begin(victim_browser)
assertion = k0.get(opts, bump=False)  # counter stays 0, like iCloud/Google synced passkeys
before = n_sessions(2)
r1 = victim_browser.post("/auth/login/finish", headers=hdr(victim_browser), json=assertion)
say("victim login ->", r1.status_code, r1.text)
# attacker holding a copy of cookie + body (MITM / malware / proxy log) replays from elsewhere
atk = client(app)
tok = prime(atk)
atk.cookies.set(CC, cookie)
r2 = atk.post("/auth/login/finish", headers={"X-CSRF-Token": tok}, json=assertion)
say("REPLAY from another client ->", r2.status_code, r2.text, "| new session cookie:", SESSION in atk.cookies)
say("live sessions for V before/after:", before, n_sessions(2))
r3 = atk.get("/today")
say("replayed session usable: GET /today ->", r3.status_code)

# ---- P2: replay when the authenticator has a real counter: credential gets revoked ---------
say("\n== P2 replay with counter>0 authenticator revokes the victim's passkey (DoS on the credential)")
v2 = signed_in("v@x.test")
k1 = SoftKey()
register_key(v2, k1, "hw")
vb = client(app)
prime(vb)
opts, cookie = passkey_login_begin(vb)
assertion = k1.get(opts)  # counter -> 1
r1 = vb.post("/auth/login/finish", headers=hdr(vb), json=assertion)
say("legit login ->", r1.status_code)
atk = client(app)
tok = prime(atk)
atk.cookies.set(CC, cookie)
r2 = atk.post("/auth/login/finish", headers={"X-CSRF-Token": tok}, json=assertion)
say("replay ->", r2.status_code, r2.text)
say("credential deleted_at after replay:", db_exec(db, "SELECT label, deleted_at IS NOT NULL FROM webauthn_credentials WHERE label='hw'"))
vb2 = client(app)
prime(vb2)
opts, _ = passkey_login_begin(vb2)
r = vb2.post("/auth/login/finish", headers=hdr(vb2), json=k1.get(opts))
say("victim passkey login afterwards ->", r.status_code, r.text)

# ---- P3: cross-user credential id registration ------------------------------------------
say("\n== P3 attacker registers a credential with the victim's credential id")
a = signed_in("a@x.test")
dup = SoftKey(cred_id=k0.cred_id)  # same id as V's live credential, attacker's own key material
r = register_key(a, dup, "dup-live")
say("dup of live V credential ->", r.status_code, r.text)
dead = SoftKey(cred_id=k1.cred_id)  # id of V's revoked credential (from P2)
a = signed_in("a@x.test")
r = register_key(a, dead, "dup-revoked")
say("dup of REVOKED V credential ->", r.status_code, r.text)
say("rows with that id:", db_exec(db, "SELECT user_id, deleted_at IS NOT NULL FROM webauthn_credentials WHERE credential_id=?", (k1.cred_id,)))

# ---- P4: reauth with another user's credential ------------------------------------------
say("\n== P4 attacker session re-auths with the victim's credential")
a = signed_in("a@x.test")
ka = SoftKey()
register_key(a, ka, "a-key")
r = a.post("/auth/reauth/begin", headers=hdr(a))
opts = r.json()
say("allowCredentials has only A's id:", [c["id"] for c in opts["allowCredentials"]] == [b64u for b64u in [__import__("_common").b64u(ka.cred_id)]])
forged = k0.get(opts)  # V's still-live synced key signs A's challenge
r = a.post("/auth/reauth/finish", headers=hdr(a), json=forged)
say("reauth finish with V's credential ->", r.status_code, r.text)

# ---- P5: challenge purpose / user binding ------------------------------------------------
say("\n== P5 challenge cookie purpose and user binding")
vb = client(app)
prime(vb)
opts, login_cookie = passkey_login_begin(vb)
a = signed_in("a@x.test")
r = a.post("/auth/reauth/begin", headers=hdr(a))
reauth_opts = r.json()
a.cookies.delete(CC)  # drop the reauth-purpose cookie so only the login one is sent
a.cookies.set(CC, login_cookie)  # login-purpose cookie presented to reauth finish
r = a.post("/auth/reauth/finish", headers=hdr(a), json=ka.get(reauth_opts))
say("login-purpose cookie on reauth/finish ->", r.status_code, r.text)
# A's register-purpose challenge presented by V's session
v3 = signed_in("v@x.test")
a2 = signed_in("a@x.test")
ra = a2.post("/auth/register/begin", headers=hdr(a2))
a_cookie = a2.cookies.get(CC)
kv = SoftKey()
v3.cookies.set(CC, a_cookie)
cred = kv.create(ra.json())
r = v3.post("/auth/register/finish", headers=hdr(v3), json={"label": "x", "credential": cred})
say("A's register challenge used by V's session ->", r.status_code, r.text)

# ---- P6: usernameless login ignores userHandle (user-handle confusion) -------------------
say("\n== P6 login resolves the user from credential id only")
vk = SoftKey()
v4 = signed_in("v@x.test")
register_key(v4, vk, "v-uh")
vb = client(app)
prime(vb)
opts, _ = passkey_login_begin(vb)
cred = vk.get(opts)
cred["response"]["userHandle"] = __import__("_common").b64u(b"3")  # claim to be user 3 (attacker)
r = vb.post("/auth/login/finish", headers=hdr(vb), json=cred)
say("login with forged userHandle=3 ->", r.status_code, r.text)
me = db_exec(db, "SELECT user_id FROM sessions ORDER BY created_at DESC LIMIT 1")
say("session owner:", me, "(expected 2 = credential owner)")

# ---- P7: sessions created by a passkey survive revoking that passkey ---------------------
say("\n== P7 session issued by a passkey survives removal of the passkey")
kp = SoftKey()
v5 = signed_in("v@x.test")
register_key(v5, kp, "to-remove")
row = db_exec(db, "SELECT id FROM webauthn_credentials WHERE label='to-remove'")[0][0]
thief = client(app)
prime(thief)
opts, _ = passkey_login_begin(thief)
r = thief.post("/auth/login/finish", headers=hdr(thief), json=kp.get(opts))
say("passkey login ->", r.status_code)
fresh_reauth(v5)
r = v5.post(f"/auth/passkeys/{row}/revoke", headers=hdr(v5))
say("owner revokes passkey ->", r.status_code)
r = thief.get("/today")
say("session created via that passkey still works: GET /today ->", r.status_code)
