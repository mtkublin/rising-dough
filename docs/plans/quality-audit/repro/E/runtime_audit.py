"""T-Q08 Track E runtime confirmation (frontend-visual-audit style, scratch DB only).

Usage (never against data/budget.sqlite):
  cp data/demo.sqlite /tmp/audit-E.sqlite
  BUDGET_DATABASE_URL=sqlite:////tmp/audit-E.sqlite uv run python \
      docs/plans/quality-audit/repro/E/runtime_audit.py setup
  BUDGET_DATABASE_URL=sqlite:////tmp/audit-E.sqlite BUDGET_ENV=dev \
      BUDGET_COOKIE_SECRET=audit-e-not-a-secret uv run uvicorn \
      budget_planner.web.app:app --port 8765 &
  uv run python docs/plans/quality-audit/repro/E/runtime_audit.py audit http://127.0.0.1:8765

``setup`` migrates the scratch DB and gives user 1 a login. ``audit`` sweeps the routes at
1440 / 1024 / 375 and runs the behaviour probes; JSON goes to stdout.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

SCRATCH = "/tmp/audit-E.sqlite"  # noqa: S108
ROUTES = [
    "/today",
    "/ledger",
    "/ledger?view=recurring",
    "/ledger?view=planned",
    "/accounts",
    "/plan",
    "/plan?tab=year",
    "/plan?tab=forecast",
    "/plan?tab=analytics",
    "/settings",
    "/settings/security",
    "/settings/password",
    "/settings/users",
    "/planned",
    "/categories",
    "/recurring",
    "/transactions",
    "/budget",
    "/forecast",
]
VIEWPORTS = [(1440, 900), (1024, 768), (375, 812)]

_DIAG_JS = """() => {
  const seen = new Map();
  document.querySelectorAll('[id]').forEach(e => seen.set(e.id, (seen.get(e.id) || 0) + 1));
  const dup = [...seen].filter(([, n]) => n > 1).map(([id, n]) => ({id, n}));
  const triggers = [...document.querySelectorAll('[hx-trigger]')]
    .map(e => e.getAttribute('hx-trigger'));
  const targets = [...document.querySelectorAll('[hx-target]')].map(e => {
    const t = e.getAttribute('hx-target');
    let found = true;
    try {
      if (t.startsWith('closest ')) found = !!e.closest(t.slice(8));
      else if (!['this', 'body'].includes(t)) found = !!document.querySelector(t);
    } catch (err) { found = 'bad-selector'; }
    return {t, found};
  }).filter(x => x.found !== true);
  return {dup, triggers, missingTargets: targets,
          hscroll: document.documentElement.scrollWidth > innerWidth};
}"""


def setup() -> None:
    from budget_planner.config import Settings
    from budget_planner.db.connection import get_connection
    from budget_planner.db.migrate import apply_migrations
    from tests.auth_support import seed_login_user

    assert os.environ["BUDGET_DATABASE_URL"] == f"sqlite:///{SCRATCH}", "scratch DB only"
    conn = get_connection(Settings(_env_file=None))
    try:
        apply_migrations(conn)
        seed_login_user(conn)
    finally:
        conn.close()


def _login(ctx: Any, base: str) -> str:
    from tests.auth_support import TEST_EMAIL, TEST_PASSWORD

    ctx.request.get(f"{base}/health")
    token = next(c["value"] for c in ctx.cookies() if c["name"] == "csrf")
    resp = ctx.request.post(
        f"{base}/auth/login",
        form={"email": TEST_EMAIL, "password": TEST_PASSWORD, "next": "/today", "_csrf_token": token},
        max_redirects=0,
    )
    assert resp.status == 303, resp.status
    return str(token)


def _sweep(browser: Any, base: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for w, h in VIEWPORTS:
        ctx = browser.new_context(viewport={"width": w, "height": h})
        _login(ctx, base)
        for route in ROUTES:
            page = ctx.new_page()
            errs: list[str] = []
            fails: list[str] = []
            page.on("console", lambda m, e=errs: e.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e, errs=errs: errs.append(f"pageerror: {e}"))
            page.on("requestfailed", lambda r, f=fails: f.append(r.url))
            page.on(
                "response",
                lambda r, f=fails: f.append(f"{r.status} {r.url}") if r.status >= 400 else None,
            )
            page.goto(f"{base}{route}", wait_until="networkidle")
            diag = page.evaluate(_DIAG_JS)
            out.append({"route": route, "vp": w, "consoleErrors": errs, "requestFailures": fails, **diag})
            page.close()
        ctx.close()
    return out


def _probes(browser: Any, base: str) -> dict[str, Any]:
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    _login(ctx, base)
    page = ctx.new_page()
    res: dict[str, Any] = {}
    # P1: toast payloads: accounts emit {kind}, planned/recurring/categories emit {variant}.
    page.goto(f"{base}/today", wait_until="networkidle")
    res["toast_classes"] = page.evaluate(
        """() => {
          const fire = d => document.body.dispatchEvent(new CustomEvent('toast', {detail: d}));
          fire({kind: 'success', message: 'accounts-shape'});
          fire({variant: 'success', message: 'planned-shape'});
          return [...document.querySelectorAll('#toast-root .rd-toast')].map(e => e.className);
        }"""
    )
    # P2: bulk delete uses bare fetch(); does it carry X-CSRF-Token?
    page.goto(f"{base}/ledger", wait_until="networkidle")
    reqs: list[dict[str, Any]] = []
    page.on(
        "response",
        lambda r: reqs.append(
            {"url": r.url, "status": r.status, "csrf_header": "x-csrf-token" in r.request.headers}
        )
        if r.request.method == "POST"
        else None,
    )
    boxes = page.locator("[data-bulk-row]")
    res["bulk_rows_present"] = boxes.count()
    if boxes.count():
        boxes.first.check()
        page.on("dialog", lambda d: d.accept())
        page.evaluate("document.body.addEventListener('ledger-stale', () => window.__stale = (window.__stale||0)+1)")
        page.locator("[data-bulk-delete]").click()
        page.wait_for_timeout(1500)
        res["stale_events_fired"] = page.evaluate("window.__stale || 0")
    res["bulk_delete_requests"] = reqs
    # P3: do HTMX 4xx responses carrying an OOB flash reach the user? (htmx 2 default: no swap)
    page.goto(f"{base}/ledger", wait_until="networkidle")
    res["error_flash"] = page.evaluate(
        """async () => {
          let respErrors = 0;
          document.body.addEventListener('htmx:responseError', () => respErrors++);
          await htmx.ajax('GET', '/transactions/999999/edit', {target: '#modal-root', swap: 'innerHTML'})
            .catch(() => null);
          await new Promise(r => setTimeout(r, 600));
          return {
            respErrors,
            flash: document.getElementById('flash-region').innerText,
            flashAssertive: document.getElementById('flash-region-assertive').innerText,
          };
        }"""
    )
    ctx.close()
    return res


def audit(base: str) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        sweep = _sweep(browser, base)
        probes = _probes(browser, base)
        browser.close()
    json.dump({"sweep": sweep, "probes": probes}, sys.stdout, indent=1)


def fx_probe(base: str) -> None:
    """Does the recurring 'Monthly out' strip convert foreign-currency rules to PLN? (scratch DB)"""
    import sqlite3

    from playwright.sync_api import sync_playwright

    def strip(page: Any) -> str:
        page.goto(f"{base}/ledger?view=recurring", wait_until="networkidle")
        return str(page.locator(".rd-recurring-strip").inner_text()).replace("\n", " ")

    db = sqlite3.connect(SCRATCH)
    acc = db.execute(
        "SELECT a.id FROM recurring_rules r JOIN accounts a ON a.id = r.account_id "
        "WHERE r.deleted_at IS NULL GROUP BY a.id ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()[0]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context()
        _login(ctx, base)
        page = ctx.new_page()
        before = strip(page)
        db.execute("UPDATE accounts SET currency = 'EUR' WHERE id = ?", (acc,))
        db.commit()
        after = strip(page)
        db.execute("UPDATE accounts SET currency = 'PLN' WHERE id = ?", (acc,))
        db.commit()
        browser.close()
    print(json.dumps({"account_flipped": acc, "before": before, "after_eur": after}))


if __name__ == "__main__":
    if sys.argv[1] == "setup":
        setup()
    elif sys.argv[1] == "fx":
        fx_probe(sys.argv[2])
    else:
        audit(sys.argv[2])
