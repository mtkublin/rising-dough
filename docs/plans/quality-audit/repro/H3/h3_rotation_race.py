"""H3: an in-flight request re-sets the OLD session token after re-auth rotated it.

AuthRequiredMiddleware re-issues the cookie it resolved at request start when the response does not
set one itself. If a slow request (any route) started before /auth/reauth rotated the token, its
response arrives later and carries `Set-Cookie: __Host-session=<old token>`, so the browser ends up
holding a dead token and the next request is redirected to the login page (ADR-0076 §4 assumes no
concurrent requests). The slow route is added by this script to widen the window; the race itself
is in src/budget_planner/web/middleware/auth.py (dispatch, last lines).

Run: uv run python docs/plans/quality-audit/repro/H3/h3_rotation_race.py
"""

from __future__ import annotations

import re
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn

sys.path.insert(0, str(Path(__file__).parent))
from _common import PW, make_app, new_db, say  # noqa: E402

db = new_db("race")
app, _ = make_app(db)


@app.get("/today-slow")
async def slow():
    import asyncio

    await asyncio.sleep(1.0)
    return {"ok": True}


with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    PORT = s.getsockname()[1]
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()
while not server.started:
    time.sleep(0.05)
B = f"http://127.0.0.1:{PORT}"


def setcookie(r, name):
    m = re.search(rf"{name}=([^;]+)", r.headers.get("set-cookie", ""))
    return m.group(1) if m else None


with httpx.Client(base_url=B) as c:
    g = c.get("/auth/login")
    csrf = setcookie(g, "__Host-csrf")
    r = c.post("/auth/login", data={"email": "v@x.test", "password": PW, "_csrf_token": csrf},
               headers={"Cookie": f"__Host-csrf={csrf}"})
    t1 = setcookie(r, "__Host-session")
    say("login ok:", r.status_code)
    out = {}

    def slow_call():
        out["slow"] = httpx.get(B + "/today-slow", headers={"Cookie": f"__Host-session={t1}; __Host-csrf={csrf}"})

    th = threading.Thread(target=slow_call)
    th.start()
    time.sleep(0.3)
    r = httpx.post(B + "/auth/reauth", data={"password": PW, "next": "/", "_csrf_token": csrf},
                   headers={"Cookie": f"__Host-session={t1}; __Host-csrf={csrf}"})
    t2 = setcookie(r, "__Host-session")
    say("reauth ->", r.status_code, "| rotated token differs:", t1 != t2)
    th.join()
    late = setcookie(out["slow"], "__Host-session")
    say("slow in-flight response (arrives AFTER the rotation) sets session cookie to the OLD token:", late == t1)
    # Browser applies Set-Cookie in arrival order: t2 then t1 -> final cookie = t1
    final = late or t2
    chk = httpx.get(B + "/auth/reauth", headers={"Cookie": f"__Host-session={final}"})
    say("next navigation with the cookie the browser now holds ->", chk.status_code, chk.headers.get("location"), "(302 to login = signed out)")
server.should_exit = True
