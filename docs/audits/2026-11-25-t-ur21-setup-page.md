# Frontend visual audit: T-UR21 first-run setup page

Task: T-UR21, branch wi/ui/sourdough/UR21. ADR-0027, ADR-0107, ADR-0134 section 9, ADR-0148, ADR-0150.
Method: frontend-visual-audit probe (Playwright, chromium) against a scratch server: a freshly migrated temp SQLite with zero users, `BUDGET_ENV=test`,
a configured `BUDGET_PLANNER_SETUP_TOKEN_HASH`; heavy lock /tmp/ui-redesign-heavy.lock taken and released around the run. data/budget.sqlite not touched.

## Routes and states

`/setup?token=...` in two states: open (empty form) and after a failed save (mismatched confirmation, server 422, inline `▲` error under the field).
Light and dark, each at 1440, 1024 and 375: 12 diagnostic rows. The e2e `tests/e2e/test_setup_page.py` also walks mismatch, fix, create, landing on
/today, and the redirect to sign in once setup is closed; the 404 without a token.

## Diagnostics

| State | horizontalScroll | overflowingElements | duplicateIds | requestFailures | consoleErrors |
|---|---|---|---|---|---|
| open, all widths, both themes | 0 | 0 | 0 | 0 | 0 |
| mismatch (422), all widths, both themes | 0 | 0 | 0 | 0 | 0 (1 expected: the browser's "Failed to load resource ... 422" line for the deliberate 422) |

The error is visible in every row (`#setup-confirm-error` visible, `aria-invalid` and `aria-describedby` set on the confirm field).

## Comparison

No handoff board exists for setup (derived.md row "First-run setup"). Compared by eye against `pages/auth/force-password` and `login` at 1440 and 375:
bake column and headline, title, lede, field labels, hint and `▲` error style, primary pill button match in structure, spacing and type. Phone: the bake
header collapses above the form like login.

## Findings

None blocking. The tablet and phone passes look like login. The 422 console line is expected behaviour.

## Step 3b

- Template pages/auth/setup.html: no `style=`, `{% set`, `float`, `/ 100`, `* 100`; messages come from `services.setup` and `services.users` (invalid
  email, under 12 characters, mismatch); the token and the name and email are echoed, the password fields are never refilled.
- Every failing save shows a visible error: field errors inline (422), throttle as the alert (429), wrong token a bare 404 by design (no oracle).
