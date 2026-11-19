"""H3: CSRF double-submit edge cases, login CSRF, token lifecycle, pre-auth parser fuzz,
stale-admin step-up on /settings/users, open-redirect battery on every `next` consumer.

Run: uv run python docs/plans/quality-audit/repro/H3/h3_csrf_preauth.py
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import CSRF, PW, SESSION, challenge_cookie_name, client, db_exec, hdr, login, make_app, new_db, prime, say  # noqa: E402

db = new_db("csrf")
BIG = {f"rate_limit_{k}": 5000 for k in ("login_per_minute", "login_per_hour", "login_ip_per_hour", "passkey_login_per_minute", "passkey_login_per_hour", "reauth_per_minute", "reauth_per_hour")}
app, settings = make_app(db, **BIG)
CC = challenge_cookie_name(settings)
NOW = {"t": None}
app.state.reauth_clock = lambda: NOW["t"] or datetime.now(UTC)


def ck(cl, name):
    vals = [c.value for c in cl.cookies.jar if c.name == name]
    return vals[-1] if vals else None


say("== C1 login CSRF")
c = client(app)
r = c.post("/auth/login", data={"email": "v@x.test", "password": PW})
say("no cookie, no token ->", r.status_code, r.text)
prime(c)
r = c.post("/auth/login", data={"email": "v@x.test", "password": PW})
say("cookie, no token ->", r.status_code, r.text)
r = c.post("/auth/login", data={"email": "v@x.test", "password": PW, "_csrf_token": "x"})
say("cookie, wrong token ->", r.status_code, r.text)
# attacker-controlled cookie value (needs cookie injection; __Host- blocks it in browsers)
c2 = client(app)
c2.cookies.set(CSRF, "a", domain="testserver.local")
r = c2.post("/auth/login", data={"email": "a@x.test", "password": PW, "_csrf_token": "a"})
say("attacker-chosen 1-char cookie 'a' + same form token ->", r.status_code, "(303 = accepted: no format/signature check on the token)")

say("\n== C2 CSRF token lifecycle across login / logout")
c = client(app)
t0 = prime(c)
login(c)
t1 = ck(c, CSRF)
c.post("/auth/logout", headers=hdr(c))
t2 = ck(c, CSRF)
say("token before login == after login == after logout:", t0 == t1 == t2)

say("\n== C3 header vs form precedence")
c = client(app); login(c); tok = ck(c, CSRF)
r = c.post("/auth/logout", headers={"X-CSRF-Token": ""}, data={"_csrf_token": tok})
say("empty header + valid form token ->", r.status_code)
c = client(app); login(c); tok = ck(c, CSRF)
r = c.post("/auth/logout", headers={"X-CSRF-Token": "wrong"}, data={"_csrf_token": tok})
say("wrong header + valid form token ->", r.status_code)
c = client(app); login(c); tok = ck(c, CSRF)
r = c.post("/auth/logout", content=b"x", headers={"Content-Type": "text/plain", "X-CSRF-Token": tok})
say("text/plain + header ->", r.status_code, "(header alone suffices; cross-site fetch cannot set it without CORS preflight)")
c = client(app); login(c)
r = c.post("/auth/logout", content=b"x", headers={"Content-Type": "text/plain"})
say("text/plain, no token (classic cross-site form) ->", r.status_code)
for m in ("PUT", "PATCH", "DELETE"):
    c = client(app); login(c)
    r = c.request(m, "/auth/logout")
    say(f"{m} without token ->", r.status_code)

say("\n== C4 pre-auth parser fuzz on POST /auth/login (all expected 4xx; 5xx = finding)")
c = client(app); tok = prime(c)
cases = {
    "non-ascii form token": dict(data={"email": "a", "password": "b", "_csrf_token": "café"}),
    "non-ascii header token (latin-1)": dict(headers={"X-CSRF-Token": "café".encode("latin-1")}, data={"email": "a"}),
    "non-ascii cookie vs ascii token": None,
    "multipart no boundary": dict(content=b"x", headers={"Content-Type": "multipart/form-data"}),
    "multipart bad boundary body": dict(content=b"--b\r\nContent-Disposition: form-data; name=\xff\r\n\r\nx\r\n--b--", headers={"Content-Type": "multipart/form-data; boundary=b", "X-CSRF-Token": tok}),
    "urlencoded invalid utf-8 %ff": dict(content=b"email=%ff%fe&password=x&_csrf_token=" + tok.encode(), headers={"Content-Type": "application/x-www-form-urlencoded"}),
    "urlencoded 1500 fields": dict(content="&".join(f"f{i}=1" for i in range(1500)).encode() + b"&_csrf_token=" + tok.encode(), headers={"Content-Type": "application/x-www-form-urlencoded"}),
    "NUL in email": dict(data={"email": "a\x00b@x.test", "password": "p", "_csrf_token": tok}),
    "next with NUL": dict(data={"email": "a@x.test", "password": "p", "next": "/a\x00b", "_csrf_token": tok}),
    "duplicate _csrf_token": dict(content=b"_csrf_token=bad&_csrf_token=" + tok.encode() + b"&email=a&password=b", headers={"Content-Type": "application/x-www-form-urlencoded"}),
    "JSON body to form route": dict(json={"email": "a"}, headers={"X-CSRF-Token": tok}),
    "bad content-length": None,
}
for name, kw in cases.items():
    if kw is None:
        continue
    r = c.post("/auth/login", **kw)
    say(f"  {name:36} -> {r.status_code}")
r = c.post("/auth/login", content=b"", headers={"Content-Type": "application/x-www-form-urlencoded", "X-CSRF-Token": tok, "Cookie": f"{CSRF}={tok}; {SESSION}=".encode() + b"\xe9\xe9"})
say(f"  {'non-ascii session cookie bytes':36} -> {r.status_code}")

say("\n== C5 malformed passkey login bodies with a VALID challenge cookie")
bodies = {
    "{} ": {},
    "id int": {"id": 1, "rawId": 1, "type": "public-key", "response": {}},
    "rawId not base64": {"id": "!!", "rawId": "!!", "type": "public-key", "response": {"clientDataJSON": "e30", "authenticatorData": "AAAA", "signature": "AQ"}},
    "response is string": {"id": "AAAA", "rawId": "AAAA", "type": "public-key", "response": "x"},
    "null response": {"id": "AAAA", "rawId": "AAAA", "type": "public-key", "response": None},
    "huge nested": {"id": "AAAA", "rawId": "AAAA", "type": "public-key", "response": {"clientDataJSON": "e30" * 1000, "authenticatorData": "AAAA", "signature": "AQ"}},
    "list": [],
}
for name, body in bodies.items():
    cl = client(app); prime(cl)
    cl.post("/auth/login/begin", headers=hdr(cl))
    r = cl.post("/auth/login/finish", headers=hdr(cl), json=body)
    say(f"  {name:20} -> {r.status_code} {r.text[:60]}")
cl = client(app); prime(cl); cl.post("/auth/login/begin", headers=hdr(cl))
r = cl.post("/auth/login/finish", headers=hdr(cl) | {"Content-Type": "application/json"}, content=b"\xff\xfe")
say(f"  {'non-utf8 body':20} -> {r.status_code}")

say("\n== C6 unbounded attacker email in audit_log (one request)")
c = client(app); tok = prime(c)
big = "A" * 200_000 + "@x.test"
before = db_exec(db, "SELECT count(*) , coalesce(sum(length(payload)),0) FROM audit_log")[0] if False else None
cols = [r[1] for r in db_exec(db, "PRAGMA table_info(audit_log)")]
pcol = "new_value" if "new_value" in cols else next((x for x in cols if "new" in x), cols[-1])
r = c.post("/auth/login", data={"email": big, "password": "x", "_csrf_token": tok})
say("200KB email login ->", r.status_code, "| max stored audit payload bytes:", db_exec(db, f"SELECT max(length({pcol})) FROM audit_log")[0][0])

say("\n== C7 stale admin and /settings/users (step-up on admin POSTs, HTMX and plain)")
adm = client(app); login(adm, "adm@x.test")
NOW["t"] = datetime.now(UTC) + timedelta(minutes=11)
for h in ({}, {"HX-Request": "true"}):
    r = adm.post("/settings/users/2/reset-password", headers=hdr(adm, **h))
    say(f"  stale admin reset-password {h or 'plain'} ->", r.status_code, r.headers.get("hx-redirect") or r.headers.get("location"))
r = adm.post("/settings/users/2/delete", headers=hdr(adm))
say("  stale admin delete ->", r.status_code)
NOW["t"] = None

say("\n== C8 open-redirect battery (Location / JSON redirect values)")
evil = ["//evil.example", "/\\evil.example", "/%2f/evil.example", "/%5cevil.example", "https://evil.example", "/\t/evil.example", "/ /evil.example", "///evil.example", "/.//evil.example", "/a?next=//evil.example", "javascript:alert(1)", "/auth/login/../x", "/auth/loginx", "/AUTH/login", "∕evil.example", "/∕evil.example", "/%0d%0aSet-Cookie:x=1"]
for e in evil:
    c = client(app)
    r = login(c, "v@x.test", PW, nxt=e)
    loc = r.headers.get("location")
    r2 = c.post("/auth/reauth", data={"password": PW, "next": e, "_csrf_token": ck(c, CSRF)})
    say(f"  next={e!r:30} login -> {loc!r:26} reauth -> {r2.headers.get('location')!r}")
for e in ("//evil.example/x", "/\\evil.example", "https://evil.example/"):
    c = client(app); login(c)
    r = c.get(f"/auth/login?next={e}")
    r2 = c.get("/auth/reauth", params={"next": e})
    import re
    m = re.search(r'name="next" value="([^"]*)"', r2.text)
    say(f"  GET /auth/login?next={e!r} signed-in ->", r.headers.get("location"), "| reauth form next field:", m.group(1) if m else None)
c = client(app); prime(c)
for hu in ("//evil.example/x", "https://evil.example/x", "/\\evil.example"):
    r = c.post("/transactions", headers=hdr(c, **{"HX-Request": "true", "HX-Current-URL": hu}))
    say(f"  anon HX-Current-URL={hu!r} -> HX-Redirect", r.headers.get("hx-redirect"))
r = c.get("//evil.example/x", follow_redirects=False)
say("  GET //evil.example/x anonymous ->", r.status_code, r.headers.get("location"))

say("\n== C9 reflected values on the login page (autoescape check)")
c = client(app)
xss = "/a\"><img src=x onerror=alert(1)><script>1</script>"
r = c.get("/auth/login", params={"next": xss})
say("GET next reflected raw:", "<img src=x" in r.text or "<script>1</script>" in r.text)
tok = prime(c)
r = c.post("/auth/login", data={"email": "\"><svg onload=alert(1)>", "password": "x", "next": xss, "_csrf_token": tok})
say("failed-login echo of email/next raw:", "<svg onload" in r.text or "<img src=x" in r.text)
