# Track G: dead code, doc drift and config drift (T-Q10)

`AUDIT_SHA = 9fb18cbca26ef305855efc8fc106d896edc82631`. Every `path:line` is valid at this SHA (this branch only adds audit docs). Read-only audit: nothing under `src/`, `tests/`, config, ADRs or CHANGELOG was changed.

## 1. Coverage statement

| Area | How it was checked | Depth |
|---|---|---|
| vulture (172 hits) | every hit classified by hand, section 2.1 | complete; dynamic/pydantic/handler hits grouped |
| Routes (113 handlers, 19 routers) | route table dumped from the router modules; each path grepped in templates, JS, `.py`, tests | complete |
| Templates (111 files, 16 flagged) | grep of full relative path, bare name, `include`/`extends`/`import`/`from`, string-built names (`"settings/_" ~ active_tab`) | complete |
| JS (19 files) and CSS | each file name grepped in `base.html` and templates | complete; unused CSS classes (132/658) not examined, out of scope per ADR-0107 |
| Macros | 15 files in `_partials/components/` checked for importers | complete |
| ADRs (129 files, numbers 0001-0128) | 4 parallel readers, each verified the 1-3 most load-bearing claims per ADR against code/config; drift claims I re-verified myself are marked (V). Several ADRs got an index/status-line check plus presence check only | **shallow for ~40 ADRs** (see "Depth" in section 3); no ADR was read line by line |
| CHANGELOG vs tasks.md | scripted over all 9 `docs/plans/*/tasks.md` | complete for ids; wording not compared |
| requirements.md | every top-level section skimmed, sections 3.x/6.x compared with code | section 3 deep, sections 6-12 spot-checked only |
| CLAUDE.md, justfile, skills | every command and path referenced | complete |
| Config parity | `.pre-commit-config.yaml`, `justfile`, `ci.yml`, `security.yml`, `terraform.yml`, `uv.lock`, `pyproject.toml` | complete for Python/frontend; Terraform workflows only skimmed |

Not done: line-by-line reading of all ADR bodies; checking every requirements.md bullet; unused CSS; running the app.

Repro: `docs/plans/quality-audit/repro/G/fx_client_no_base_url.py` (+ `.out`).

## 2. Dead code

### 2.1 vulture hits (172 at 60%), classified

| Group | Hits | Classification | Notes |
|---|---|---|---|
| FastAPI route handlers (`index`, `new_form`, `create_*`, `login_*`, ...) in `web/routers/*` | about 105 | used dynamically (decorator registration) | the vulture whitelist pass was never done; a whitelist or `--ignore-decorators "@router.*"` would remove them |
| Middleware `dispatch` (admin, auth, csrf, must_change_password, request_id, security_headers) | 6 | used dynamically (Starlette) | |
| `config.py` pydantic fields and validators (`model_config`, `bind_host`, `trusted_hosts`, `_upper_ccy`, `_finalise`, ...) | 12 | used dynamically (pydantic), **except** `fx_api_url` (config.py:70) and `bind_port` (config.py:52) | `fx_api_url` is never read anywhere in `src/`; this hides a live bug, see G-01. `bind_port` is only read by a unit test (`tests/unit/test_config.py:24`) |
| Frozen-dataclass fields (`updated_at`, `fetched_at`, `taken_at`, `net_minor`, `largest_items`, `category_direction`, `avg_*`, `base_balance`, `txn_count`, `assets_base`, ...) in `domain/*`, `services/*` | about 45 | used dynamically (populated by `Row` mapping or read from Jinja; spot-checked `net_minor`, `largest_items`, `category_direction`, `avg_this_year_minor`, `rising`, `position` in templates) | `web/charts.py:414-415` `bar_height`, `value_label` are set at `charts.py:487-488` but read by **no template**: unsure, probably dead data |
| `domain/enums.py:39-42` `AuditOperation.CREATE/UPDATE/DELETE/UNDELETE` | 4 | used dynamically (`AuditOperation(row["operation"])` at `repositories/audit.py:22`); repositories write raw strings (`repositories/accounts.py:177`) | enum members are documentation only |
| `db/connection.py:73` `row_factory`, `web/middleware/csrf.py:138,149` `_receive` | 3 | false positive (attribute assignment on foreign object) | |
| `db/seed.py:53` `seed` | 1 | used (CLI `python -m`, 14 tests) | |
| `repositories/rate_limit.py:36` `get_count` | 1 | **dead in src**, used by 2 tests only | |
| `web/htmx.py:31` `trigger_from_iterable` | 1 | **dead in src**, 3 tests only | |
| `web/htmx.py:13` `is_htmx` | 1 | **dead in src** (`web/errors.py:30` has its own `_is_htmx`) | duplicate helper |
| `web/rendering.py:51` `render_str` | 1 | **dead in src**, used by `tests/integration/web/test_csrf.py` only | |
| `domain/accounts.py:97` `last_activity_date` | 1 | **dead in src**, tested only (`tests/unit/services/test_balance.py:279`) | |
| `services/password_change.py:84` `message_for` | 1 | used dynamically (Jinja `settings/_password_form.html:3`) | |
| `web/routers/plan.py:284` `_redirect_budget` | 1 | used dynamically but nothing links to `/budget-legacy` | G-11 |
| `web/routers/today.py:175` `afford_alias` | 1 | used dynamically but template calls `/today/afford` (`today/index.html:63`) | G-11 |
| `web/routers/dev_components.py:20` | 1 | used (dev-only page, 404 in production) | |
| remaining variables (`web/today_data.py:47 balance_minor`, `web/routers/transactions.py:44 projected_balance`, `services/recurring_formula.py:459,461`, `services/forecast.py:59,927-929`, `services/export.py:38`) | about 12 | used dynamically (dataclass fields) / unsure | |

Survivors judged dead: `get_count`, `trigger_from_iterable`, `is_htmx`, `render_str`, `last_activity_date`, `fx_api_url`, `bind_port`, and the unread chart fields. All are Low except `fx_api_url` (G-01).

### 2.2 Templates (16 flagged by the baseline)

| Template | Verdict | Evidence |
|---|---|---|
| `.gitkeep` | false positive | not a template |
| `_partials/components/_period_header.html`, `_table_row.html` | dead | no importer anywhere in `src/` or `tests/` |
| `budget/manage.html` | dead | `GET /budget/manage` now redirects (`routers/budget.py:306-312`); only `manage.html:22` itself posts `/budget/defaults` |
| `categories/index.html`, `planned/index.html`, `recurring/index.html`, `transactions/index.html` | dead | their index routes are 302 redirects to the ledger/settings (`routers/categories.py:22`, `planned.py:55`, `recurring.py:58`, `transactions.py:113`); no `render(...)` names them |
| `partials/_cheatsheet.html`, `_direction_badge.html`, `_money.html`, `_pagination.html` | dead | no includer. `partials/_direction_badge.html` is a duplicate of `_partials/components/_direction_badge.html` |
| `partials/accounts/_fortune_split.html`, `_totals.html` | dead | no includer |
| `settings/_fx.html`, `settings/_prefs.html` | **false positive** | included by string concatenation `{% include "settings/_" ~ active_tab ~ ".html" %}` at `settings/_drawer.html:44` |

So 13 real orphans, 2 false positives (`settings/_fx`, `settings/_prefs`), and `.gitkeep`. Also: `_partials/components/_button.html`, `_direction_badge.html`, `_filter_chips.html`, `_pill.html`, `_toast.html` are imported only by the dev page `templates/dev/components.html:3-12` (a dev-only gallery that 404s in production, `routers/dev_components.py:25`). Whether they survive the ADR-0107 redesign is the redesign's call, but today nothing in production renders them. `_partials/segmented.html` and `partials/_*` pairs exist next to `_partials/components/*` (two partial trees).

### 2.3 JS, CSS, macros, migrations

- JS: all 19 files under `static/js/` plus `htmx-csrf.js` are referenced (`base.html:26-90`, `passkeys.js` and `users-admin.js` from their own templates). No dead JS file. `docs/requirements.md:180` names `static/js/overlay-stack.js`, which does not exist (G-09).
- CSS: every `static/*.css` file is referenced except `tailwind.src.css` (build input, by design). 132 of 658 classes unused per baseline: out of scope (ADR-0107), not examined.
- Migration helpers: no unreferenced helper found in `db/migrate.py`/`db/startup_migrate.py` (not exhaustively traced).
- Re-exports and shims: `services/planned.py:75-78` re-export of `UnsupportedDirectionError`/`ValidationError` is **live** (used at `routers/planned.py:86,530`); `services/recurring.py:633-640` re-export of `rt_expand`/`resolve_rule_amount` is **live** (`services/budget.py:307`, `services/forecast.py:387`); `PlannedKind = Literal["persisted"]` (`services/planned.py:37`) is a single-valued alias kept "so templates keep reading `view.kind`" and could be removed. `services/balance.py:204-206` `balance_series` is documented as a shim with a "Phase 7 task should replace it" note; Phase 7 is long past.
- `web/app.py:236-247` `_register_routers` wraps each router import in `except ImportError: continue  # pragma: no cover` ("tolerated so each task can commit atomically"): the iterative-landing rationale is stale and the guard can silently drop a whole router (G-14).

### 2.4 Routes with no UI caller

Searched templates, `static/js`, router-built URLs and `HX-Trigger` payloads.

| Route | Handler | Callers | Verdict |
|---|---|---|---|
| `POST /recurring/formula/preview` | `routers/recurring.py:546` | tests only (`tests/integration/web/test_formula_preview.py`) | ADR-0056 section 4 live-preview is unreachable: `partials/recurring/_form.html` does not call it, `recurring-form.js` has no preview code, `_formula_preview.html` is rendered only by this handler |
| `POST /recurring/batch/promote-due` | `routers/recurring.py:424` | none (Today wires only `/planned/batch/promote-due`, `today/index.html:119`) | dead UI path; `recurring_batch_undo` (`:469`) is reachable only through the toast this route emits |
| `GET /accounts/last-checked` | `routers/accounts.py:133` | tests only | dead; `partials/accounts/_last_checked.html` exists only for it |
| `POST /budget/recurring/{category_id}/{month}` | `routers/budget.py:347` | none (the tab uses `/budget/defaults` and `/budget/one-off`) | dead |
| `GET /plan/analytics` | `routers/plan.py:254` | tests only (`test_plan_analytics.py`) | dead; `_analytics_bundle.html` is also included directly by `plan/_analytics_tab.html:19` |
| `GET /budget-legacy` | `routers/plan.py:284` | none | dead |
| `GET /afford` | `routers/today.py:175` | none (`today/index.html:63` calls `/today/afford`) | dead alias ("Phase 7 cleanup drops this") |
| `GET /analytics`, `/budget/manage`, `/categories`, `/transactions`, `/planned`, `/recurring` (index) | various | `partials/_nav.html:26,31` still lists `/analytics` and `/categories` as `extra_paths` | legacy 302 redirects "kept for one release per ADR-0023" (T-070); `routers/analytics.py` is a whole module for one redirect and says "removes this module in a Phase 7 cleanup" |

## 3. ADR drift

ADR README index vs files: every file is indexed and every index link resolves. Structural findings:

- **Duplicate numbers**: `0105-ci-principals-in-durability-bucket-policies.md` and `0105-committed-includes-all-overdue-items.md`; `0121-drill-gate-skip-for-non-deploy-prs.md` and `0121-path-filtered-workflows-are-not-required-checks.md`. Any "ADR-0105" or "ADR-0121" reference is ambiguous. (The Mutmut plan's ADR-0095 collision named in the plan is not a file collision: 0095 is unique, it is already taken by `0095-budget-committed-converts-to-base-currency.md`, so the Mutmut ADR needs a free number, 0129 or later.)
- **Gap**: 0044 does not exist (no file, no index row, not referenced).
- **Index order**: rows out of numeric order: 0100 before 0099, 0113 before 0112, 0128 before 0127, 0105/0121 pairs.
- **Index vs file titles** differ for 21 ADRs (0022, 0024, 0025, 0027, 0030, 0031, 0032, 0041, 0057-0060, 0064, 0075, 0087, 0089, 0091-0093), mostly cosmetic; 0031 is substantive (index: "Explicit '+ Rule' Create Affordance", file: "Rules Row Override Popup, Yearly Grid").
- **Broken links** (3): `0091-...:` to `0032-v3-hosting-scaleway-poland.md` and `0034-v3-backups-litestream-to-object-storage.md`; `0092-...` to `0034-v3-backups-litestream-to-object-storage.md` (old filenames, renamed to `0032-v3-remote-deployment-...` and `0034-v3-sqlite-replication-litestream.md`).
- README line 19 (ADR-0013) lacks the "(superseded by ADR-0038)" note that the file carries.
- Dangling references found by the readers: ADR-0070 `tests/integration/web/_auth_helpers.py` (missing); ADR-0096 `terraform/bootstrap/terraform.tf` (actual `versions.tf`); ADR-0033:45 `just rotate-fallback-password` (no such recipe); ADR-0036 `terraform/cloud-init/compose/caddy/Dockerfile` (missing); ADR-0052 `tailwind.config.ts`, `static/css/app.css`, `static/css/fonts.css` (actual `tailwind.config.js`, `static/tailwind.src.css`, `static/fonts.css`); ADR-0106 and ADR-0081 name planned (not yet existing) tests, expected.

Verdict legend: **TRUE** still true; **TRUE+AMEND** still true but a later ADR amended/superseded part of it and the status line does not say so (the index does); **DRIFTED** a concrete claim is contradicted by code/config; **SUPERSEDE** should be marked superseded; **PROPOSED-LIVE** status says Proposed but the decision is implemented (or accepted per the plans).

**Verdict counts over 129 ADR files: TRUE 87, TRUE+AMEND 17, PROPOSED-LIVE 15, DRIFTED 5, SUPERSEDE 5.** (No ADR in the Accepted/Proposed set was found Rejected. ADR-0005 and ADR-0013 are already Superseded and correct.)

Depth: verdicts for 0001, 0003, 0004, 0006-0010, 0014, 0016, 0020, 0021, 0024, 0029, 0038-0040, 0042, 0043, 0046, 0048, 0049, 0058, 0062-0066, 0068-0077, 0085-0089, 0095, 0098, 0108, 0112-0117, 0119, 0120, 0122, 0123, 0126 rest on a presence check of the main artefact (file/column/workflow exists), not on verifying every decision clause. Treat "TRUE" there as "no contradiction found", not "proved".


### Notable ADR drift details (all re-checked by me unless marked)

- **ADR-0002** lines 15-16: "Tailwind CSS via CDN (no node toolchain)", "Plotly ... via CDN script". Actual: `package.json:7,16` (local Tailwind 3.4.14 build), `web/charts.py:3` (server-side SVG, ADR-0054). Only `pyproject.toml:136` (mypy override) and `:172` (pytest filterwarnings) still mention plotly.
- **ADR-0036**: custom `caddy-ratelimit` image "pinned by digest in `docker-compose.yml.tpl`". Actual `terraform/cloud-init/compose/docker-compose.yml.tpl:122` is `image: caddy:2.8`; the file's own header comment (line 4) repeats the false claim; `Caddyfile.tpl` has no `rate_limit` (V).
- **ADR-0052**: Tailwind v4 / `@theme` never landed (`package.json:16` pins 3.4.14; `static/tokens.css:1` still says "Tailwind v4: move into @theme") (V). Superseded by 0107, which is itself still Proposed, so the chain 0027, 0052, 0107 is the only way to learn the real state.
- **ADR-0057**: `CategoryArchivedError` and `services.recurring.create_rule` archive validation do not exist in `src/` (reader result; moderate confidence, validation may live elsewhere).
- **ADR-0023 / 0026 / 0028**: nav and FAB model replaced (Today/Ledger/Plan/Accounts, top-bar add); `fab_target_for` has no definition in `src/` (V).
- **ADR-0106 / 0107**: `docs/plans/ui-redesign/tasks.md:12` states "UI test harness exit gate done (T-UT12)" and "ADR-0107 Accepted", while both ADR files say Proposed, `docs/plans/ui-test-harness/tasks.md` shows T-UT02 and T-UT03 open and `tests/contract/` does not exist (V).
- **ADR-0110**: file says `Status: Accepted` and, one line below, `Superseded by: ADR-0111`.

### Proposed but live (15)

0032, 0033, 0034, 0035, 0037, 0050, 0051, 0054, 0056, 0061, 0078, 0118, 0127 (decision implemented, flip to Accepted); 0106, 0107 (accepted in the plans, implementation pending: needs an explicit status such as "Accepted, implementation pending"). 0053, 0055 and 0052 are implemented but superseded by the Proposed 0107, counted under SUPERSEDE.

### Full per-ADR verdict table

| ADR | Status line | Verdict | Evidence |
|---|---|---|---|
| 0001 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0002 | Accepted | DRIFTED | lines 15-16 (Tailwind CDN, Plotly via CDN) contradicted by package.json:7 and web/charts.py:3; FastAPI/HTMX/Jinja core still true |
| 0003 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0004 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0005 | Superseded by [ADR-0061](0061-v3-multi-user- | TRUE | Superseded by ADR-0061 correctly recorded (migrations/0012_multi_user.sql) |
| 0006 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0007 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0008 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0009 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0010 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0011 | Accepted | TRUE+AMEND | derived balance holds; amended by ADR-0125 but status line silent |
| 0012 | Accepted | TRUE+AMEND | amended by ADR-0038 (direct promotion), status silent; promoted_from_planned_id still at migrations/0012_multi_user.sql:166 |
| 0013 | Superseded by [ADR-0038](0038-recurring-stan | TRUE | file status 'Superseded by ADR-0038' correct; README index line 19 lacks the note |
| 0014 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0015 | Accepted | TRUE+AMEND | amended by 0042, 0043, 0087; status silent |
| 0016 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0017 | Accepted | TRUE+AMEND | stack matches .pre-commit-config.yaml; line 24 'CI runs the full suite' overtaken by ADR-0120 |
| 0018 | Accepted | TRUE+AMEND | single matrix row true (ci.yml:16); amended by ADR-0108 |
| 0019 | Accepted | TRUE+AMEND | audit_log/soft delete live (migrations/0002_core_schema.sql:222); amended by 0061, 0080, 0081, 0083, 0122 |
| 0020 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0021 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0022 | accepted (2026-10-23) | TRUE+AMEND | amended by 0061, 0081, 0122; status wording lower-case |
| 0023 | Accepted | DRIFTED | section 1 nav (Overview/Ledger/Accounts/Budget) contradicted by web/templates/partials/_nav.html:24-27 (Today/Ledger/Plan/Accounts); partly superseded by 0050, 0051, 0055; status silent |
| 0024 | accepted (2026-10-25) | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0025 | accepted (2026-10-25) | TRUE+AMEND | migrations/0005_user_preferences.sql live; F4.6 amended by 0031, 0039, 0041, 0085, 0105 |
| 0026 | Accepted | DRIFTED | FAB per surface via fab_target_for: symbol absent in src/; replaced by top_bar_add (templates/ledger/index.html:12); amended by 0056 |
| 0027 | Accepted | TRUE+AMEND | Tailwind 3.4.14 build, stylelint, tests/visual live; amended by 0052 (never landed), 0097, 0106, 0107, 0113, 0120 |
| 0028 | Accepted | TRUE | segmented tabs are plain links (ledger/index.html:19); cites fab_target_for and .segmented__btn that are stale |
| 0029 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0030 | accepted (2026-10-27) | TRUE+AMEND | amended by 0040, 0060 (section 4 superseded), 0062 |
| 0031 | accepted (2026-10-27) | TRUE+AMEND | amended by 0049, 0062; Budget page became Plan; README title differs from file title |
| 0032 | Proposed | PROPOSED-LIVE | Stardust1-S / pl-waw-2 live: terraform/modules/compute/variables.tf:11-14; amended by 0084, 0102, 0118 |
| 0033 | Proposed | PROPOSED-LIVE | WebAuthn + bcrypt live (pyproject.toml:21-23); single-user premise superseded by 0061; amended by 0065, 0067, 0070, 0072 |
| 0034 | Proposed | PROPOSED-LIVE | Litestream sidecar and retention match terraform/cloud-init/compose/litestream.yml.tpl:14-17 |
| 0035 | Proposed | PROPOSED-LIVE | terraform/ tree and bootstrap live; amended by 0088, 0090, 0091, 0096 |
| 0036 | Proposed | DRIFTED | custom xcaddy 'caddy-ratelimit' image pinned by digest: actual terraform/cloud-init/compose/docker-compose.yml.tpl:122 'image: caddy:2.8'; no rate_limit in Caddyfile.tpl (app-side per ADR-0072); compose line 4 comment also false |
| 0037 | Proposed | PROPOSED-LIVE | release.yml:14 has no SSH deploy job; ADR already says superseded in part by 0111 |
| 0038 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0039 | Accepted (amended by [ADR-0085](0085-budget- | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0040 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0041 | Accepted | TRUE+AMEND | amended by 0059, 0064; status line silent |
| 0042 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0043 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0045 | Accepted | SUPERSEDE | Decision superseded by ADR-0047; status plain Accepted |
| 0046 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0047 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0048 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0049 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0050 | Proposed | PROPOSED-LIVE | name 'Rising Dough' live (templates/base.html:10); visual direction superseded by 0107 |
| 0051 | Proposed | PROPOSED-LIVE | IA kept by 0107; nav and tabbar live (templates/base.html:37,60) |
| 0052 | Proposed | SUPERSEDE | v4 migration never landed (package.json:16 tailwindcss 3.4.14; static/tokens.css:1); superseded by 0107 which is itself Proposed |
| 0053 | Proposed | SUPERSEDE | macros implemented (templates/_partials/components/, 15 files) but 0107 supersedes; status Proposed |
| 0054 | Proposed | PROPOSED-LIVE | Plotly gone: web/charts.py:3; residual plotly entries pyproject.toml:136,172 |
| 0055 | Proposed | SUPERSEDE | rd-tabbar live (templates/base.html:60) but 0107 supersedes; status Proposed |
| 0056 | Proposed | PROPOSED-LIVE | add-entry overlay live (templates/partials/_add_entry_overlay.html); section 4 live formula preview has no caller (G-13) |
| 0057 | Accepted | DRIFTED | 'services.recurring.create_rule raises CategoryArchivedError': symbol absent from src/; text contradicts itself on archived_at vs deleted_at (no archived_at in migrations/) |
| 0058 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0059 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0060 | Accepted — 2026-10-29 | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0061 | Proposed | PROPOSED-LIVE | multi-user live: migrations/0012_multi_user.sql, routers/settings_users.py; basis of 0068-0076 |
| 0062 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0063 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0064 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0065 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0066 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0067 | Accepted | TRUE+AMEND | amended by 0076; code matches (routers/auth.py, services/auth.py) |
| 0068 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0069 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0070 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0071 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0072 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0073 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0074 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0075 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0076 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0077 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0078 | Proposed | PROPOSED-LIVE | age-encrypted Litestream live (terraform/cloud-init/compose/litestream-entrypoint.sh), retention.py exists; amended by 0093, 0112, 0114 |
| 0079 | Proposed | TRUE | v4 not built (no src/budget_planner/crypto/); Proposed is accurate |
| 0080 | Proposed | TRUE | v4 not built; Proposed accurate (0081 cites future tests/perf/ and just ci-perf) |
| 0081 | Proposed | TRUE | v4 not built; Proposed accurate (0081 cites future tests/perf/ and just ci-perf) |
| 0082 | Proposed | TRUE | v4 not built; Proposed accurate (0081 cites future tests/perf/ and just ci-perf) |
| 0083 | Proposed | TRUE | v4 not built; Proposed accurate (0081 cites future tests/perf/ and just ci-perf) |
| 0084 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0085 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0086 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0087 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0088 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0089 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0090 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0091 | Accepted (shared-project assumption supersed | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0092 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0093 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0094 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0095 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0096 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0097 | Accepted (amended 2026-11-18, see the Amendm | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0098 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0099 | Accepted; required merge checks amended by [ | TRUE+AMEND | amended by 0109, 0110, 0111, 0115, 0121; status lists only 0121 |
| 0100 | Accepted | TRUE+AMEND | amended by 0104, 0105 (ci-principals); status silent |
| 0101 | Accepted | TRUE+AMEND | amended by 0116; status silent |
| 0102 | Accepted | TRUE+AMEND | Dockerfile:9,43 python:3.12-slim-trixie; amended by 0103 |
| 0103 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0104 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0105a | Accepted | TRUE | terraform/modules/bucket_policy/variables.tf:39; DUPLICATE NUMBER |
| 0105b | Accepted | TRUE | overdue handling in web/today_data.py; DUPLICATE NUMBER |
| 0106 | Proposed | PROPOSED-LIVE | harness partly built: tests/contract/ absent, ui-test-harness/tasks.md T-UT02/03 open, yet ui-redesign/tasks.md:12 says T-UT12 done |
| 0107 | Proposed | PROPOSED-LIVE | ui-redesign/tasks.md:12 says 'ADR-0107 Accepted'; implementation not started (Tailwind 3 build, old templates live) |
| 0108 | Accepted (2026-11-18, T-CS06; results in `do | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0109 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0110 | Accepted | SUPERSEDE | file line 4 says 'Superseded by ADR-0111' but line 3 says Status: Accepted |
| 0111 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0112 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0113 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0114 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0115 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0116 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0117 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0118 | Proposed | PROPOSED-LIVE | root_volume_type default l_ssd: terraform/modules/compute/variables.tf:253-256 |
| 0119 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0120 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0121a | Accepted | TRUE | drill-gate-skip.yml + scripts/ci/drill_gate_skip.py exist; DUPLICATE NUMBER |
| 0121b | Accepted | TRUE | path-filtered workflows rule (helper: not deeply verified); DUPLICATE NUMBER |
| 0122 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0123 | Accepted | TRUE | main claim verified or no contradiction found (helper spot-check) |
| 0124 | Accepted | TRUE | decision only; goals/starter code not started (docs/plans/gamification/README.md:8) |
| 0125 | Accepted | TRUE | decision only; goals/starter code not started (docs/plans/gamification/README.md:8) |
| 0126 | Accepted | TRUE | docs/plans/gamification/ exists |
| 0127 | Proposed | PROPOSED-LIVE | drain step live: .github/workflows/terraform.yml:462-464; CHANGELOG 2026-11-19 shows rehearsal green |
| 0128 | Accepted | TRUE | decision only; goals/starter code not started (docs/plans/gamification/README.md:8) |

## 4. Doc drift

### 4.1 CHANGELOG vs `tasks.md` ✅ status

Scripted over `docs/plans/*/tasks.md` (heading id vs `docs/CHANGELOG.md`).

| Plan | ✅ tasks | ✅ but no CHANGELOG entry | Open (◻/plain) but CHANGELOG says done |
|---|---|---|---|
| v1 | 96 | T-080, T-082, T-083, T-084, T-085, T-097, T-098, T-099, T-100 | T-108 (`CHANGELOG.md:1025` "T-108 ... rewritten"), T-126 (forecast overlay shipped, `CHANGELOG.md:1009`; `services/forecast.py:9-11` implements it, ADR-0042 Accepted), T-109 |
| v2 | 13 | none | 60 of 73 tasks are ◻ although the Rising Dough v2 UI is live; e.g. T-R71, T-R72, T-R73 are resolved by Accepted ADR-0057, 0058, 0059 |
| v3 | 160 | T-D21, T-D22 | T-D147 (`CHANGELOG.md` "CI(T-D147)", body records PR #30 skip working), T-D143 (`CHANGELOG.md` T-D143 heading; ADR-0118 default is `l_ssd`, `terraform/modules/compute/variables.tf:256`; body says "blocked on T-D156", which is done) |
| ci-speed | 9 | T-CS03 | none |
| quality-audit | T-Q01, T-Q02 | T-Q01, T-Q02 (expected, audit commits docs only) | T-Q18 mentioned in CHANGELOG while open (planning entry) |
| v4, gamification, ui-redesign | 0 | n/a | all ◻, consistent with "not started" |
| ui-test-harness | 1 | none | T-UT12 reported done by `ui-redesign/tasks.md:12` but T-UT02, T-UT03 are ◻ here |

T-D102, T-D104, T-D105, T-D108 are open by design ("won't do"/"deferred"); their ids appear in the CHANGELOG as decisions. v2's `tasks.md` header says tasks get a ✅ only after the visual-audit sweep, so either the v2 plan was never closed out or its 60 ◻ rows are stale after the ADR-0107 redesign took over.

### 4.2 `requirements.md` vs implemented behaviour

Section 3 (non-functional and UI) is stale in several places; sections 6-12 were spot-checked and found consistent with ADR status (sections 7, 12 correctly say not started).

| Line | Claim | Reality |
|---|---|---|
| `requirements.md:109` | "Plotly for charts." | removed (ADR-0054); `web/charts.py:3` |
| `:156-157` | CI "Setup steps: `actions/setup-python@v5` + `actions/setup-node@v4`" | `ci.yml:29-36` uses `uv python install 3.12` and `actions/setup-node` pinned by SHA (v4.4.0); no setup-python |
| `:136-147` (3.5 command list) | lists `dev`, `css`, `test`, `lint`, `format`, `typecheck`, `ci`, `db-reset`, `seed` | `justfile` also has `dev-demo`, `demo-build`, `lint-changed`, `test-changed`, `test-fast`, `worktree-init`, `prod-db-seed`, `docker-build`, `security-scan`, `test-prod-stack`, `tf-*`, `drill-preflight`; none documented here |
| `:171` | "Four top-level nav items ... Overview, Ledger, Accounts, Budget" | `partials/_nav.html:24-27`: Today, Ledger, Plan, Accounts (Settings in the footer) |
| `:180` | overlay stack managed by `static/js/overlay-stack.js` | file does not exist (`static/js/` has 19 files, none named so; `settings/_drawer.html:6` still mentions it) |
| `:174`, `:177` | Quick-add FAB, `g o`/`g l`/`g a`/`g b` shortcuts, `/settings?tab=categories\|fx\|prefs` | FAB replaced by top-bar add (see ADR-0026 row); `_nav.html` uses `g p` for Plan; tabs exist |

### 4.3 CLAUDE.md vs `justfile`

| CLAUDE.md claim | Reality |
|---|---|
| `just dev` with `--db=<path>` | exists (`justfile:31-47`); only `--db=` accepted, other args exit 2 |
| `just dev-demo` | exists (`justfile:50`), runs `just dev --db=data/demo.sqlite` |
| `just demo-build` | exists (`justfile:55`) but is not mentioned in the "Developer commands" block, only in the Databases table |
| `just lint-changed main`, `just test-changed main` | exist with a `BASE` parameter (`justfile:117`, `:132`); positional `main` works |
| `just worktree-init` | exists (`justfile:176`) |
| `just test` "fails under 90%" | `pyproject.toml:154` `--cov-fail-under=90` |
| `just lint` = ruff + sqlfluff + djlint | also runs `npm run stylelint` (`justfile:97`); and does **not** run `ruff format --check` (see G-05) |
| `just ci` "everything CI runs" | `justfile:116` `ci: lint typecheck test`; the pre-commit-only checks are not in it (G-05) |
| Stack: "Tailwind (CDN), Plotly" | local Tailwind build (ADR-0027), no Plotly (ADR-0054) |
| Change policy and handoff checklist: `docs/tasks.md`, `docs/implementation_plan.md` | neither file exists at `docs/`; tasks live in `docs/plans/<plan>/tasks.md` (V) |
| "`PYTEST_WORKERS=2` ... `0` runs serially" | consistent with `justfile:112-114` |
| "Server binds to 127.0.0.1 only in v1" | still enforced for the container-local bind (`config.py:159-166`) but the comment cites superseded ADR-0005 |
| `justfile:23` "Binds 127.0.0.1 per ADR-0005" | ADR-0005 is Superseded by ADR-0061 (also `config.py:49,162,166`, `web/templating.py:183`) |

### 4.4 Skills under `.claude/skills/`

- `orchestrator-mode/SKILL.md:62-63` references `docs/requirements.md`, `docs/tasks.md` and `docs/implementation_plan.md`; the last two do not exist (same stale path as CLAUDE.md). Commands it uses (`just lint-changed`, `test-changed`, `worktree-init`, `db-reset`, `migrate`, `seed`) all exist. ADR references (0066, 0097, 0108, 0120) are current.
- `frontend-visual-audit/SKILL.md:193` references `.claude/plans/todo/frontend-visual-fixes.md`; the file exists. The skill is generic (no project route list, no mention of `--db=`), so it does not carry the stale paths; `CLAUDE.md` requires the 1440/1024/375 sweep and the skill's defaults match.

### 4.5 Stale code comments

`justfile:23`, `config.py:49,162,166`, `web/templating.py:183` cite ADR-0005 (superseded). `web/routers/today.py:174`, `services/balance.py:206`, `routers/analytics.py:8` promise a "Phase 7" cleanup that has not happened. `docker-compose.yml.tpl:4` cites a custom caddy build that does not exist.

## 5. Config parity: pre-commit vs `just ci` vs GitHub Actions

PR CI is `ci.yml` -> `just ci` (`lint typecheck test`). `security.yml` runs pip-audit/trivy; `terraform.yml` runs terraform checks and tflint. Pre-commit is the local gate (ADR-0120).

| Check | pre-commit | `just ci` / `ci.yml` | Other workflow | Parity |
|---|---|---|---|---|
| ruff check | yes, `--fix`, rev v0.17.2 (`.pre-commit-config.yaml:23`) | yes (`justfile:93`), lock 0.17.2 | | same version, but pre-commit auto-fixes |
| ruff format | yes (`:26`) | **no** (`just lint` has only `ruff check`; `ruff format` only in `just format`) | | **gap** |
| mypy | yes, v2.4.0, whole repo, deps from `additional_dependencies` (ranges, `cryptography<49`) | yes (`justfile:106`), env from `uv.lock` (mypy 2.4.0, cryptography 50.0.2, pandas-stubs 3.0.5, ...) | | same mypy version, **different dependency set** (hook env is floating ranges, CI env is the lock) |
| sqlfluff | yes, **rev 3.1.1** | yes, lock **4.4.0** | | **version drift** |
| djlint | yes, **rev v1.35.2** | yes, lock **1.47.0** | | **version drift** |
| bandit | yes, **rev 1.7.10** | **no** | none | **not in CI**; lock has 1.9.4 |
| detect-secrets | yes, v1.5.0 | **no** | none | **not in CI** (lock 1.5.0) |
| stylelint | yes (`files` only `static/*.css`) | yes (`npm run stylelint`) | | same tool; pre-commit excludes `tailwind.css` |
| tailwind-check (generated CSS equals committed) | yes (`scripts/pre-commit/tailwind_check.sh`) | CI runs `npm run css` (`ci.yml:51`) but never diffs the result | | **gap**: CI builds and discards |
| hygiene hooks (trailing whitespace, EOF, check-yaml/toml, large files, merge-conflict, line endings) | yes (pre-commit-hooks v4.6.0) | no | | gap (low impact) |
| pytest | testmon-selected subset (`just test-fast`) | full suite, `--cov-fail-under=90`, xdist `auto` | | intentional (ADR-0120) |
| pip-audit | no | no | `security.yml:` pip-audit job | CI-only, consistent with ADR |
| trivy | no | no | `security.yml` | CI-only |
| terraform fmt/validate/tflint | no | no | `terraform.yml`; tflint pinned v0.53.0 (`terraform.yml:145`) | CI-only |
| Python / Node / just / uv | `default_language_version python3.12` | Python 3.12 via `uv python install`, Node 20, just **1.34.0**, uv **"latest"** (`ci.yml:26`) | | local `just`/`uv` unpinned; CI uv unpinned |

`httpx2>=0.1` in the dev group (`pyproject.toml:44`) is not imported anywhere in `src/` or `tests/` or `scripts/` (V).

## 6. Findings

Schema per plan section 4. IDs are track-local (`G-nn`).

### G-01 Live FX fetch can never succeed: `httpx.Client` is built without `base_url`; `fx_api_url` setting is dead

- **Severity**: Critical (wrong money shown for non-base-currency accounts; impact depends on prod having such accounts, see Q1). **Confidence**: Confirmed (repro). **Track / root cause**: G / `dead-code` (dead config masking `silent-fallback`; hand off to Track C).
- **Location(s)**: `config.py:70` (`fx_api_url`, never read); `services/fx.py:55` (`http.get(f"/{on_date.isoformat()}", ...)`, a relative URL); clients built without `base_url` at `web/today_data.py:124`, `web/routers/forecast.py:49`, `services/forecast.py:950`; swallowed at `services/fx.py:109` (`except (httpx.HTTPError, ...)`); degrade-to-1 at `web/today_data.py:128-129`.
- **Description**: `fx._fetch_remote` expects a client with the Frankfurter base URL, but no production code sets one. httpx raises `UnsupportedProtocol`, a subclass of `httpx.HTTPError`, which `get_rate` catches and turns into the stale-cache fallback. `fx_repo.upsert_rate` is called only from `get_rate` (`services/fx.py:112`), so the `fx_rates` cache is never filled by the app. Cache-only readers (`fx.convert_cached`, used by `services/budget.py:80,111`, `web/routers/ledger.py:275`, `services/ledger_totals.py`) therefore see only rows that arrived some other way, and otherwise degrade to native amounts (`budget.py:82` "committed uses native amount") or rate 1 (`today_data.py:129`). Unit tests construct the client with `base_url=` (`tests/unit/services/test_forecast_monthly.py:43`), which hides this. vulture flagged `fx_api_url` as unused; the flag was the clue. Violates ADR-0006 (historical FX cached from Frankfurter) and ADR-0095.
- **Evidence**: `repro/G/fx_client_no_base_url.py` prints `httpx.UnsupportedProtocol`, `caught by get_rate's except httpx.HTTPError: True`, "Request URL is missing an 'http://' or 'https://' protocol." (`.out` file recorded).
- **Impact**: cross-currency totals (Today fortune/balances, Budget committed, forecast) use stale cached rates, native amounts or rate 1 instead of the real rate; a EUR account can be added 1:1 to PLN.
- **Mitigation**: build one FX client factory in `services/fx.py` (`httpx.Client(base_url=settings.fx_api_url, timeout=...)`) and use it at all three sites; add an integration test that fails if a client without `base_url` reaches `_fetch_remote` and a test that asserts `fx_api_url` is read.
- **Alternatives**: make `_fetch_remote` build an absolute URL from `settings.fx_api_url` (also removes the footgun at the call sites; changes the function signature).
- **Effort**: S. **Related**: ADR-0006, ADR-0095, Track C silent-fallback, Q1.

### G-02 Fifteen ADRs say Proposed but are implemented or accepted in the plans

- **Severity**: Medium. **Confidence**: Confirmed. **Class**: `doc-drift`.
- **Location(s)**: `docs/adr/` 0032, 0033, 0034, 0035, 0037, 0050, 0051, 0054, 0056, 0061, 0078, 0106, 0107, 0118, 0127 (status line, line 3); evidence in section 3 table.
- **Description**: the status field no longer separates decisions in force from open ones; ADR-0061 and ADR-0078 are the basis of Accepted ADRs 0068-0076, 0122. ADR-0107 and ADR-0106 are "Accepted" in `docs/plans/ui-redesign/tasks.md:12`.
- **Impact**: an agent or reviewer cannot tell what binds (CLAUDE.md says "read the relevant ADR before changing an area").
- **Mitigation**: one docs-first PR flips the 13 implemented ADRs to Accepted and sets 0106/0107 to "Accepted, implementation pending"; add a check in `tests/architecture/` that `Proposed` ADRs are not referenced as binding by an Accepted one.
- **Effort**: S. **Related**: G-03, G-04.

### G-03 Amendments and supersessions live only in the README index, not on ADR status lines

- **Severity**: Medium. **Confidence**: Confirmed. **Class**: `doc-drift`.
- **Location(s)**: status lines of 0002, 0011, 0012, 0015, 0017, 0018, 0019, 0022, 0023, 0025, 0026, 0027, 0030, 0031, 0041, 0045, 0067, 0099, 0100, 0101, 0102, 0110 (see table, TRUE+AMEND/SUPERSEDE rows); README line 19 (0013).
- **Description**: a reader of the ADR file sees "Accepted" for decisions that were partly overturned (0045 Decision superseded by 0047; 0052/0053/0055 superseded by 0107; 0110 superseded by 0111 and says so one line below its own "Accepted").
- **Impact**: wrong decisions followed; Track E/redesign work can cite a dead ADR.
- **Mitigation**: add a status-line convention `Accepted (amended by ADR-N ...)` and a generator or architecture test that derives amendments from README rows and fails on a mismatch.
- **Effort**: M (22 files, mechanical). **Related**: G-02.

### G-04 ADR numbering and index hygiene

- **Severity**: Low. **Confidence**: Confirmed. **Class**: `doc-drift`.
- **Location(s)**: duplicate 0105 and 0121 (two files each); gap 0044; README rows out of order (0099/0100, 0112/0113, 0127/0128); 21 index-vs-file title mismatches; 3 broken links (`0091-...` to `0032-v3-hosting-scaleway-poland.md`, `0034-v3-backups-litestream-to-object-storage.md`; `0092-...` to the same 0034 name); README line 19.
- **Mitigation**: do not renumber the duplicates (references would break); add a `tests/architecture/test_adr_index.py` (unique numbers except the two grandfathered pairs, index sorted, links resolve) and rename the new Mutmut ADR to the next free number (0129 or later). Fix the three links.
- **Effort**: S.

### G-05 `just ci` / PR CI omits checks that pre-commit enforces: ruff format, bandit, detect-secrets, tailwind-check

- **Severity**: Medium. **Confidence**: Confirmed. **Class**: `config-drift`.
- **Location(s)**: `justfile:92-98` (lint without `ruff format --check`), `:116`; `.pre-commit-config.yaml:26,76-83,125-131`; `.github/workflows/ci.yml:51,68`.
- **Description**: bandit, detect-secrets, formatting and the committed-tailwind check run only in a local hook. `git commit --no-verify`, a commit from a machine without the hooks installed, or an automation (GitHub UI edit, Dependabot) bypasses them and PR CI is green. `ci.yml:51` builds the Tailwind CSS but does not compare it to the committed file.
- **Impact**: format/bandit/secret regressions and stale `tailwind.css` can reach `main` and prod.
- **Mitigation**: add a single `just precommit-all` (or `pre-commit run --all-files` with `SKIP=pytest-fast`) step to `ci.yml` so the hook config is the one source for both; keep the pytest hook skipped there. This also removes the version drift in G-06 as a side effect.
- **Alternatives**: add bandit, detect-secrets, `ruff format --check` and a `git diff --exit-code` after `npm run css` as separate `just lint` lines (more duplication, ADR-0117 favours one source).
- **Effort**: S. **Related**: ADR-0017, ADR-0120, G-06.

### G-06 Tool version drift between pre-commit pins, `uv.lock` and CI

- **Severity**: Medium. **Confidence**: Confirmed. **Class**: `config-drift`.
- **Location(s)**: `.pre-commit-config.yaml:58` sqlfluff 3.1.1 vs `uv.lock` 4.4.0; `:70` djlint v1.35.2 vs 1.47.0; `:78` bandit 1.7.10 vs 1.9.4; mypy hook `additional_dependencies` lines 33-56 are unpinned ranges (and `cryptography<49` vs lock 50.0.2 on Linux) while `just typecheck` uses the lock; `ci.yml:26` uv `"latest"`, `:42` just 1.34.0 vs unpinned local.
- **Description**: `just lint` (CI) runs sqlfluff 4.4.0 and djlint 1.47.0; the local hook runs 3.1.1 and 1.35.2, so a file can pass one and fail the other. The mypy hook can resolve different stubs than CI.
- **Impact**: "green locally, red in CI" (or the reverse) on SQL and templates; mypy results can differ.
- **Mitigation**: run the hooks as `repo: local`, `language: system`, `entry: uv run <tool>` so every linter uses the lock (as `pytest-fast`, `stylelint` already do), pin `uv` in `ci.yml`, and drop the hook-side `rev` pins.
- **Alternatives**: keep remote hooks and add a test that asserts hook revs equal `uv.lock` versions.
- **Effort**: S. **Related**: G-05.

### G-07 Unused dev dependency `httpx2` and stale plotly leftovers

- **Severity**: Low. **Confidence**: Confirmed. **Class**: `dead-code` / `dependency`.
- **Location(s)**: `pyproject.toml:44` `httpx2>=0.1` (locked 2.16.0, `uv.lock:739-746`, no import in `src/`, `tests/`, `scripts/`); `pyproject.toml:136` (mypy override for `plotly.*`), `:172` (pytest filterwarnings for `plotly.*`).
- **Mitigation**: remove `httpx2`, and both plotly entries (and the `pandas.*`/`pyarrow.*` override only if no longer needed). Check provenance of `httpx2` first (Q2).
- **Effort**: S.

### G-08 CLAUDE.md and the orchestrator skill point at files that do not exist

- **Severity**: Medium. **Confidence**: Confirmed. **Class**: `doc-drift`.
- **Location(s)**: `CLAUDE.md` change-policy item 1 and handoff checklist (`docs/tasks.md`, `docs/implementation_plan.md`) and Stack line ("Tailwind (CDN), Plotly"); `.claude/skills/orchestrator-mode/SKILL.md:62-63`.
- **Description**: the mandatory "docs first" procedure names two top-level plan files that were replaced by per-plan `docs/plans/<plan>/tasks.md` and `implementation_plan.md`; an agent following it literally cannot comply or invents the files. The stack line is two ADRs old.
- **Mitigation**: edit CLAUDE.md and the skill to name `docs/plans/<plan>/{tasks,implementation_plan}.md`, fix the Stack line (local Tailwind build, server-rendered SVG), add `demo-build`, `test-fast`, `set-password` to the command list.
- **Effort**: S. **Related**: G-09.

### G-09 `requirements.md` section 3 contradicts the code

- **Severity**: Medium. **Confidence**: Confirmed. **Class**: `doc-drift`.
- **Location(s)**: `docs/requirements.md:109` (Plotly), `:156-157` (setup-python@v5, setup-node@v4), `:136-147` (recipe list), `:171` (nav), `:174,177,180` (FAB, `g b`, `overlay-stack.js`).
- **Description**: see table 4.2. The "canonical" requirements document disagrees with the shipped UI and CI.
- **Mitigation**: update section 3.1, 3.5, 3.6, 3.9 in one docs-first change; section 3.9 should be replaced by a pointer to the ADR-0051/0077 nav until the ADR-0107 redesign lands.
- **Effort**: S.

### G-10 Task status in `tasks.md` disagrees with CHANGELOG and ADRs

- **Severity**: Medium. **Confidence**: Confirmed. **Class**: `doc-drift`.
- **Location(s)**: `docs/plans/v1/tasks.md:515` (T-108), `:519` (T-109), `:670` (T-126); `docs/plans/v3/tasks.md:920` (T-D143), `:952` (T-D147); `docs/plans/v2/tasks.md` (60 rows ◻, e.g. T-R71 to T-R73); `docs/plans/ui-redesign/tasks.md:12` vs `docs/plans/ui-test-harness/tasks.md:19,28`; 9 v1 tasks, T-D21, T-D22, T-CS03 with ✅ and no CHANGELOG line.
- **Impact**: CLAUDE.md's handoff checklist treats the ✅ prefix and CHANGELOG as the record; the redesign plan's entry gate (T-UR00) rests on a harness gate that the harness plan says is not done.
- **Mitigation**: reconcile the listed rows once; add an architecture test that every `### ✅ T-*` id appears in the CHANGELOG and every id named as done in the CHANGELOG heading has ✅.
- **Effort**: M.

### G-11 Legacy redirects and aliases kept past their stated expiry

- **Severity**: Low. **Confidence**: Confirmed. **Class**: `dead-code`.
- **Location(s)**: `web/routers/analytics.py` (whole module), `routers/budget.py:306`, `routers/categories.py:22`, `routers/planned.py:55`, `routers/recurring.py:58`, `routers/transactions.py:113`, `routers/plan.py:284`, `routers/today.py:175`, `web/templates/partials/_nav.html:26,31` (`extra_paths`); fragments `partials/_direction_badge.html` etc. see 2.2.
- **Description**: "kept at 302 for one release per ADR-0023" (T-070) and "Phase 7 cleanup drops this"; v2, v3 and the Phase-7 label have all passed. Mitigation caveat: bookmarks of a single user; routes still exercised by tests.
- **Mitigation**: one cleanup task removing the redirects, `routers/analytics.py`, the `/afford` and `/budget-legacy` aliases and updating `_ROUTER_NAMES` (`web/app.py:215-232`) and `extra_paths`.
- **Effort**: S.

### G-12 Orphan templates and a duplicated partial tree

- **Severity**: Low. **Confidence**: Confirmed (grep, section 2.2). **Class**: `dead-code`.
- **Location(s)**: 13 files listed in 2.2 (`_partials/components/_period_header.html`, `_table_row.html`, `budget/manage.html`, `categories/index.html`, `planned/index.html`, `recurring/index.html`, `transactions/index.html`, `partials/_cheatsheet.html`, `_direction_badge.html`, `_money.html`, `_pagination.html`, `partials/accounts/_fortune_split.html`, `_totals.html`). Markup is out of scope per ADR-0107; recorded only because the ADR-0107 migration should not port them.
- **Mitigation**: delete in the redesign cleanup; add `tests/architecture/test_templates_referenced.py` (every template is rendered, included or imported, with an allowlist for string-built includes).
- **Effort**: S.

### G-13 Routes with no caller; ADR-0056 live formula preview is unreachable

- **Severity**: Medium (one user-visible feature missing), the rest Low. **Confidence**: Confirmed (grep of all callers). **Class**: `dead-code`.
- **Location(s)**: `routers/recurring.py:546` (formula preview), `:424` (batch promote-due), `routers/accounts.py:133`, `routers/budget.py:347`, `routers/plan.py:254`; see 2.4.
- **Description**: the formula preview endpoint, its template `partials/recurring/_formula_preview.html` and the ADR-0056 section 4 behaviour are only exercised by tests; the unified entry form (ADR-0060) no longer calls it. Each dead route is also a user-scoped surface that Track D must still cover.
- **Mitigation**: decide per route: re-wire the preview in the entry form (or in the ADR-0107 redesign) or delete route, template and tests; delete the other four.
- **Effort**: S per route, M for the preview re-wire.

### G-14 `_register_routers` silently skips a router whose import fails

- **Severity**: Medium. **Confidence**: Confirmed (code). **Class**: `dead-code` / `silent-fallback`.
- **Location(s)**: `web/app.py:236-247` (`except ImportError: continue  # pragma: no cover`).
- **Description**: the docstring says "missing modules (during iterative landing) are tolerated". Today every module exists, so the guard only matters when a router (or something it imports) is broken: the app then starts without that router's routes (a missing auth router would start without login). The `pragma: no cover` hides it from the coverage gate.
- **Mitigation**: replace the loop by explicit imports and `include_router` calls (no `importlib`, no `try`).
- **Effort**: S.

### G-15 Stale comments: superseded ADR-0005 and elapsed "Phase 7" promises

- **Severity**: Low. **Confidence**: Confirmed. **Class**: `doc-drift`.
- **Location(s)**: `justfile:23`, `config.py:49,162,166`, `web/templating.py:183`, `web/routers/today.py:174`, `services/balance.py:206`, `web/routers/analytics.py:8`, `terraform/cloud-init/compose/docker-compose.yml.tpl:4`.
- **Mitigation**: update the comments to cite ADR-0061 / ADR-0036 (accurate), delete the Phase-7 promises or open tasks.
- **Effort**: S.

### G-16 ADR bodies contradicted by code (DRIFTED set)

- **Severity**: Medium. **Confidence**: Confirmed for 0002, 0023, 0026, 0036, 0052 (V); Probable for 0057. **Class**: `doc-drift`.
- **Location(s)**: ADR-0002 lines 15-16; ADR-0023 section 1; ADR-0026 and ADR-0028 (`fab_target_for`); ADR-0036 lines 68, 108-109 vs `docker-compose.yml.tpl:122`; ADR-0052 lines 17-18 vs `package.json:16`; ADR-0057 line 24.
- **Mitigation**: edit each status line to the true state (partly superseded by N); ADR-0036 needs an amendment ADR or a dated addendum explaining stock `caddy:2.8` and app-side rate limiting (ADR-0072). ADR-0057 needs either the validation implemented or the text corrected.
- **Effort**: M.

### G-17 Dead symbols kept alive only by tests

- **Severity**: Low. **Confidence**: Confirmed (grep). **Class**: `dead-code`.
- **Location(s)**: `repositories/rate_limit.py:36 get_count`, `web/htmx.py:13 is_htmx` (duplicate of `web/errors.py:30`), `web/htmx.py:31 trigger_from_iterable`, `web/rendering.py:51 render_str`, `domain/accounts.py:97 last_activity_date`, `config.py:52 bind_port`, `web/charts.py:414-415 bar_height/value_label`, `services/planned.py:37 PlannedKind`.
- **Mitigation**: delete them and their tests (or move test-only helpers under `tests/`); add a vulture whitelist file and run `vulture` in `just lint` at 80% confidence.
- **Effort**: S.

**Counts (17 findings)**: Critical 1 (G-01), High 0, Medium 10 (G-02, G-03, G-05, G-06, G-08, G-09, G-10, G-13, G-14, G-16), Low 6 (G-04, G-07, G-11, G-12, G-15, G-17).

## 7. Questions for the operator

1. **G-01**: does prod hold any account whose currency differs from `base_currency`, and does the prod `fx_rates` table have rows? (Not queried: `data/budget.sqlite` and the prod host are hands-off. A read-only count run by the operator on a copy would settle impact.) Until then, treat the Critical rating as "confirmed mechanism, impact unproven".
2. `httpx2` in the dev group: what is it for, and who added it? It is imported nowhere and is not the well-known `httpx`; check provenance before the next `uv sync`.
3. `FastAPI` docs routes `/docs` and `/openapi.json` are registered (`/openapi.json`, `/docs`, `/docs/oauth2-redirect` in the app route table); is that intended in prod (Track D)?
4. Is the v2 plan (`docs/plans/v2/tasks.md`, 60 rows open) to be closed as superseded by ADR-0107, or are any rows real remaining work?
5. Should CI run `pre-commit run --all-files` (G-05/G-06 mitigation) or is "pre-commit is the local gate" (ADR-0120) meant to exclude bandit and detect-secrets from CI on purpose?
6. ADR-0107 and ADR-0106: are they Accepted (plans say so) or still Proposed (files say so)? A decision is needed before G-02 is closed.
7. Can the two duplicate ADR numbers (0105, 0121) stay grandfathered with a test, or should references be disambiguated?

## 8. Next-step hints (not findings)

- A `vulture` whitelist plus a templates-referenced architecture test would make section 2 repeatable.
- Track C should pick up G-01 and re-run the FX differential test (Track A) against a client with the real base URL.
