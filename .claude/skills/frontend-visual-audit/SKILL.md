---
name: frontend-visual-audit
description: Systematically audit a running frontend by driving a headless browser (Playwright), capturing full-page screenshots at multiple viewports, and collecting runtime diagnostics (layout overflow, clipped elements, console errors, failed network requests). Use when the user reports visual bugs the agent cannot see (horizontal scroll, missing content, broken responsive layout, elements that disappear) or asks for a visual sweep across routes.
---

# Frontend Visual Audit

Reusable workflow for visually auditing a running web app without a human-in-the-loop screenshot pass. Produces screenshots + a diagnostic JSON per route and feeds back a categorized findings list.

Use when:
- User reports a visual bug that cannot be reproduced from reading the code alone.
- Change touched layout / CSS / responsive breakpoints and must be verified across pages.
- Reviewing a redesign or shell change (navigation, scroll behavior, overflow, sticky positioning).
- Smoke-checking that every known route renders without a runtime error.

Do **not** use for:
- Backend-only changes.
- Service logic or data correctness (use route-level integration tests). **Exception:** the numbers a template prints and the HTMX contract are in scope (Step 3b).
- Accessibility deep audits — this covers surface signals only (missing alt, duplicate IDs, visible focus). Use a dedicated a11y tool for a full audit.

## Prerequisites

- Target app is running locally and reachable (e.g. `http://127.0.0.1:8000`).
- Node available (`node --version`) **or** Python with Playwright (`uv run python -c "import playwright"`).
- Playwright browsers installed (`npx playwright install chromium` or `uv run playwright install chromium`). If missing, install before running the script.
- A writable output directory for screenshots + JSON (default: `/tmp/fe-audit/`).

## Step 1 — Enumerate routes

Pick what to audit. Scope options:

- **Full map**: every GET route the app exposes. Pull from the router (FastAPI `app.routes`, Next.js file tree, React Router config).
- **Shell smoke**: top-nav destinations + a handful of representative detail pages.
- **Targeted**: the one or two routes that reproduce the reported bug.

Encode as a plain list the script iterates over. Keep the base URL separate so the same script works against dev / staging.

## Step 2 — Audit script

Save as `audit-frontend.js` (or `.py`). Default viewports cover desktop + tablet + narrow mobile; adjust to the app's declared breakpoints.

```js
// audit-frontend.js
const { chromium } = require('playwright');
const fs = require('fs');

const BASE = process.env.AUDIT_BASE || 'http://127.0.0.1:8000';
const OUT  = process.env.AUDIT_OUT  || '/tmp/fe-audit';
const ROUTES = [
  '/',
  // add routes here
];
const VIEWPORTS = [
  { label: 'desktop', width: 1440, height: 900 },
  { label: 'tablet',  width: 1024, height: 768 },
  { label: 'mobile',  width:  375, height: 812 },
];

const DIAGNOSTIC = () => ({
  viewport:        [window.innerWidth, window.innerHeight],
  docScroll:       [document.documentElement.scrollWidth, document.documentElement.scrollHeight],
  horizontalScroll: document.documentElement.scrollWidth > window.innerWidth,
  verticalScroll:   document.documentElement.scrollHeight > window.innerHeight,
  // Elements wider than the viewport — common cause of horizontal scroll.
  overflowingElements: Array.from(document.querySelectorAll('body *'))
    .filter(el => el.getBoundingClientRect().right > window.innerWidth + 1)
    .slice(0, 20)
    .map(el => ({
      tag: el.tagName.toLowerCase(),
      id: el.id || null,
      cls: el.className && typeof el.className === 'string' ? el.className : null,
      right: Math.round(el.getBoundingClientRect().right),
    })),
  // Elements clipped by an ancestor with overflow: hidden/clip.
  clippedElements: Array.from(document.querySelectorAll('body *'))
    .filter(el => {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) return false;
      return r.bottom > window.innerHeight + document.documentElement.scrollTop + 50
          || r.top < -50;
    })
    .slice(0, 20)
    .map(el => ({ tag: el.tagName.toLowerCase(), id: el.id || null })),
  // Fixed/sticky elements — flag so the human reviewer can sanity-check them.
  fixed: Array.from(document.querySelectorAll('body *'))
    .filter(el => ['fixed','sticky'].includes(getComputedStyle(el).position))
    .slice(0, 10)
    .map(el => ({ tag: el.tagName.toLowerCase(), id: el.id || null, position: getComputedStyle(el).position })),
  images: {
    total: document.images.length,
    broken: Array.from(document.images).filter(i => !i.complete || i.naturalWidth === 0).length,
  },
  duplicateIds: (() => {
    const seen = new Map();
    document.querySelectorAll('[id]').forEach(e => seen.set(e.id, (seen.get(e.id)||0)+1));
    return Array.from(seen.entries()).filter(([,n]) => n > 1).map(([id,n]) => ({ id, count: n }));
  })(),
});

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const summary = [];

  for (const vp of VIEWPORTS) {
    const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    for (const route of ROUTES) {
      const page = await context.newPage();
      const consoleErrors = [];
      const requestFailures = [];
      page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
      page.on('pageerror', e => consoleErrors.push(`pageerror: ${e.message}`));
      page.on('requestfailed', r => requestFailures.push({ url: r.url(), reason: r.failure()?.errorText }));

      const url = `${BASE}${route}`;
      const slug = `${vp.label}__${route.replace(/\W+/g, '_') || 'root'}`;
      try {
        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });
        await page.waitForSelector('main', { timeout: 5000 }); // a known-rendered element
      } catch (e) {
        summary.push({ route, viewport: vp.label, error: String(e) });
        await page.close();
        continue;
      }
      await page.waitForTimeout(500);
      const diag = await page.evaluate(DIAGNOSTIC);
      const shotPath = `${OUT}/${slug}.png`;
      await page.screenshot({ path: shotPath, fullPage: true });
      fs.writeFileSync(`${OUT}/${slug}.json`, JSON.stringify({ route, url, viewport: vp, diag, consoleErrors, requestFailures }, null, 2));
      summary.push({
        route, viewport: vp.label,
        horizontalScroll: diag.horizontalScroll,
        overflowingCount: diag.overflowingElements.length,
        duplicateIds: diag.duplicateIds.length,
        brokenImages: diag.images.broken,
        consoleErrors: consoleErrors.length,
        requestFailures: requestFailures.length,
        screenshot: shotPath,
      });
      console.log(`${vp.label} ${route} — overflow:${diag.horizontalScroll} errs:${consoleErrors.length}`);
      await page.close();
    }
    await context.close();
  }
  fs.writeFileSync(`${OUT}/summary.json`, JSON.stringify(summary, null, 2));
  await browser.close();
})();
```

Run:

```bash
node audit-frontend.js
# or override:
AUDIT_BASE=http://127.0.0.1:3000 AUDIT_OUT=./audit node audit-frontend.js
```

Python variant (same logic) available if the project pins Playwright through `uv`.

## Step 3 — Review signals

Read `summary.json` first to pick which routes to inspect. For each row with non-zero signals, open the matching `.json` for detail and the matching `.png` for ground truth.

Signals and what they usually mean:

| Signal | Likely cause | Where to look |
|--------|--------------|---------------|
| `horizontalScroll: true` | A descendant exceeds viewport width | `overflowingElements[]` first entry |
| `overflowingElements[]` populated but `horizontalScroll: false` | Content is clipped by `overflow-x: hidden/clip` on an ancestor — may still be visually broken | Compare screenshot against intended design |
| `verticalScroll: false` but page clearly has more content | A scroll container (usually `overflow-x: hidden` on a tall ancestor) is swallowing Y scroll — use `overflow-x: clip` instead | Any ancestor of `main` with non-visible overflow-x |
| `consoleErrors[]` non-empty | JS runtime error or 404 for an asset | Open the JSON entry |
| `requestFailures[]` non-empty | Missing static asset, wrong asset path, CORS | URL in the entry |
| `duplicateIds[]` non-empty | Fragment / partial reused incorrectly — HTMX swaps may misbehave | Entry lists the offending ids |
| `images.broken > 0` | Missing or wrongly-pathed image | Inspect screenshot + network |
| Fixed/sticky element missing from screenshot | Positioning or z-index regression | `fixed[]` entry + screenshot |

## Step 3b — Behaviour contract and template logic (MANDATORY for template / HTMX changes)

Each item needs evidence (page text, DOM query, a forced response), not an opinion. Report the result per route. The static guards (template-logic and HTMX-contract tests in `tests/architecture/`, ADR-0130) must also be green; this step proves what they cannot.

1. **Swap targets exist.** For every `hx-target` / `hx-swap` on the page, the target selector matches exactly one element, before and after the swap (`document.querySelectorAll(sel).length === 1`).
2. **Failing saves are visible.** For every state-changing form, force a 404, 409 and 500 (intercept the request with `page.route`, or submit a stale id) and confirm a visible error or flash appears and the form is not left looking saved. Silent failure is a blocking finding.
3. **No arithmetic in templates.** No `float`, `/ 100`, `* 100`, `set` blocks re-deriving a service value, or hard-coded currency or period literals in the touched templates (`rg` the files). Derived values come from the view model.
4. **Money formatting by currency.** Amounts go through the `money` / `money_num(currency)` filters; check one non-PLN and one zero-decimal currency (JPY) on the scratch DB.
5. **Rendered number equals the service value.** Read the number from the page text, call the service function on the same scratch DB, compare. Mismatch is blocking.
6. **IDs and listeners.** No duplicate ids after a swap (re-run the diagnostic after the HTMX request). Every emitted `HX-Trigger` event has a listener, and every listener has an emitter.
7. **Scratch data only.** Run against `--db=<scratch>` or `data/demo.sqlite`, never `data/budget.sqlite`.

## Step 4 — Categorize findings

| Category | Description | Where to fix |
|----------|-------------|--------------|
| **Layout** | Horizontal scroll, clipped content, broken responsive breakpoint, misaligned grid | CSS tokens / layout rules |
| **Content** | Broken image, missing fragment, duplicate IDs after an HTMX swap | Template / partial / data-plumbing |
| **Behavior** | Console error, failed network request, missing JS init, silent failed save, swap target missing | Client script / asset path / router error handling / HTMX contract |
| **Template logic** | Arithmetic, `float`, literals or re-derived values in a template; rendered number differs from the service | View model / service; not the template |
| **A11y surface** | Missing focus ring on an interactive element in the screenshot, invisible nav target | Component CSS + ARIA |

Write category + concrete file:line pointers directly in the response. Don't dump raw screenshots.

## Step 5 — Fix plan

Short plan is enough — one bullet per finding with the file to edit and the one-line change. If a finding needs more than one file, split it into its own bullet so the user can approve piecewise.

If findings are many or interact, write a plan file:

- Layout / behavior fixes: `.claude/plans/todo/frontend-visual-fixes.md`

Format each entry: *Route — viewport — one-line symptom — suggested fix (path:line).*

## Step 6 — Write the audit record (MANDATORY when the change touches templates or CSS)

Commit `docs/audits/<YYYY-MM-DD>-<slug>.md` in the same change (guard G31, `tests/architecture/test_frontend_audit_record.py`, fails without it). Required content:

- **Routes** audited (path list) and the change they belong to (task id).
- **Viewports**: 1440, 1024 and 375, one row per route x viewport.
- **Diagnostics**: for each row the five signals `horizontalScroll`, `overflowingElements`, `duplicateIds`, `consoleErrors`, `requestFailures` (value, or 0/false), plus findings fixed or triaged.
- **Screenshots**: paths of the captured PNGs (viewed by you; say what you checked).

Ad-hoc Playwright scripts do not replace the skill run; the record must come from it.

## Common gotchas

- **`overflow-x: hidden` on a tall ancestor breaks vertical scroll.** Use `overflow-x: clip` instead — `clip` doesn't establish a scroll container, so Y scroll propagates normally.
- **`height: 100dvh` falls back to `auto` in older Safari.** Add `height: 100vh;` before `height: 100dvh;` for a safe fallback.
- **Sticky elements inside a flex row** need `align-self: flex-start` (or the parent needs `align-items: flex-start`), otherwise the flex item stretches to the row height and `top: 0` has no effect.
- **Stale Tailwind output**: `static/tailwind.css` is a local build. If a new utility class has no effect, run `just css` (the `tailwind-check` hook fails on a stale file). Hard-reload to bypass the browser cache.
- **Server-rendered SVG charts and any canvas/iframe widget** can have a fixed intrinsic size and overflow narrow containers. Give the SVG a `viewBox` with `width: 100%` or wrap in `overflow-x: auto`.
- **Never use `networkidle`** (unreliable with HTMX polling and SSE); the script waits for `domcontentloaded` plus a known-rendered element.
- **Headless Chromium default viewport is 1280×720** — always set an explicit viewport before `goto`, or responsive bugs hide.
- **Full-page screenshot is the ground truth**, not the diagnostic JSON. If a signal and the screenshot disagree, trust the screenshot and widen the diagnostic.
