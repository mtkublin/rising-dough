# Sourdough Redesign — Tasks

> **After the redesign, `tests/architecture/allowlists/template_logic.toml` must be empty (burned to zero, ADR-0130 amendment 2026-11-21); new templates add no entries.** Remediation T-Q237 and T-Q273 only burn down templates that survive the redesign; every other entry is deleted by this plan (surface tasks flip `removal.md` rows to `deleted` and delete the matching `template_logic.toml` entries; T-UR15 is not done while the file has an entry).

> **Transfer note (T-Q273, 2026-11-22): `template_logic.toml` holds 83 entries over 51 old templates; none survives, so remediation burned none.** Each surface task deletes the entries of the templates it removes (rule counts are one per expression; the new templates must not reproduce them: compute in the view model, use the `money` / `money_num` / `pct` / named date filters, no `{% set %}`, no literal currency codes, no `|float`).
> | Owner | Entries (templates) |
> |---|---|
> | T-UR04 (shared) | `_partials/combobox`, `_partials/segmented`, `_partials/components/{_amount,_button,_direction_badge,_heatmap_cell,_pace_tag,_period_header,_pill,_planned_net,_progress_bar,_segmented,_sparkline,_top_bar_add}`, `partials/{_flash,_nav,_pagination,_tabbar}`, `partials/transactions/{_form,_table}` |
> | T-UR06 | `errors/{404,409,422,500}` |
> | T-UR08 | `accounts/index`, `partials/accounts/{_card,_reconcile_modal,_row,_snapshot_item}` |
> | T-UR09, T-UR10 | `ledger/{index,_table,_recently_deleted}`, `partials/planned/{_form,_promote_inline_row,_row}`, `partials/recurring/{_form,_override_form,_promote_inline_row,_row}`, `recurring/index` |
> | T-UR13 | `partials/categories/_form`, `settings/{_drawer,_fx,_tabs,index}` |
> | T-UR14 | `settings/{_password_form,security}`, `settings/users/{_password-toast,_row,list}` |
> | T-UR15 | `dev/components` (3 currency literals; port from the handoff) |

> Plan: [README.md](README.md). Decision: [ADR-0107](../../adr/0107-sourdough-redesign-from-designer-handoff.md). Handoff: `docs/design/rising-dough-frontend/` (its `README.md` is required reading for every task).
> Legend: `[P]` parallel-safe within its phase, `[S]` sequential, `→ T-URxx` depends on upstream task.
> Every Phase 2 task follows the per-surface loop and definition of done in [README.md](README.md#per-surface-loop-test-first), including the visual diff at the strict default tolerance (0.1%, `MAX_DIFF_PIXEL_RATIO`, plus the cluster cap `MAX_DIFF_CLUSTER_PX`, ADR-0147 §2) unless `derived.md` records an operator-signed exception (T-UR00b).

---

## Phase P — Backend preconditions (own PR and release, before Phase 0)

> **Decision**: [ADR-0148](../../adr/0148-redesign-backend-preconditions-released-first.md). Everything backend that can ship before the migration ships first: schema, repositories, services, ports, config switches, service guards and the fields the handoff needs. No templates, CSS, JS or new page-rendering routes; existing routes change only the service call and the error shown through the existing flash. One PR to `main` from `ui/preconditions`, released through the ADR-0099 pipeline; Phase 0 starts after the release is live. Contract tests for the changed behaviour change here (requirements already amended), so the migration starts from that baseline.

### ✅ T-UR29 [P] User edit guards (server side of T-UR20)
- `services/users.edit_user` refuses an actor demoting themselves (today allowed while a second admin exists) and demoting the last admin; an email different from the stored one is refused with a validation error (422 on the route, nothing saved; operator 2026-11-22). Delete keeps refusing self and last admin.
- Tests assert the stored row, the audit row and that a second user's rows are untouched; HTTP tests on the existing edit route assert the flashed refusal and unchanged DB state.
- ADR-0134 §11, ADR-0073, requirements §10.1 (user admin line), §6.2.

### ✅ T-UR30 [P] Invite data layer (data part of T-UR20)
- Migration `0019_invites.sql` (+ `down/`): invites (email, role, inviting admin, token hash, created / expires / used / revoked timestamps, soft delete + audit via repository helpers). Repository, user-scoped where it applies.
- Lifetime 7 days from create or resend (named constant). Service: create (refuses an email that already has a live user or a pending invite), resend (new token and new expiry, old token dead; refused on a revoked or used invite), revoke (final: a revoked invite cannot be resent, the admin creates a new one), accept (creates the user with the invite's email and role, marks the invite used, one `db_transaction`), link state (`pending`, `expired`, `used`, `invalid`). Token stored hashed, compared in constant time, never logged.
- No routes, no templates. Migration rehearsal on a scratch copy (never `data/budget.sqlite`).
- ADR-0134 §1, §10, ADR-0019, ADR-0022.

### ✅ T-UR31 [P] Invite email port behind a switch (was T-UR19) → T-UR30
- Injected mail port (ADR-0021) with a no-op adapter and a fake for tests; the invite service calls it on create and resend only when the config switch is on (default off). No secret committed; Terraform and secret only after T-UR18 is go. Code kept on no-go.
- Done (2026-11-23): port `MailSender` + frozen `MailMessage` + `MailSendError` in `domain/ports.py`; `adapters/mail/noop.py` `NoopMailSender` (logs one fixed line, no recipient or token); fake `FakeMailSender` in `tests/auth_support.py`; switch `Settings.invite_email_enabled` (env `BUDGET_INVITE_EMAIL_ENABLED`, default off). `create_invite` / `resend_invite` take optional `mail`, `email_enabled`, `base_url`; the send runs after the transaction commits, a `MailSendError` is logged (no token) and reported as `IssuedInvite.mail_sent = False` (invite stays valid, no half-state). Link `<base_url>/invite/<token>`, path only without base URL (route is T-UR20). Enabled without a sender raises `ValueError` before any write.
- Done (2026-11-23): port `MailSender` + frozen `MailMessage` + `MailSendError` in `domain/ports.py`; `adapters/mail/noop.py` `NoopMailSender` (logs one fixed line, no recipient or token); fake `FakeMailSender` in `tests/auth_support.py`; switch `Settings.invite_email_enabled` (env `BUDGET_INVITE_EMAIL_ENABLED`, default off). `create_invite` / `resend_invite` take optional `mail`, `email_enabled`, `base_url`; the send runs after the transaction commits, a `MailSendError` is logged (no token) and reported as `IssuedInvite.mail_sent = False` (invite stays valid, no half-state). Link `<base_url>/invite/<token>`, path only without base URL (route is T-UR20). Enabled without a sender raises `ValueError` before any write.
- ADR-0134 §1, ADR-0099.

### ✅ T-UR32 [P] Setup-token service (service part of T-UR21)
- Source (operator 2026-11-22): the drill workflow generates the token and passes only its hash to the app as config (`BUDGET_PLANNER_SETUP_TOKEN_HASH`, unset = setup closed); the plain token appears only in the workflow output. The app stores no token, only a consumed marker: migration `0020_setup_token_consumed.sql` (+ `down/`).
- Predicate "setup open": hash configured, no consumed marker, no users exist and no bootstrap admin configured. Token check: constant-time compare against the configured hash; the consumed marker is written in the same `db_transaction` that creates the first admin; invalid once any user exists. Never committed, never logged (log redaction test).
- No route, no template; `/setup` stays T-UR21.
- Done (2026-11-23): env name is `BUDGET_PLANNER_SETUP_TOKEN_HASH` (field `planner_setup_token_hash`: `BUDGET_` env prefix plus field name, no dynamic alias). Hash scheme: lowercase hex sha256 of the token (`services/setup.hash_token`; config validation rejects anything else). Marker table `setup_token_consumed` (single row, `id = 1`, `consumed_at`; the created admin is in the audit row `setup_token`). "No users" = no live user with an email (the pre-v3 legacy owner row does not count). Dev env counts as bootstrap-configured (dev default admin), so setup is closed there. `services/setup.py`: `is_open`, `check_token`, `complete_setup` (wrong token and closed setup raise the same `SetupClosedError`).
- ADR-0134 §9.

### ✅ T-UR33 [P] Account delete rule (service part of T-UR23)
- Service refuses delete while any live (not soft-deleted) transaction, planned item or recurring rule references the account (operator 2026-11-22: soft-deleted rows do not block) and returns the reference counts (transactions, planned, recurring; "blocked by recurring only" derivable). Otherwise soft delete as before.
- The current accounts UI shows the refusal through the existing error flash (no template change). Tests assert DB state, audit and the counts.
- Requirement F2.8, ADR-0134 §3.

### ✅ T-UR34 [S] Value inventory and data gaps
- `docs/plans/ui-redesign/value-inventory.md`: per handoff page and state, every displayed value (text and the attributes of ADR-0147 §4) with the service or view-model field that produces it, or `missing`.
- Every `missing` field added to its service or view model (canonical modules first, reuse report). Export (`/transactions/export`, `/planned/export`) honours the current tab and filters (ADR-0134 §6). The credit-limit preview returns "left of limit" and "left after this entry" (ADR-0134 §2).
- Values that only differ because the handoff is internally inconsistent are listed as overlay candidates for T-UR00b, not fixed in the app.
- ADR-0147 §3.
- T-UR34b ✅ G1 export honours tab and filters (`direction` for actual; account, category, direction, search and the Ledger planned window for planned; `web/ledger_export.py` builds the per-tab hrefs; ADR-0134 §6, ADR-0148).
- T-UR34a ✅ inventory: `docs/plans/ui-redesign/value-inventory.md` (106 handoff pages + 5 chart specimens; 20 overlay-candidate families for T-UR00b). Gap groups (one wave 2 item each, T-UR34b..l): G1 export filters and per-tab links (`web/ledger_data.py` parsers, export routers, `PlannedFilter`); G2 ledger strips, planned row status, recurring override deltas (`services/ledger_totals.py`, `web/ledger_data.py`); G3 credit-limit preview "left before" (`services/limit_preview.py`); G4 Today afford unclamped per-day and over amount (`services/today.py`); G5 reconcile difference (`services/account_reconcile.py`); G6 category entry count and recent categories (`services/categories.py`); G7 session device label (`services/security_settings.py`); G8 re-auth attempts left (`services/rate_limit.py`, `services/reauth.py`); G9 forecast summary delta (`services/forecast.py`); G10 view-model values: hero `data-digits`/`data-marks`/`data-signs` filter, budget over count, bar left% and cells (`web/view_models.py`, `web/templating.py`); G11 422 summary (`web/errors.py`). Shared files, disjoint hunks: `web/ledger_data.py` (G1, G2), `web/routers/transactions.py` (G1, G3).
- Done (2026-11-23): gap groups G1..G11 delivered as T-UR34b..T-UR34l, registry catch-up T-UR34m, designer follow-up questions T-UR34n. Remainder T-UR34c2 moved to the frontend phase: ledger filter default from/to period, and recurring next-period net via `pending_occurrences` (the inventory board figure uses the monthly in-minus-out net, which T-UR34c delivered).

### ✅ T-UR35 [S] Precondition release → T-UR29..T-UR34
- PR `ui/preconditions` → `main` with a green `drill-gate` on its head SHA (deploy PR: migrations 0019, 0020); release **v3.2.0** through the ADR-0099 pipeline; prod smoke (sign-in, Today, Accounts, edit user refusal, account delete refusal on a referenced account). `docs/CHANGELOG.md` entry; Phase P lines marked ✅.
- Before the PR: migration rehearsal of 0019 and 0020 (up, down, up) on a copy of `data/demo.sqlite` (never `data/budget.sqlite`); the orchestrator runs `just test-e2e` once alone.
- Progress (2026-11-23): migrations 0019/0020 rehearsed up/down/up on a demo copy (ok); prod pre-check of users without an email = 0 (read-only); `just test-e2e` replaced by the green GitHub `e2e.yml` run on the PR head; PR #48 merged with a green `drill-gate` on fd8ade5b; CI fixes T-UR35a (clock-independent planned export test) and T-UR35b (422 summary as a pure function). Remaining: release v3.2.0, prod smoke (sign-in, Today, Accounts, edit user refusal, account delete refusal), then ✅.
- Done (2026-11-23): v3.2.0 released through the ADR-0099 pipeline (release run 45222802367: ci, build + cosign, approved `tf-apply-prod`, host converged, no rollback); operator prod smoke passed (sign-in, Today, Accounts, edit user email refusal, account delete refusal on a referenced account). Phase P complete; T-UR00 unblocked.

### Phase P execution plan

Orchestrator mode (ADR-0066, `.claude/skills/orchestrator-mode/SKILL.md`): main work branch `ui/preconditions` from `main`; one worktree + `wi/ui-preconditions/<ID>` branch per item; hook-only testing; agents sized under 1 h.

| Item | Size | Wave | Touches (conflict map) | Migration |
|---|---|---|---|---|
| T-UR29 | S | 1 | `services/users.py` (`edit_user`), users router error path, `tests/**/users*` | — |
| T-UR33 | S | 1 | `services/accounts.py` delete path, accounts repository counts, accounts router error path | — |
| T-UR34a | M | 1 | discovery only: `docs/plans/ui-redesign/value-inventory.md`; no code | — |
| T-UR30 | M | 2 → T-UR29 | new `repositories/invites.py`, new `services/invites.py`; accept calls the users service (after T-UR29 to avoid `users.py` conflicts) | 0019 |
| T-UR32 | S | 2 | new `services/setup.py`, settings field, small repository for the marker | 0020 |
| T-UR34b ✅ | S | 2 | G1 export filters: `web/ledger_data.py` (parsers), `web/ledger_export.py` (new), export handlers, `PlannedFilter.description_contains` + planned repository | — |
| T-UR34e ✅ | S | 2 | `services/today.py` (`AffordResult.unclamped_per_day_minor`, `over_minor`, `AFFORD_INVALID_MESSAGE`), `web/routers/today.py` pass-through; "over" = max(amount - max(remaining, 0), 0); handoff "114.20 over" does not reproduce (board: left 1,399.93 over 7 days, 1,800.00 gives -57.15 per day and 400.07 over); blank/zero now 422 | — |
| T-UR34d ✅ | S | 2 | G3 credit-limit preview: `services/limit_preview.py` (`LimitPreview.available_before`, `account_name`; `exclude_txn_id`), `web/routers/transactions.py` `limit_preview` handler (`txn_id` query param, pass-through); edit mode leaves the edited transaction's own effect out of the "before" balance (orchestrator decision, designer to confirm: the edit board repeats the new-entry figures; foreign or unknown id ignored); no template change (ADR-0134 §2, ADR-0148) | — |
| T-UR34g ✅ | S | 2 | `services/categories.py` (`entry_count`, `usage_by_category`, `picker_summary`, `RECENT_CATEGORY_LIMIT = 4`), `repositories/transactions.category_usage`, `web/routers/categories.py` edit context `entry_count`; entries = live transactions only (planned and recurring not counted: designer question); recent = latest live txn date desc, id asc, system Reconciliation excluded; total = live categories | — |
| T-UR34f ✅ | S | 2 | `services/account_reconcile.py` (`ReconcilePreview`, `preview_difference`: signed typed - current, available credit for a limited liability, adjustment direction), `web/accounts_data.reconcile_modal_context` (`preview` value), `web/routers/accounts.py` reconcile GET (optional `actual_balance` query); data only, no template; frontend phase needs an HTMX preview endpoint rendering `preview` | — |
| T-UR34c ✅ | M | 2 | G2 ledger strips: `services/ledger_totals.py` (`PlannedTotals.overdue_count/due_today_count`, `RecurringTotals.rule_count/next_due/net_minor` (monthly-equivalent in minus out), `planned_status`, `override_delta`, `spent_minor`), `web/ledger_data.py` (`status` per planned row, `override_deltas` per recurring row, `spent_minor` and `filter_summary` context keys); data only, no template. Remainder T-UR34c2: default from/to period fallback, next-period net via `pending_occurrences` (inventory specifies the monthly net) | — |
| T-UR34i ✅ | S | 2 | G8 re-auth attempts left: `services/rate_limit.py` (`attempts_left`, `user_identity`), `repositories/rate_limit.py` (`get_count`), `services/reauth.attempts_left`, `web/routers/auth.py` + `web/auth_flow.reauth_page` pass `attempts_left` (data only, no template; signed-in re-auth flow only, anonymous sign-in unchanged; ADR-0147 §3, ADR-0148) | — |
| T-UR34h ✅ | S | 2 | G7 session device label: new pure `domain/user_agent.py` (`device_label`, board format "Firefox · macOS", fallback "Unknown device"), `services/security_settings.py` (`SessionRow.device_label`); backend only, no template | — |
| T-UR34k ✅ | M | 2 | G10 view-model values: `web/view_models.py` (`hero_fit`, `bar_cells`, `BudgetView.over_count/left_pct/cells/period_start/period_end`, `BudgetLineView.left_pct/cells`, `UpcomingView` counts), `web/templating.py` (`hero_fit` filter); cells round half up on the floored percent, min-one-cell on the 20-cell bar only; plan range text is structured dates on `BudgetView` (not `PlanHeader`); backend only | — |
| T-UR34l ✅ | S | 2 | G11 422 summary: `web/errors.py` (`field_count`, `field_errors` context), new `web/field_labels.py` (`FIELD_LABELS` MappingProxyType, `field_label`, `field_summary`); no template change | — |
| T-UR34j ✅ | S | 2 | G9 forecast summary delta: `services/forecast.py` (`ProjectionSummary.delta_minor` non-negative magnitude of end - now, `delta_direction` `TrendDirection` up/down/flat, `months`); router already passes the summary through; backend only, no template | — |
| T-UR34m ✅ | S | 2 | catch-up registry: register T-UR34c/h/i/k/l and T-UR33 shared helpers in `canonical_modules.toml` and the CLAUDE.md table; dedupe `web/view_models._upcoming_item` overdue/due-today onto `ledger_totals.planned_status` (ADR-0130 §7) | — |
| T-UR34b.. | S each | 2 | one item per gap group found by T-UR34a (export filters, credit-limit preview, others); split by owning service so items don't share files | — |
| T-UR34c.. | S each | 2 | one item per gap group found by T-UR34a (export filters, credit-limit preview, others); split by owning service so items don't share files | — |
| T-UR31 | S | 3 → T-UR30 | mail port Protocol + `adapters/mail/` no-op adapter + test fake, settings switch; invite service create/resend call | — |
| T-UR34n ✅ | S | docs | `docs/plans/ui-redesign/designer-change-request.md` (follow-up section 2026-11-23, seven items); docs only, no code | — |

- **Migration numbers are fixed here** (0019 invites, 0020 setup marker) so parallel items cannot collide; a later item needing a migration takes 0021 and updates this table.
- **Canonical modules**: register in `tests/architecture/canonical_modules.toml` and the CLAUDE.md table in the same change: "Invites (create, resend, revoke, accept, link state)" → `services/invites.py` (T-UR30); "First-run setup (open predicate, token check, consume)" → `services/setup.py` (T-UR32); "Outbound mail" → the port and `adapters/mail/` (T-UR31). Search terms in each row; reuse report in each handoff.
- **Tests per item** (CLAUDE.md "Tests assert values"): exact stored values, the audit row and its payload, stored timestamps in UTC, and that a second user's rows are absent or unchanged; HTTP tests (T-UR29, T-UR33) assert the flashed error text and unchanged DB state, not only the status. Token items add a log-capture test proving the token and its hash never appear in logs.
- **No allowlist entries, no suppressions** (ADR-0130). New modules start at zero on every guard.
- **T-UR34 split**: T-UR34a is the inventory; the orchestrator reads it and dispatches the gap items (T-UR34b, T-UR34c, ...) in wave 2, each added to this table before dispatch.

---

## Phase 0 — Entry

### ◻ T-UR00 [S] Entry gate and open design questions → T-UR35
- UI test harness exit gate ✅ (T-UT12); quality-audit `[pre-v4-P3]` remediation ✅; ADR-0107 Accepted; **precondition release live (T-UR35, ADR-0148)**.
- Operator decisions recorded in `derived.md` for the handoff README §6 open items: visible bulk-select entry point (#7), inline promote variant, `g o` vs `g t` for Today, and every `no board` / `handoff-only` row from `../ui-test-harness/parity.md` (T-UT06). All decided by 2026-11-22: bulk select as delivered, promote dialog only, `g t` for Today (ADR-0147 §5).
- Work branch `ui/sourdough` created from `main` after the precondition release.
- **Removal ledger** `removal.md` generated from `git ls-files` at the branch point: every file under `web/templates/`, `web/static/` (outside `rd/`), `tests/visual/baselines/`, plus the Tailwind/Node config, `justfile` recipes, pre-commit hooks and CI steps that exist only for the old frontend. Each row: path, owning surface task (or T-UR15 for shared files), status (`delete` / `keep: <reason>`). Only the kept-behaviour files from ADR-0107 §2 may be `keep`.
- **`template_logic.toml` (ADR-0130 amendment 2026-11-21):** after the redesign the allowlist must be empty; new templates add no entries; surface tasks delete the entries of the templates they remove.
- `tests/architecture/test_old_frontend_removed.py`: reads `removal.md` and fails if a row marked `deleted` still exists, or if a new file appears under an old-frontend path (the old trees may only shrink). Starts green with nothing deleted.

### ◻ T-UR00b [S] Pixel parity against the handoff → T-UR00 (blocks T-UR05..T-UR14)
- **Decision**: [ADR-0106 amendment 2026-11-22](../../adr/0106-ui-behaviour-test-harness.md#amendment-2026-11-22-pixel-parity-against-the-handoff) as amended by [ADR-0147](../../adr/0147-handoff-parity-ci-rendered-references-and-data-overlay.md). The handoff screenshots are the visual baselines; the goal of every surface task is pixel parity, test-first.
- **Deliverables**:
  - **Seed from handoff data**: one base seed built from `value-inventory.md` (T-UR34): the handoff's accounts, categories, transactions, planned and recurring items, budgets and users at the frozen date 2026-10-31, used by the frozen server in the visual suite, replacing the `data/demo.sqlite` stand-in. State variants (`--empty`, `--no-matches`, `--long`, `--over-limit`, error states) are named modifiers of the base seed. No masking of dynamic regions.
  - **Data overlay**: `tests/visual/handoff_overlay.toml` corrects handoff values the seed cannot produce (internally inconsistent boards such as *Delete account · confirm* naming "Investments E", totals that do not add up) and carries the `g o` → `g t` rows. Applied when the handoff is served for references and for `--target=mockup` journeys. Allowed fields and the guard `tests/visual/test_handoff_overlay.py` per ADR-0147 §4: text and value attributes only, never tags, classes, ids, CSS or JS; chart geometry rows only with `source = "geometry"` (generated once T-UR12's geometry exists). The vendored handoff stays byte-identical.
  - **References rendered in CI**: `visual.yml` renders the overlaid handoff and the app in the same job and pinned container and compares every page, overlay and state at 1440 / 1024 / 375 in light and dark. `tests/visual/reference/` removed from git and gitignored; a guard fails on a committed PNG there. Local `just visual-reference` and `just test-visual --reference=handoff` run in the same container, never on the host. The provenance manifest of the ADR-0106 amendment §2 is not built.
  - **Tolerance**: `handoff.SURFACE_TOLERANCE` removed; every app-vs-handoff comparison uses `MAX_DIFF_PIXEL_RATIO = 0.001` and the cluster cap `MAX_DIFF_CLUSTER_PX` (largest 8-connected differing region), calibrated as twice the largest cluster seen in repeated handoff-vs-itself runs under load. A failing test writes the diff with the largest cluster outlined. Exceptions only via `derived.md` "Tolerance exceptions" (reason + operator sign-off). Stale `CI_VISUAL=1` wording removed from `tests/visual/README.md` and the `justfile` comments.
  - `tests/visual/test_reference.py` compares every surface (the `MIGRATED_SURFACES` opt-in no longer gates the red run).
- **Acceptance**:
  - the seed renders the overlaid handoff content (spot-checked per surface: same names, amounts, dates, counts); every overlay row has a reason, and the overlay guard is green (and red on a tag, class or CSS change);
  - CI run renders all references in the job; no PNG committed under `tests/visual/reference/`;
  - a red run showing every surface (today, accounts, ledger, plan, settings, auth, errors, overlays) failing against its reference with the old app, recorded in the handoff note;
  - ratio (0.1%) and calibrated cluster cap recorded in `tests/visual/README.md`.
- **Depends**: T-UR00, T-UR34. References: ADR-0147, ADR-0106 amendment 2026-11-22, ADR-0027 amendment 2026-11-22 (T-Q251), `.github/workflows/visual.yml`.

---

## Phase 1 — Foundation (sequential core, then two parallel items)

### ◻ T-UR01 [S] Assets and toolchain → T-UR00
- **Deliverables**:
  - Handoff `static/` copied to `src/budget_planner/web/static/rd/` unchanged, minus `js/stand-in.js`.
  - `scripts/build_css_bundle.py` + `just css`: concatenates `rd/css/main.css`'s `@import` list in order into `rd/css/app.bundle.css`, preserving `@layer` order; pre-commit hook fails when the bundle is stale. Unit test on a small fixture tree.
  - stylelint runs with the handoff's `.stylelintrc.json` on `static/rd/css/**`; the old config keeps linting the old files until T-UR15.
  - Script tags as `type="module"`; theme script as classic `<head>` script; external icon sprite path.
- **Acceptance**: bundle byte-identical across two runs; `just lint` green; old pages render unchanged (crawler and visual on old UI unchanged).
- References: ADR-0107 §3–§4.

### ◻ T-UR02 [S] Base layout and shell → T-UR01
- **Deliverables**: `templates/layouts/base.html` per the handoff page shell: skip link, nav (desktop rail ≥ 768 px, bottom tab bar below), header, `#modal-root`, `#drawer-root`, `#toast-root`, `#flash-region`, global `#palette` and `#shortcuts` dialogs, CSRF meta for `htmx-csrf.js`, CSP nonce on any `<style>`. `fragments/flash/*`, `fragments/toast/undo`, `fragments/states/*`. The palette entries and shortcut targets come from the existing palette route data.
- **Test-first**: `tests/ui_map/shell.py` rewritten to the handoff markup and checked with `--target=mockup` before the template is written.
- **Acceptance**: a placeholder page extending the new base passes shell journeys (navigation, palette, shortcuts, theme switch); unmigrated pages still use the old base; crawler green on both.

### ◻ T-UR03 [P] Server-side value helpers → T-UR01
- **Deliverables** (pure functions + Jinja filters, unit-tested, ADR-0107 §5): category colour to `data-color` preset or nonce'd rule with the `--cat-edge` 3:1 contrast computation; block-character bar spans (20 / 10 cells, `--over`, `--none`); hero figure fit counts (`data-digits`, `data-marks`, `data-signs`); year-cell `data-state`; bar `aria-label` text.
- **Acceptance**: 100 % branch coverage on the helpers; every preset in `category-colors.css` round-trips.

### ◻ T-UR04 [P] Shared fragments and dialog plumbing → T-UR02
- **Deliverables**:
  - Fragments used by more than one surface: `fields/category-picker`, `fields/formula`, `fields/formula-component`, amount input, `forms/error-summary`, `popovers/period-picker`, `plan/period-nav`, row-menu shell, `ledger/pagination`.
  - Response helpers: render a dialog into `#modal-root`; POST success → swap row + OOB `flash/success`; delete/skip/restore → row removal + `toast/undo`; validation error → dialog re-render with `aria-invalid` + error summary (422).
  - Kept behaviour JS (`htmx-csrf.js`, `passkeys.js`) moved under `static/rd/js/` and adapted to the new markup hooks.
- **Acceptance**: contract tests for dialog/OOB behaviour green; each shared fragment rendered in a fragment-level test via the UI map.

---

## Phase 2 — Surfaces (parallel, orchestrator mode) → T-UR01..T-UR04

Each item owns its page templates, its surface-only fragments and overlays, its UI-map module and its router context changes. Shared fragments belong to T-UR04; a surface that needs a change there sends it back to the orchestrator as a follow-up instead of editing it.

**Each item also deletes its old files** as the last step before handoff: every `removal.md` row owned by the surface (old page templates, partials only it includes, its old CSS sheet, its old JS, its old visual baselines, old-markup `id` / `data-testid` hooks go with the templates), plus Python left dead by the switch (view-model fields, router helpers or template filters only the old templates used; confirmed by `vulture` and coverage). Rows are flipped to `deleted` in the same commit. A file still referenced by an unmigrated surface stays, and its row moves to T-UR15.

### ◻ T-UR05 [P] Auth
- Handoff: `pages/auth/login`, `login--error`, `reauth`, `reauth--error`; `register`, `invite`, `invite--expired` only if T-UR00 decided to wire them.
- Routes: login, logout, re-auth, passkey login.

### ◻ T-UR06 [P] Errors
- Handoff: `pages/errors/404`, `409`, `422`, `500`; `offline` per the T-UR00 decision.
- Error handlers render the new pages for full-page requests and the error summary fragment for HTMX requests.

### ◻ T-UR07 [P] Today
- Handoff: `pages/today` and its states (`--empty`, `--loading`, `--afford-over`, `--afford-invalid`, `--flash`); overlays `new-entry*` (happened, planned, repeats fixed, repeats formula, error, phone sheet), `promote--planned`, `promote--recurring`, `row-menu--upcoming`.
- Fragments: `today/upcoming-list`, `today/afford-result`, `rows/upcoming-row`, hero.
- The new-entry dialog is owned here; Ledger reuses it.

### ◻ T-UR08 [P] Accounts
- Handoff: `pages/accounts`, `accounts--empty`; overlays `new-account*`, `edit-account*`, `delete-account*`, `reconcile*`, `row-menu--account`.
- Fragments: `rows/account-row` (including the credit-limit line), `rows/reconcile-snapshot`, sparkline chart.

### ◻ T-UR09 [P] Ledger · actual → T-UR07
- Handoff: `pages/ledger/actual` (+ `--empty`, `--no-matches`, `--long`); overlays `edit-transaction*`, `row-menu--transaction`, `category-picker*`.
- Fragments: `ledger/filter-bar`, `ledger/bulk-bar`, `rows/transaction-row`, `rows/transaction-day`.

### ◻ T-UR10 [P] Ledger · planned, recurring, recently deleted → T-UR07
- Handoff: `pages/ledger/planned` (+ `--empty`), `recurring` (+ `--empty`), `recently-deleted`; overlays `edit-planned`, `edit-recurring*`, `override--occurrence`, `override--remove`, `row-menu--planned`, `row-menu--recurring`.
- Fragments: `rows/planned-row`, `rows/recurring-row`, `rows/deleted-planned`, `rows/deleted-category`.

### ◻ T-UR11 [P] Plan · budget and year
- Handoff: `pages/plan/budget`, `year`; overlays `override--budget-*`, `override--year-cell`, `period-picker*`, `row-menu--budget`.
- Fragments: `rows/budget-line`, `plan/unbudgeted-disclosure`, `rows/year-grid-row`, `rows/year-cell-editor`.

### ◻ T-UR12 [P] Plan · forecast and analytics
- Handoff: `pages/plan/forecast`, `analytics`; `charts/forecast`, `charts/income-vs-expense`, `charts/spend-by-category`.
- Fragments: `rows/forecast-month`, `rows/analytics-category`, `charts/*`. SVG geometry from the server per the handoff's chart notes (amends ADR-0054).

### ◻ T-UR13 [P] Settings · categories, currency and FX, preferences
- Handoff: `pages/settings/categories`, `currency-fx`, `preferences`; overlays `new-category*`, `edit-category`, `archive-category`.
- Fragments: `rows/category-row`. Theme switch (`theme-switch.js`) on Preferences.

### ◻ T-UR14 [P] Settings · security and users
- Handoff: `pages/settings/security` (+ `--error`), `users`; overlay `edit-user`.
- Fragments: `rows/session-row`, `rows/user-row`. Passkey add / remove keeps `passkeys.js` behaviour.

---

## Phase 2b — Scope added by the designer answers (2026-11-21, [ADR-0134](../../adr/0134-redesign-scope-decisions-from-the-designer-change-request.md))

Server-side parts moved to Phase P and ship first ([ADR-0148](../../adr/0148-redesign-backend-preconditions-released-first.md)); what remains here is pages, routers that render them and frontend. These land in the redesign release (ADR-0107 §8). Each needs its own requirement text first (done in `docs/requirements.md`, ADR-0134 Consequences) and the per-surface loop in [README.md](README.md#per-surface-loop-test-first). Not started.

### ◻ T-UR18 [S] Invite email: cost evaluation (operator)
- Evaluate mail provider, Terraform and secret cost for sending invite email. Output: go or no-go recorded in ADR-0134 (amendment). On no-go the switch of T-UR19 stays off and the code is kept. ADR-0134 §1.

### ◻ T-UR19 [moved] Invite email behind a config switch → T-UR31
- **Moved whole to T-UR31** (Phase P, ADR-0148). Original scope kept for reference: send the invite email through an injected port (ADR-0021), behind a config switch, default off. No secret committed; Terraform and secret only if T-UR18 is go. ADR-0134 §1, ADR-0099.

### ◻ T-UR20 [P] Invites, add user, user row menu, forced change → T-UR14, T-UR29, T-UR30
- **Server side shipped in Phase P** (ADR-0148): invite model, migration and service (T-UR30), edit and delete guards (T-UR29). This task builds the pages, dialogs and the routes that render them on top. Routes: create invite with email and role, pending row with expiry, row menu copy link / resend / revoke; invite pages (AU08 and expired, used, invalid AU09); add user dialog with one-time credential dialog (not toast), duplicate email refused; reset and delete user with confirms (ledger entries stay); forced change page (ST10). Edit user dialog (name and member/admin, email read-only) as the first row-menu item before reset and delete; an admin's own row has no menu. Server-side guards (no self-demotion, no last-admin demotion, email unchanged) already shipped in T-UR29; the UI hides the menu on the admin's own row on top of them; delete keeps refusing self and last admin. ADR-0134 §10, §11, ADR-0061, ADR-0073.

### ◻ T-UR21a [P] Setup-token hash wiring → T-UR32
- The drill workflow (and the prod bootstrap path, if any) generates the one-time setup token, prints it only in the workflow output, and passes only its sha256 hex as `BUDGET_PLANNER_SETUP_TOKEN_HASH` to the app (instance metadata / env, per ADR-0111); nothing sets it today, so setup stays closed. Needs an operator decision on where the hash lives for prod.
- Must land before T-UR21 (`/setup` page) can be exercised on a drill.
- ADR-0134 §9, ADR-0099, ADR-0111.

### ◻ T-UR21 [P] First-run `/setup` page with one-time token → T-UR05, T-UR32, T-UR21a
- Token service and "setup open" predicate shipped in Phase P (T-UR32, ADR-0148); this task adds the page and route. Page on `/setup` (not `/auth/register*`), reachable only while no users exist and no bootstrap admin is configured, and only with a valid single-use setup token; 404 without it (no oracle). Token invalidated once the first admin is created, never committed, never logged. Errors: invalid email, credential under 12 characters, mismatch. Once any user exists it redirects to sign in. ADR-0134 §9.

### ◻ T-UR22 [S] Drills: bootstrap admin off by default, setup token in workflow output → T-UR21
- Keep `BUDGET_PLANNER_ADMIN_EMAIL` and Terraform `admin_email` (ADR-0061 §3) but off by default for drill deploys. Drill pipeline generates the per-deploy setup token and surfaces it in the job summary or the explore-drill URL (`/setup?token=...`). Prod behaviour unchanged. ADR-0134 §9, ADR-0099.

### ◻ T-UR23 [P] Account delete rule (blocked dialog) → T-UR08, T-UR33
- Service rule shipped in Phase P (T-UR33, ADR-0148); this task builds the blocked and confirm dialogs on the returned counts. Original scope: service refuses delete while any transaction, planned or recurring item references the account; dialog links to them; state blocked by recurring only; final confirm otherwise. Tests assert DB state and audit. Requirement F2.8. ADR-0134 §3.

### ◻ T-UR24 [P] Remove inline promote routes → T-UR07, T-UR10
- Delete `GET /planned/{planned_id}/promote/inline`, `GET /recurring/{rule_id}/promote/inline`, their templates, UI-map names and route allowlist entries. ADR-0134 §5.

### ◻ T-UR25 [P] Offline save-failure handling → T-UR04
- HTMX request failure (no response) keeps an open dialog's typed input and shows the offline state (`errors/offline` markup); no service worker. ADR-0134 §4, ADR-0113.

### ◻ T-UR26 [deferred] Service worker for failed full page loads
- Deferred beyond the redesign release; needs its own ADR (ADR-0123, ADR-0113 CSP). Tracked here so the offline page is not wired to full-page failures until then. ADR-0134 §4.

### ◻ T-UR27 [P] Theme switch → T-UR13
- Preferences Appearance control (system, light, dark), default system, per browser, full light set. ADR-0134 §8.

### ◻ T-UR28 [P] Ledger export menu and credit-limit line → T-UR09
- `export` menu beside the Ledger Actual and Planned tabs (csv, parquet, current tab and filters, kept on phone, none on Recurring); credit-limit line under the account in new entry, edit and phone sheet (pink with `role=alert` over limit, saving allowed). ADR-0134 §2, §6.

---

## Phase 3 — Cutover

### ◻ T-UR15 [S] Delete the old frontend (final sweep) → T-UR05..T-UR14
- **Files**: every remaining `removal.md` row: old `base.html`, what is left of `_partials/`, `partials/` and the per-feature template directories, `app.css`, `rising-dough.css`, `tailwind.css`, `tailwind.src.css`, `tokens.css`, `fonts.css`, `auth.css`, `settings-*.css`, old fonts, `favicon.svg`, old `static/js/*` (the kept behaviour JS already moved to `rd/js/` in T-UR04), remaining old visual baselines. Port `dev/components.html` from the handoff's `components.html`.
- **Toolchain**: Tailwind npm dependency and config, `just css-watch` and the Tailwind part of `just css`, the `tailwind-check` pre-commit hook, the old stylelint config, Tailwind steps in CI workflows and the Dockerfile.
- **Dead Python**: anything only the old frontend used (old-template view-model fields, helpers, filters, the v2 legacy redirects if T-UR00 decides they have served their purpose), found with `vulture` plus coverage on the full suite.
- **Harness leftovers**: allowlist entries and UI-map names that pointed at old markup; the old-UI `xfail`s that no longer apply.
- **Docs**: `CLAUDE.md` (stack: Tailwind gone), `docs/requirements.md` §3 stack and tooling lines, the `frontend-visual-audit` skill and any agent briefs that name old paths; ADR-0052, ADR-0053, ADR-0055 marked `Superseded by ADR-0107` and ADR-0050 marked superseded for visual direction, in the files and in `docs/adr/README.md`.
- **Operator**: delete the untracked `data/rising-dough-frontend/` copy from the main checkout (if not done after T-UT01).
- **Acceptance**: `tests/architecture/allowlists/template_logic.toml` is empty (ADR-0130 amendment 2026-11-21); every `removal.md` row is `deleted` or `keep` with an ADR-0107 §2 reason; `test_old_frontend_removed.py` green; `grep -r` finds no reference to a removed path, `tailwind`, `app.css` or `rising-dough.css` outside `docs/adr/` and `docs/CHANGELOG.md`; `just ci` green; crawler inventory diff reviewed.

### ◻ T-UR16 [S] Full validation → T-UR15
- Crawler, all journeys, `just test-e2e-browsers` (Firefox, WebKit), axe on every page at 375 and 1440 in both themes, visual diff on every handoff page, `frontend-visual-audit` sweep at 320 / 375 / 768 / 1024 / 1440 / 1920 on every route, budgets from README (gzip sizes, LCP / CLS / INP on `/today`, `/ledger`, `/plan`), keyboard map (`g t/l/p/a/s`, ADR-0147 §5, `n`, `/`, `[` `]`, `?`, `⌘K`), reduced motion.
- Findings fixed or triaged with the operator; results attached to the release PR.
- **Hardening (from v3 T-D140d, ADR-0113)**: drop inline `style=` attributes and remove `'unsafe-inline'` from `style-src` in the prod CSP (from v3 T-D140d, ADR-0113). The Caddyfile CSP lives in `terraform/cloud-init/compose/Caddyfile.tpl`; the e2e CSP guard (T-D140c) parses it. Acceptance: no `style="` attribute in any rendered page (crawler and axe runs), and the CSP guard passes with `style-src 'self'` only.

### ◻ T-UR17 [S] Release → T-UR16
- PR `ui/sourdough` → integration branch, then to `main` with a green `drill-gate` on its head SHA (ADR-0099). Smoke on drill (`mode=explore`) with the operator clicking through.
- ADR-0107 flipped to Accepted (if not already), `docs/CHANGELOG.md` entry, `derived.md` final.
