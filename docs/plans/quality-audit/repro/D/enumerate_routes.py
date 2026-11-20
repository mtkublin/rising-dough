"""Enumerate every route of the app (T-Q07). Run with BUDGET_DATABASE_URL=sqlite:////tmp/audit-D.sqlite."""
import inspect
from fastapi.routing import APIRoute
from starlette.routing import Mount, Route
from budget_planner.web.app import app

def walk(routes, prefix=""):
    for r in routes:
        if isinstance(r, APIRoute):
            yield prefix + r.path, sorted(r.methods or []), r.endpoint
        elif isinstance(r, Mount):
            yield prefix + r.path + "/*", ["MOUNT"], None
        elif isinstance(r, Route):
            yield prefix + r.path, sorted(r.methods or []), r.endpoint
        elif hasattr(r, "original_router"):  # FastAPI >= 0.13x _IncludedRouter
            yield from walk(r.original_router.routes, prefix)
        else:
            print("UNKNOWN", type(r), vars(r).keys())

rows = []
for path, methods, ep in walk(app.routes):
    mod = ep.__module__.split(".")[-1] if ep else "-"
    loc = f"{inspect.getsourcefile(ep).split("src/")[-1].split("site-packages/")[-1]}:{inspect.getsourcelines(ep)[1]}" if ep else "-"
    rows.append((mod, path, ",".join(methods), ep.__name__ if ep else "-", loc))
for row in sorted(rows):
    print("|".join(map(str, row)))
print("TOTAL", len(rows))
