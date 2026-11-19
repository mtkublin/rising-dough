# HTMX contract matrix (generated)

## 1. Application events: emitters vs listeners

| Event | Emitted by (HX-Trigger / JS dispatch) | Listened by (hx-trigger / addEventListener) | Status |
|---|---|---|---|
| `balance-stale` | `routers/accounts.py:242`, `routers/accounts.py:344`, `routers/accounts.py:356`, `routers/accounts.py:508` (+7) | - | ORPHAN emitter (no listener) |
| `budget-stale` | `routers/budget.py:262`, `routers/budget.py:292`, `routers/budget.py:343`, `routers/budget.py:371` (+9) | - | ORPHAN emitter (no listener) |
| `forecast-stale` | `routers/accounts.py:356`, `routers/accounts.py:508`, `routers/planned.py:91`, `routers/planned.py:282` (+15) | `t/partials/forecast/_view.html:2` | paired |
| `ledger-stale` | `routers/planned.py:91`, `routers/planned.py:282`, `routers/planned.py:399`, `routers/planned.py:415` (+13) | `t/ledger/_table.html:22` | paired |
| `settings-categories-stale` | `routers/categories.py:237` | - | ORPHAN emitter (no listener) |
| `toast` | `routers/accounts.py:356`, `routers/accounts.py:386`, `routers/categories.py:237`, `routers/planned.py:91` (+1) | `static/js/app-init.js:36` | paired |
| `today-stale` | `routers/planned.py:91`, `routers/recurring.py:446` | - | ORPHAN emitter (no listener) |

Emitted names: 7; listened names: 3; orphan emitters: 4; orphan listeners: 0.

## 2. HTMX lifecycle listeners (htmx:*)

| Event | Listeners |
|---|---|
| `htmx:afterRequest` | `static/js/app-init.js:11`, `static/js/budget-override.js:49`, `static/js/overlay-actions.js:75` |
| `htmx:afterSwap` | `static/js/budget-override.js:42`, `static/js/bulk-select.js:83`, `static/js/combobox.js:164` |
| `htmx:beforeRequest` | `static/js/budget-override.js:35` |
| `htmx:beforeSwap` | `static/js/app-init.js:4`, `static/js/app-init.js:71`, `static/js/users-admin.js:73` |
| `htmx:load` | `static/js/budget-override.js:121`, `static/js/rd-wire.js:28` |

## 3. Other HX-* response headers set by routers/middleware

| Header | Value | Location |
|---|---|---|
| `HX-Redirect` | `url` | `deps.py:133` |
| `HX-Reswap` | `'none'` | `htmx.py:42` |
| `HX-Refresh` | `'true'` | `htmx.py:45` |
| `HX-Redirect` | `_login_url(_hx_current_path(request))` | `middleware/auth.py:136` |
| `HX-Redirect` | `password_url(_hx_target(request))` | `middleware/must_change_password.py:76` |
| `HX-Reswap` | `'none'` | `routers/accounts.py:245` |
| `HX-Refresh` | `'true'` | `routers/accounts.py:246` |
| `HX-Reswap` | `'none'` | `routers/categories.py:116` |
| `HX-Refresh` | `'true'` | `routers/categories.py:117` |
| `HX-Redirect` | `target` | `routers/settings_password.py:157` |
| `HX-Reswap` | `'none'` | `routers/settings_users.py:122` |
| `HX-Retarget` | `'#user-edit-form'` | `routers/settings_users.py:200` |
| `HX-Reswap` | `'outerHTML'` | `routers/settings_users.py:201` |

## 4. Swap targets that resolve to no id/class in any template, router or JS

| Attr | Selector | Location | Result |
|---|---|---|---|

Checked 113 selectors (4 fully dynamic, unverifiable statically); missing: 0.

## 5. Literal ids defined in more than one file

| id | Defined in |
|---|---|
| `cat-form-slot` | `t/categories/index.html`, `t/settings/_categories.html` |
| `main` | `t/auth/_layout.html`, `t/base.html` |
| `modal-root` | `t/base.html`, `t/planned/index.html` |
| `pw-heading` | `t/settings/password.html`, `t/settings/security.html` |

4 literal ids appear in more than one file (static only).

## 6. Literal ids repeated within one file

| id | File | Lines |
|---|---|---|
| `pw-summary` | `t/settings/_password_form.html` | 50, 52 |
