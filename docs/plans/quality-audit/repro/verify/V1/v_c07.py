"""C-07: SQL statement count + wall time per page on the demo dataset (scratch copy)."""

import time

from _web import fresh_conn, make_client

import budget_planner.web.deps as deps

fresh_conn().close()
counter = {"n": 0}
orig = deps.get_connection


def counting(settings):  # noqa: ANN001, ANN201
    c = orig(settings)
    c.set_trace_callback(lambda _s: counter.__setitem__("n", counter["n"] + 1))
    return c


deps.get_connection = counting
c, _ = make_client()
for route in ("/accounts", "/today", "/forecast", "/budget", "/plan", "/ledger"):
    counter["n"] = 0
    t = time.perf_counter()
    r = c.get(route)
    print(f"{route:10s} status={r.status_code} statements={counter['n']:6d} wall={time.perf_counter()-t:.2f}s")
