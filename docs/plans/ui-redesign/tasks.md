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
> Operator decisions 2026-11-25 (binding for the rest of the run): [operator-decisions-2026-11-25.md](operator-decisions-2026-11-25.md).
> Operator decisions 2026-11-26 (D1-D11, intended differences, grouped amount input, pre-release scope; binding): [operator-decisions-2026-11-26.md](operator-decisions-2026-11-26.md).
> Legend: `[P]` parallel-safe within its phase, `[S]` sequential, `→ T-URxx` depends on upstream task.
> Every Phase 2 task follows the per-surface loop and definition of done in [README.md](README.md#per-surface-loop-test-first), including the visual diff at the strict default tolerance (0.1%, `MAX_DIFF_PIXEL_RATIO`, plus the cluster cap `MAX_DIFF_CLUSTER_PX`, ADR-0147 §2) unless `derived.md` records an operator-signed exception (T-UR00b).

---

## Accessibility and performance gate (operator 2026-11-23)

The redesign must make the advisory `a11y-perf.yml` checks pass: `a11y (axe-core, advisory)` (no serious or critical axe violations on any crawled route) and `perf (Lighthouse budgets, advisory)` (budgets in `tests/perf/lighthouserc.json`: LCP < 2.5 s, CLS < 0.1, TBT < 200 ms, JS < 300 kB, CSS < 50 kB).

Open findings to resolve in this redesign:

- T-Q319: colour contrast (`color-contrast`), all 13 routes.
- T-Q320: link in text block (`link-in-text-block`) on /ledger and /settings; heading order on /settings.
- T-Q321: LCP about 3.8 to 4.2 s.
- T-Q322: resolved 2026-11-24 by measuring behind Caddy compression (OPS-7, ADR-0027 amendment): the real CSS is about 32 kB gzipped. The redesign must keep CSS under 50 kB compressed.

See `docs/plans/quality-audit/tasks.md`. Once they pass, the operator decides whether to make both checks required.

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
| T-UR34d ✅ | S | 2 | G3 credit-limit preview: `services/limit_preview.py` (`LimitPreview.available_before`, `account_name`; `exclude_txn_id`), `web/routers/transactions.py` `limit_preview` handler (`txn_id` query param, pass-through); edit mode leaves the edited transaction's own effect out of the "before" balance (orchestrator decision, designer confirmed 2026-11-23, ADR-0151 §1: the edit board repeats the new-entry figures; foreign or unknown id ignored); no template change (ADR-0134 §2, ADR-0148) | — |
| T-UR34g ✅ | S | 2 | `services/categories.py` (`entry_count`, `usage_by_category`, `picker_summary`, `RECENT_CATEGORY_LIMIT = 4`), `repositories/transactions.category_usage`, `web/routers/categories.py` edit context `entry_count`; entries = live transactions only (planned and recurring not counted; designer changed it 2026-11-23: all three counted, Reconciliation out of search and N, T-UR36); recent = latest live txn date desc, id asc, system Reconciliation excluded; total = live categories | — |
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
| T-UR34n ✅ | S | docs | `docs/plans/ui-redesign/designer-change-request.md` (follow-up section 2026-11-23, seven items); docs only, no code. Answered 2026-11-23: 3 agreed, 4 changed; changes are T-UR36 (ADR-0151) | — |

- **Migration numbers are fixed here** (0019 invites, 0020 setup marker) so parallel items cannot collide; a later item needing a migration takes 0021 and updates this table.
- **Canonical modules**: register in `tests/architecture/canonical_modules.toml` and the CLAUDE.md table in the same change: "Invites (create, resend, revoke, accept, link state)" → `services/invites.py` (T-UR30); "First-run setup (open predicate, token check, consume)" → `services/setup.py` (T-UR32); "Outbound mail" → the port and `adapters/mail/` (T-UR31). Search terms in each row; reuse report in each handoff.
- **Tests per item** (CLAUDE.md "Tests assert values"): exact stored values, the audit row and its payload, stored timestamps in UTC, and that a second user's rows are absent or unchanged; HTTP tests (T-UR29, T-UR33) assert the flashed error text and unchanged DB state, not only the status. Token items add a log-capture test proving the token and its hash never appear in logs.
- **No allowlist entries, no suppressions** (ADR-0130). New modules start at zero on every guard.
- **T-UR34 split**: T-UR34a is the inventory; the orchestrator reads it and dispatches the gap items (T-UR34b, T-UR34c, ...) in wave 2, each added to this table before dispatch.

---

## Phase 0 — Entry

### ✅ T-UR00 [S] Entry gate and open design questions → T-UR35
- UI test harness exit gate ✅ (T-UT12); quality-audit `[pre-v4-P3]` remediation ✅; ADR-0107 Accepted; **precondition release live (T-UR35, ADR-0148)**.
- Operator decisions recorded in `derived.md` for the handoff README §6 open items: visible bulk-select entry point (#7), inline promote variant, `g o` vs `g t` for Today, and every `no board` / `handoff-only` row from `../ui-test-harness/parity.md` (T-UT06). All decided by 2026-11-22: bulk select as delivered, promote dialog only, `g t` for Today (ADR-0147 §5).
- Work branch `ui/sourdough` created from `main` after the precondition release.
- Progress (2026-11-23): `ui/sourdough` created from `main` at bd3c1b0a (v3.2.0 live); designer follow-up answers folded into the docs (ADR-0151, T-UR36).
- **Removal ledger** `removal.md` generated from `git ls-files` at the branch point: every file under `web/templates/`, `web/static/` (outside `rd/`), `tests/visual/__snapshots__/`, plus the Tailwind/Node config, `justfile` recipes, pre-commit hooks and CI steps that exist only for the old frontend. Each row: path, owning surface task (or T-UR15 for shared files), status (`delete` / `keep: <reason>`). Only the kept-behaviour files from ADR-0107 §2 may be `keep`.
- **`template_logic.toml` (ADR-0130 amendment 2026-11-21):** after the redesign the allowlist must be empty; new templates add no entries; surface tasks delete the entries of the templates they remove.
- `tests/architecture/test_old_frontend_removed.py`: reads `removal.md` and fails if a row marked `deleted` still exists, or if a new file appears under an old-frontend path (the old trees may only shrink). Starts green with nothing deleted.
- Done (2026-11-24): removal ledger `removal.md` (154 old frontend file rows at bd3c1b0a + 24 old visual snapshot rows + 10 toolchain/CI rows; 4 `keep` rows: `htmx-csrf.js`, `js/passkeys.js`, `csrf.js`, `vendor/htmx-2.0.11.min.js`, the last two pending operator confirmation); guard `tests/architecture/test_old_frontend_removed.py` (new files allowed only under `templates/layouts`, `templates/pages`, `templates/fragments`, `static/rd`). Old visual baselines are `tests/visual/__snapshots__/` (there is no `tests/visual/baselines/`). Follow-ups: the branch-point check skips on CI's shallow checkout (`ci.yml` needs `fetch-depth: 0`, operator go); T-UR15 porting `dev/components.html` to the same path must flip that row to `keep` or use a new path.

### ✅ T-UR36 [S] Designer follow-up deltas (backend) → T-UR00 (blocks T-UR00b)
- **Decision**: [ADR-0151](../../adr/0151-designer-follow-up-answers-2026-11-23.md) §2–§3; answers in [designer-change-request.md](designer-change-request.md) (follow-up 2026-11-23). The only backend item on `ui/sourdough`; services, view models and their contract tests, no templates.
- **Category usage** (`services/categories.py`, categories / planned / recurring repositories): usage = live transactions, live planned items, live recurring rules per category (soft-deleted rows excluded); a view-model text for the edit and archive dialogs with zero parts omitted ("41 entries · 2 planned · 1 rule"; nothing when all are zero). Direction stays immutable. Reuse `account_references` (T-UR33) shape where it fits; reuse report.
- **Picker** (`picker_summary`): Reconciliation (system `adjustment`) excluded from recent, search and the total N; Transit kept.
- **Device label** (`domain/user_agent.device_label`): "<browser> · <system>" with "Unknown browser" / "unknown system" for the unknown part; "Unknown device" only when both are unknown.
- **Spent this period** (`web/ledger_data.period_spent_minor`): window from `services/budget.resolve_period_start` + `domain/periods.fiscal_window` (the Budget/Today pay period) instead of `month_bounds`.
- **Forecast summary** (`services/forecast.projection_summary`): `now_value` = today's net worth (`services/fortune.compute_fortune` `net_base`, same converter as Accounts); `delta_minor` / `delta_direction` = last month's projected end minus that; `months` unchanged.
- Tests assert exact values (counts per kind, label strings per user agent, spent over a pay period straddling a month boundary, forecast delta from net worth) and that a second user's rows are absent from the counts; requirements F1.6 and §10.1 already amended.
- Overlay follow-ups for T-UR00b: afford row 9 (−57.15 per day · 400.07 over), row 12 (N without Reconciliation), row 19 (confirmed), plus forecast delta and category count text rows.
- Done (2026-11-24): category usage counts live transactions, planned items and all live recurring rules (inactive included) with `view_models.category_usage_text` ("41 entries · 2 planned · 1 rule"), `categories.usage_for`; picker excludes Reconciliation from recent, `searchable` and N (UR36a). Device label "Unknown browser" / "unknown system" parts; spent this period over `account_planned.resolve_window` (whole pay window); forecast NOW = `compute_fortune().net_base`, delta = last projected end minus it, via `plan_data.forecast_summary` / `forecast_context` (UR36b). Archive-dialog wiring of the usage text is left to T-UR13.

### ◻ T-UR00b [S] Pixel parity against the handoff → T-UR00, T-UR36 (blocks T-UR05..T-UR14)
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
- **Depends**: T-UR00, T-UR34, T-UR36. References: ADR-0147, ADR-0106 amendment 2026-11-22, ADR-0027 amendment 2026-11-22 (T-Q251), `.github/workflows/visual.yml`.
- Progress (2026-11-24): seed `tests/visual/handoff_seed.py` (`build_seed`, 10 modifiers; `test_reference.py` uses it, `test_snapshots.py` keeps demo.sqlite; fixture choice keys on the module name, harden later) and overlay `tests/visual/handoff_overlay.toml` + `overlay.py` + guard `test_handoff_overlay.py` (12 rows) merged. The overlay rewrites the handoff to what seed + app produce (ADR-0147 §4): the handoff is internally inconsistent on Today (overdue "Annual insurance" 412.00 shown while left is 1,399.93); the app gives left 987.93 and afford -116.01 per day / 812.07 over, so the afford row 9 value moves from the ADR-0151 board figure to the seed figure in the follow-up. Remaining: seed-dependent overlay rows (Today/Plan headline, tab counts (seed: 32 actual rows, 15 recurring rules, per `test_ledger_rows` and `test_handoff_seed.py`; the handoff's 616 and 27 are overlaid, not seed values), checked dates, future session times, formula next amount, EUR-named PLN accounts, invite `used` modifier), CI-rendered references (`visual.yml`, remove the 156 committed PNGs), tolerance + cluster cap. Open decisions: `placeholder` attribute in the overlay allow-list (ADR-0147 §4), budget-row bar labels (row 8), empty/future values (rows 2-4, 13), 22nd picker entry (needs an element).
- Progress (2026-11-24, wave 3): references rendered in CI (`visual.yml` advisory job `handoff reference comparison`, `continue-on-error`, not in `visual-gate`; 106 pages x 3 widths x 2 themes from the overlaid handoff; `SURFACE_ROUTES` + `PAGE_ROUTES` map pages to app routes); 156 committed reference PNGs removed, guard `tests/architecture/test_no_committed_reference_png.py`; `just visual-reference` / `test-visual` run in the pinned container. Overlay now 40 rows; 31 seed-value rows checked against services by `tests/visual/test_overlay_values.py`; `invite-used` modifier. Remaining: tolerance + cluster cap (calibrated from CI self-comparison), seed parity follow-ups (owner Safari session, forecast per-month rows, recurring rule rows vs the board), the red-run record. Gate the reference job (add to `visual-gate` needs, drop `continue-on-error`) as surfaces migrate.
- Progress (2026-11-24, wave 4): seed parity: owner `Safari · iPhone` session in the base seed (board times after the frozen day overlaid to seed times), 57 of 60 forecast per-month cells overlaid with service-checked CASES (overlay 100 rows), modifier `recurring-board` (drops the 3 Today-only rules so ledger/recurring shows the board's 12; to be wired per page with page-specific tab-count and hero rows). Reference job sharded into 6 jobs (`REFERENCE_SHARD=<viewport>:<theme>`, 212 tests each; the unsharded job hit the 45-minute timeout, run 45480373605). Known: forecast net cells Dec 2026 and Sep 2027 keep the board's loss class while the seed projects positive (overlay is text-only). Harness gaps for the tolerance item: `SURFACE_ROUTES["auth"]` points at `/login` (route is `/auth/login`); every overlay page compares against plain `/today` (no dialog opened); `SURFACE_TOLERANCE` still per surface.
- Progress (2026-11-25): reference job sharded 6 ways (UR00bE, 9a4c4c61); strict tolerance, max diff pixel ratio 0.001 plus cluster cap (UR00bD, 93471206); cap calibrated to 52 px = 2 × 26 px, the largest handoff-vs-itself cluster over visual.yml runs 45496302019, 45496318944, 45498452834 (UR00bF, 5fd4c3af); red run 45493474608: 106 failed / 106 passed per shard on the old app. Open: dialog overlay pages open their dialog, 409/500 page routes, recurring-board modifier wiring.
- Progress (2026-11-25, F6, ledger dialogs): recent chips lead with the selected category in every picker dialog (rule in `derived.md`); edit and promote dialogs prefill grouped amounts (`2,239.80`, parser reads grouped thousands before a dot); a zero amount keeps the credit line; `override--remove` is a plain-size confirm; the selected-amount selection is collapsed by the harness as a recorded difference (`derived.md`, `tests/visual/README.md`); overlay rows for the actual-board hero behind transaction dialogs, the edit-transaction--error credit line, Bank Fees #18 and the formula hero in the edit-recurring dialogs. Open (operator): recent-chip order, edit-recurring--empty error line.
- Progress (2026-11-25, UR00f): 20 of the 59 unmapped overlay pages now open their real dialog (`tests/visual/handoff_openers.py`: `/today` plus an HTMX fetch of the dialog route into `#modal-root`, ids resolved by name from the seed; 39 stay in `UNMAPPED_OVERLAYS`). Open: row menus, palette, pickers, period pickers, shortcuts (no GET opener), POST error and filled states, formula-editor states, settings/users and invite dialogs (UR20a), delete-account (seed has no zero-balance unreferenced account) and its blocked-planned variant (no account used only by recurring rules), override--year-cell, 409/500/offline pages (no GET route triggers them).
- Progress (2026-11-26, B1 handoff-reference run; not green, T-UR00b stays open): all overlays and pages are mapped: `UNMAPPED_OVERLAYS` and `UNMAPPED_PAGES` are empty. Per-surface parity merged on `ui/sourdough` (25-26 Nov): plan (F1, F7, X2), ledger (F2, F6), accounts, auth and errors (F4, F4b), settings (F3), Today, new-entry and shell (F5, H3, F8, F9, I1), recent chips (R1), near-pass fixes (N1, N2), harness and overlay rows (H1, S1, H2, H4, W1, W2, W4a+W4b+W3, E1, O1, V1, Q1, P1, X3, X5, X6, X7, X1). Overlay O2 was returned and dropped: it would have hidden a real difference; R1 replaces it. CI harness: reference shards still failing on run 45738603125 (head `20a1799`, newest completed `visual.yml` run on the branch whose head is an ancestor of `1d48851`; the run on `1d48851` was still in progress): `1024:light` 26 failed / 186 passed, `375:light` 19 / 193, `1440:dark` 25 / 187, `375:dark` 19 / 193, `1440:light` 25 / 187, `1024:dark` 26 / 186 (212 tests per shard; the job is advisory, not in `visual-gate`). Remaining and why: the operator decisions D1-D11 in [operator-options-2026-11-26.md](operator-options-2026-11-26.md) (picker placeholder row, `accounts--empty`, afford states, ADR-0089 overdue rows, force-password, accounts dialog rows, `today--flash`, one-time password, swatch snap), the open decisions in [operator-decisions-2026-11-25.md](operator-decisions-2026-11-25.md), gating the reference job (a ruleset change, operator), and the tolerance and red-run record. Run log: [docs/runs/2026-11-26-handoff-reference-comparison.md](../../runs/2026-11-26-handoff-reference-comparison.md).
- Decided (2026-11-26): D1-D11 answered in [operator-decisions-2026-11-26.md](operator-decisions-2026-11-26.md). Pages that differ on purpose (D6-B, D7 keep, D8-L keep, `new-account--error` focus ring) go to a signed "Intended differences" table in `derived.md` and are `xfail(strict=True)` in `test_reference.py` (ADR-0147 amendment). The reference job stays advisory; follow-up: once the UI is accepted, the accepted app screenshots become the reference and the job becomes required.
- Progress (2026-11-26, wave SCR1): merged DOC1, DOC2, D5 (T-UR44), D1B, AMT (T-UR46), CI1 and OVL1; T-UR00b stays open.

---

## Phase 1 — Foundation (sequential core, then two parallel items)

### ✅ T-UR01 [S] Assets and toolchain → T-UR00
- **Deliverables**:
  - Handoff `static/` copied to `src/budget_planner/web/static/rd/` unchanged, minus `js/stand-in.js`.
  - `scripts/build_css_bundle.py` + `just css`: concatenates `rd/css/main.css`'s `@import` list in order into `rd/css/app.bundle.css`, preserving `@layer` order; pre-commit hook fails when the bundle is stale. Unit test on a small fixture tree.
  - stylelint runs with the handoff's `.stylelintrc.json` on `static/rd/css/**`; the old config keeps linting the old files until T-UR15.
  - Script tags as `type="module"`; theme script as classic `<head>` script; external icon sprite path.
- **Acceptance**: bundle byte-identical across two runs; `just lint` green; old pages render unchanged (crawler and visual on old UI unchanged).
- References: ADR-0107 §3–§4.
- Done (2026-11-24): `static/rd/` = handoff `static/` minus `js/stand-in.js`; `scripts/build_css_bundle.py` (`--check`; flat `@import url(...) layer(x)` only) builds `rd/css/app.bundle.css`; `just css` runs it after Tailwind; hooks `css-bundle-check`, `stylelint-rd` (`rd/.stylelintrc.json` = handoff config plus `declaration-block-single-line-max-declarations: null` for vendored `rd/css/components/panel.css:45`; fix panel.css and drop the override later). Audit: `docs/audits/2026-11-24-t-ur01-rd-assets.md` (clean). Moved to T-UR02: module script tags, theme script in `<head>`, bundle link, icon sprite path.

### ✅ T-UR02 [S] Base layout and shell → T-UR01
- **Deliverables**: `templates/layouts/base.html` per the handoff page shell: skip link, nav (desktop rail ≥ 768 px, bottom tab bar below), header, `#modal-root`, `#drawer-root`, `#toast-root`, `#flash-region`, global `#palette` and `#shortcuts` dialogs, CSRF meta for `htmx-csrf.js`, CSP nonce on any `<style>`. `fragments/flash/*`, `fragments/toast/undo`, `fragments/states/*`. The palette entries and shortcut targets come from the existing palette route data.
- **Test-first**: `tests/ui_map/shell.py` rewritten to the handoff markup and checked with `--target=mockup` before the template is written.
- **Acceptance**: a placeholder page extending the new base passes shell journeys (navigation, palette, shortcuts, theme switch); unmigrated pages still use the old base; crawler green on both.
- From T-UR01: link `/static/rd/css/app.bundle.css`; `<script type="module">` for `/static/rd/js/*`; `theme.js` as a classic `<head>` script; the palette is static markup today (`templates/partials/_palette.html`, 15 entries, first `g o`), there is no palette route: port the entries and use `g t` for Today (ADR-0147 §5).
- Done (2026-11-24): `templates/layouts/{base,_palette,_shortcuts}.html` per the handoff shell (top bar `rd-mainnav` >= 768 px, `rd-tabbar` below; the handoff has no side rail), `fragments/flash/{success,error}`, `fragments/toast/undo`, nine `fragments/states/*`; dev-gated placeholder `GET /dev/shell` (`routers/dev_components.py`, contract-covered, 404 in production); new-shell UI map `tests/ui_map/rd_shell.py` (old `tests/ui_map/shell.py` kept for unmigrated pages), journeys `tests/e2e/test_rd_shell.py` on mockup and app targets. Palette has the handoff's 7 entries (not 15); Today is `g t` in app, `g o` on the mockup (ADR-0147 §5). Icons use the external sprite path `/static/rd/icons/sprite.svg#icon-…`. Old `csrf.js` / `htmx-csrf.js` still load from `static/` until T-UR04. Pages pass `nav_current`. Fragment link defaults are placeholders; wiring items pass real URLs. Audit: `docs/audits/2026-11-24-t-ur02-base-layout.md` (clean).
- Follow-up done 2026-11-25 (UR02b, 98366386; audit docs/audits/2026-11-25-t-ur02b-shell-flash-toast.md): assertive live region, toast renderer (static/rd/js/app-toast.js), visible 4xx/5xx flashes, signed-in email in the topbar (designer to confirm placement).
- Done (2026-11-25): UR02c rd-styled error flash, shown above an open dialog (faff04b2, ADR-0107, ADR-0143).
- ✅ T-UR02e (operator Q29, `operator-decisions-2026-11-25.md`; ADR-0107, ADR-0143, ADR-0134 §4): outside forms, when a request gets no response the offline banner (`offline.js`, in `#flash-region`) shows alone; `app-toast.js` raises the assertive "Could not reach the server" flash only if no banner appeared. Inside forms unchanged (offline state in the form, no flash). Test: `tests/e2e/test_htmx_error_flash.py::test_network_failure_shows_offline_banner_alone` (approved edit of the flash test).

### ✅ T-UR03 [P] Server-side value helpers → T-UR01
- **Deliverables** (pure functions + Jinja filters, unit-tested, ADR-0107 §5): category colour to `data-color` preset or nonce'd rule with the `--cat-edge` 3:1 contrast computation; block-character bar spans (20 / 10 cells, `--over`, `--none`); hero figure fit counts (`data-digits`, `data-marks`, `data-signs`); year-cell `data-state`; bar `aria-label` text.
- **Acceptance**: 100 % branch coverage on the helpers; every preset in `category-colors.css` round-trips.
- Done (2026-11-24): `domain/category_colors.py` (29 hex presets = `category-colors.css`, grey is a CSS var; `preset_for`, `category_color` -> `data-color` name or `c-<hex>` plus a rule for a nonce'd `<style>`, edge >= 3:1 against `#faf7f3` light panel; registered canonical row); `web/view_models.py` `bar_spans`, `bar_aria_label` ("N percent spent, M percent left"; "no budget" is our wording, designer list), `year_cell_state`; Jinja filters `category_color`, `bar_spans`, `bar_aria_label`, `year_cell_state`, `aria_current_date`. Reused T-UR34k `hero_fit` / `bar_cells`. Follow-up: the money-scope guard flags `//` / `round` in all of `domain/`, so colour math uses `>>`; narrow the guard to money code.
- Follow-up 2026-11-25 (UR03c, d54b2941): domain.money.format_figure is the one signed-figure formatter.

### ✅ T-UR04 [P] Shared fragments and dialog plumbing → T-UR02
- **Deliverables**:
  - Fragments used by more than one surface: `fields/category-picker`, `fields/formula`, `fields/formula-component`, amount input, `forms/error-summary`, `popovers/period-picker`, `plan/period-nav`, row-menu shell, `ledger/pagination`.
  - Response helpers: render a dialog into `#modal-root`; POST success → swap row + OOB `flash/success`; delete/skip/restore → row removal + `toast/undo`; validation error → dialog re-render with `aria-invalid` + error summary (422).
  - Kept behaviour JS (`htmx-csrf.js`, `passkeys.js`) moved under `static/rd/js/` and adapted to the new markup hooks.
- **Acceptance**: contract tests for dialog/OOB behaviour green; each shared fragment rendered in a fragment-level test via the UI map.
- Done (2026-11-24): shared fragments `fragments/fields/{category-picker,formula,formula-component,amount-input}`, `popovers/period-picker`, `plan/period-nav`, `menus/row-menu`, `ledger/pagination` (UI-map render tests `tests/ui_map/test_rd_shared_fragments.py`; inputs documented in each fragment header; audit `docs/audits/2026-11-24-t-ur04a-shared-fragments.md`); `fragments/forms/error-summary`; response helpers `web/dialogs.py` (`dialog_response`, `saved_response` row + OOB `#modal-root` clear + OOB `flash/success`, `removed_response` `HX-Reswap: delete` + OOB `toast/undo`, `invalid_dialog_response` 422; canonical row) with contract tests `tests/contract/test_dialogs.py`; kept JS copied to `static/rd/js/{csrf,htmx-csrf,passkeys}.js` (`htmx-csrf.js` swaps 422 bodies), loaded by `layouts/base.html`; old copies stay until T-UR15 (audit `docs/audits/2026-11-24-t-ur04b-dialogs-js.md`). For page items: dialog inputs need `id="field-<name>"` and `aria-invalid` from `errors`; verify the undo toast OOB on a delete swap in the first page that uses `removed_response`; the picker shows the bare direction until the `direction_label` filter lands.
- Follow-up (2026-11-24): `web/dialogs.dialog_response` wraps the dialog in one `<div>` so the vendored `dialog.js` (`init(e.target)` + `querySelectorAll`) opens a `<dialog>` that would otherwise be the swap root (UR04c); `pages/dev/dialog.html` carries its own wrapper too (harmless nesting; drop it in T-UR15). Picker direction text now from the `direction_label` filter (`↓ expense`, `↑ income`, `⇄ transit`, `± adjustment`; audit `docs/audits/2026-11-24-t-ur03b-direction-label.md`).
- Done (2026-11-25): UR04g dialog shell gaps: placeholder, hero race, action attrs, field_error, formula refresh, stale unit, budget hero sign (4d4bd510).

---

## Phase 2 — Surfaces (parallel, orchestrator mode) → T-UR01..T-UR04

Each item owns its page templates, its surface-only fragments and overlays, its UI-map module and its router context changes. Shared fragments belong to T-UR04; a surface that needs a change there sends it back to the orchestrator as a follow-up instead of editing it.

**Each item also deletes its old files** as the last step before handoff: every `removal.md` row owned by the surface (old page templates, partials only it includes, its old CSS sheet, its old JS, its old visual baselines, old-markup `id` / `data-testid` hooks go with the templates), plus Python left dead by the switch (view-model fields, router helpers or template filters only the old templates used; confirmed by `vulture` and coverage). Rows are flipped to `deleted` in the same commit. A file still referenced by an unmigrated surface stays, and its row moves to T-UR15.

### ✅ T-UR05 [P] Auth
- Handoff: `pages/auth/login`, `login--error`, `reauth`, `reauth--error`; `register`, `invite`, `invite--expired` only if T-UR00 decided to wire them.
- Routes: login, logout, re-auth, passkey login.

### ✅ T-UR06 [P] Errors
- Handoff: `pages/errors/404`, `409`, `422`, `500`; `offline` per the T-UR00 decision.
- Error handlers render the new pages for full-page requests and the error summary fragment for HTMX requests.

### ✅ T-UR07 [P] Today
- Handoff: `pages/today` and its states (`--empty`, `--loading`, `--afford-over`, `--afford-invalid`, `--flash`); overlays `new-entry*` (happened, planned, repeats fixed, repeats formula, error, phone sheet), `promote--planned`, `promote--recurring`, `row-menu--upcoming`.
- Fragments: `today/upcoming-list`, `today/afford-result`, `rows/upcoming-row`, hero.
- The new-entry dialog is owned here; Ledger reuses it.
- Page part done 2026-11-25 (UR07a, 10cf35bb; audit docs/audits/2026-11-24-t-ur07a-today.md). Open (UR07b): new-entry dialog /add, promote and override dialogs; re-enable the T-UR07b skips.
- Remaining: none. UR07b audit F6 (upcoming-row override links did not open) is resolved by UR10b (`e6daa30c`): the override dialog opens through the Upcoming row menu ([audit](../../audits/2026-11-25-t-ur10b-planned-recurring-dialogs.md)).

### ✅ T-UR08 [P] Accounts
- Handoff: `pages/accounts`, `accounts--empty`; overlays `new-account*`, `edit-account*`, `delete-account*`, `reconcile*`, `row-menu--account`.
- Fragments: `rows/account-row` (including the credit-limit line), `rows/reconcile-snapshot`, sparkline chart.
- Page part done 2026-11-25 (UR08a, 40f1ff1f; audit docs/audits/2026-11-24-t-ur08a-accounts.md). Open (UR08b): new/edit/delete/reconcile dialogs, ISO currency combobox in the new-account form (currently dead in the new shell), unknown-id POST /accounts/<id>/delete reports success (audit F5); re-enable the T-UR08b skips and the /accounts KNOWN_BUGS xfail.
- Remaining: UR08b (awaiting operator contract-test decision).

#### ✅ T-UR08c Account delete of an unknown or foreign id returns 404 (operator decision Q15, audit F5)
- `POST /accounts/{id}/delete` for an unknown, foreign or archived id: 404, no `HX-Trigger` toast, no DB or audit change, same response for every case. Contract test renamed `test_delete_unknown_or_foreign_is_404`. ADR-0152 §5 amended; no new ADR; no template change. Files: `web/routers/accounts.py`, `tests/contract/test_accounts.py`.

#### ✅ T-UR41a Unknown routes: HTML 404 page for browsers, JSON 404 for API clients (operator decision Q12)
- A request to an unknown route with `Accept: text/html` and no `HX-Request` gets the existing `pages/errors/404.html` page (status 404, heading "Not found", `X-Request-Id`). Every other caller (JSON, `*/*`, HTMX) keeps `{"detail": "Not Found"}`. Handler in `web/errors.py`; contract test `test_unknown_route_is_404_html_for_browsers_json_for_api_clients` replaces the JSON-for-every-caller pin. ADR-0106 §1 amended; no new ADR. Template item (reuses the T-UR06 404 template; the orchestrator dispatches the visual-auditor). Files: `web/errors.py`, `tests/contract/test_errors.py`, `docs/adr/0106-ui-behaviour-test-harness.md`.

### ✅ T-UR09 [P] Ledger · actual → T-UR07
- Handoff: `pages/ledger/actual` (+ `--empty`, `--no-matches`, `--long`); overlays `edit-transaction*`, `row-menu--transaction`, `category-picker*`.
- Fragments: `ledger/filter-bar`, `ledger/bulk-bar`, `rows/transaction-row`, `rows/transaction-day`.

### ✅ T-UR10 [P] Ledger · planned, recurring, recently deleted → T-UR07
- Handoff: `pages/ledger/planned` (+ `--empty`), `recurring` (+ `--empty`), `recently-deleted`; overlays `edit-planned`, `edit-recurring*`, `override--occurrence`, `override--remove`, `row-menu--planned`, `row-menu--recurring`.
- Fragments: `rows/planned-row`, `rows/recurring-row`, `rows/deleted-planned`, `rows/deleted-category`.

### ✅ T-UR11 [P] Plan · budget and year
- Handoff: `pages/plan/budget`, `year`; overlays `override--budget-*`, `override--year-cell`, `period-picker*`, `row-menu--budget`.
- Fragments: `rows/budget-line`, `plan/unbudgeted-disclosure`, `rows/year-grid-row`, `rows/year-cell-editor`.
- Budget tab done 2026-11-25 (UR11a, 22a3dc57; audit docs/audits/2026-11-24-t-ur11a-plan-budget.md). Open (UR11b): year tab, override dialogs, year-cell editor; re-enable the T-UR11b skips.

### ✅ T-UR12 [P] Plan · forecast and analytics
- Handoff: `pages/plan/forecast`, `analytics`; `charts/forecast`, `charts/income-vs-expense`, `charts/spend-by-category`.
- Fragments: `rows/forecast-month`, `rows/analytics-category`, `charts/*`. SVG geometry from the server per the handoff's chart notes (amends ADR-0054).
- Done: UR12 (`8de349c3`) and UR12b (`294bbbce`: seed history, geometry rows, ADR-0147 §4 amendment). Remaining: none.

### ✅ T-UR13 [P] Settings · categories, currency and FX, preferences
- Handoff: `pages/settings/categories`, `currency-fx`, `preferences`; overlays `new-category*`, `edit-category`, `archive-category`.
- Fragments: `rows/category-row`. Theme switch (`theme-switch.js`) on Preferences.

### ✅ T-UR14 [P] Settings · security and users
- Handoff: `pages/settings/security` (+ `--error`), `users`; overlay `edit-user`.
- Fragments: `rows/session-row`, `rows/user-row`. Passkey add / remove keeps `passkeys.js` behaviour.

---

## Phase 2b — Scope added by the designer answers (2026-11-21, [ADR-0134](../../adr/0134-redesign-scope-decisions-from-the-designer-change-request.md))

Server-side parts moved to Phase P and ship first ([ADR-0148](../../adr/0148-redesign-backend-preconditions-released-first.md)); what remains here is pages, routers that render them and frontend. These land in the redesign release (ADR-0107 §8). Each needs its own requirement text first (done in `docs/requirements.md`, ADR-0134 Consequences) and the per-surface loop in [README.md](README.md#per-surface-loop-test-first). Not started.

### ✅ T-UR18 [S] Invite email: cost evaluation (operator)
- Evaluate mail provider, Terraform and secret cost for sending invite email. Output: go or no-go recorded in ADR-0134 (amendment). On no-go the switch of T-UR19 stays off and the code is kept. ADR-0134 §1.
- Decision 2026-11-25: decided: no-go for v1 (operator QA Q9, recorded in the ADR-0134 amendment of 2026-11-25, §1/§10). `BUDGET_INVITE_EMAIL_ENABLED` stays off, admins copy the invite link by hand, the code stays.

### ◻ T-UR19 [moved] Invite email behind a config switch → T-UR31
- **Moved whole to T-UR31** (Phase P, ADR-0148). Original scope kept for reference: send the invite email through an injected port (ADR-0021), behind a config switch, default off. No secret committed; Terraform and secret only if T-UR18 is go. ADR-0134 §1, ADR-0099.

### ✅ T-UR20 [P] Invites, add user, user row menu, forced change → T-UR14, T-UR29, T-UR30
- **Split (2026-11-25):** UR20a = invite landing pages and invite management on `/settings/users`; UR20b = add user with one-time credential dialog, reset and delete confirms, edit user dialog check, forced change page (ST10). Invite email is NO-GO for v1 (Q9): the switch stays off, admins hand the link over themselves.
- **UR20a done (2026-11-25):** `GET/POST /invite/{token}` (AU08 accept, AU09 expired / used / invalid; public path, rate-limited like `/setup`; accepting signs the person in and lands on Today); `+ create invite` dialog (email, role; 422 with visible error for a bad or duplicate email or a pending invite) that answers with the invite link dialog (the link is shown once: only its hash is stored); pending and expired invite rows on the Users table (`✉ invited · expires 02 DEC`), row menu `resend invite` (new link and 7 days, link dialog) and `revoke invite` (confirm, then the link reads `invalid`). No `copy link` item: the stored hash cannot give the link back, so `resend invite` is the way to get one (derived.md). Service `accept_invite` gained the 12-character and confirm checks. ADR-0134 §1, §10; ADR-0148.
- **PAR-D progress (2026-11-25):** design-parity seed items in `tests/visual/handoff_seed.py`: category chip colours by name from the handoff presets, the picker entry "Wyjścia na miasto", 23 upcoming rows on Today (value-inventory §5 row 12 and the PAR-D note). Open: the picker count N (seed yields 24; handoff 21, ADR-0151 23) and, blocked by ADR-0151/ADR-0147, the afford-it states and `accounts--empty`.
- Note (UR20a audit F3): invite links use the configured public base URL (`Settings.webauthn_origin`), not the request host, so a link made behind a proxy or on a drill is correct only when that origin is set. Error flashes of the users and invite routes (404, 409) use `fragments/flash/error.html` (F1); `partials/_flash.html` loses these callers (still used by `web/errors.py` for old-shell pages; cutover slice to check).
- **UR20b done (2026-11-25):** `GET /settings/users/new` add user dialog (email, name, role; `+ add user` on the page) answering with the one-time password dialog (shown once, `no-store`, password not in logs or audit); a duplicate or bad email re-opens the dialog with the field error and the summary (422, no user written). Reset and delete confirms, the last-admin / self guards (409 error flash) and the edit dialog (name and role, email read-only, first menu item, own row no menu) existed from UR14 and are pinned with exact values (delete keeps the user's ledger entries; reset flags the user and signs their sessions out). Forced change page ST10 existed from UR14 (rate limit and CSRF as the password flow, now pinned `no-store`).
- **Server side shipped in Phase P** (ADR-0148): invite model, migration and service (T-UR30), edit and delete guards (T-UR29). This task builds the pages, dialogs and the routes that render them on top. Routes: create invite with email and role, pending row with expiry, row menu copy link / resend / revoke; invite pages (AU08 and expired, used, invalid AU09); add user dialog with one-time credential dialog (not toast), duplicate email refused; reset and delete user with confirms (ledger entries stay); forced change page (ST10). Edit user dialog (name and member/admin, email read-only) as the first row-menu item before reset and delete; an admin's own row has no menu. Server-side guards (no self-demotion, no last-admin demotion, email unchanged) already shipped in T-UR29; the UI hides the menu on the admin's own row on top of them; delete keeps refusing self and last admin. ADR-0134 §10, §11, ADR-0061, ADR-0073.

### ✅ T-UR21a [P] Setup-token hash wiring → T-UR32
- Caveat (2026-11-25): the OPERATOR still adds the GitHub `prod` secret `SETUP_TOKEN_HASH` and runs the approved apply ([q10-operator-steps.md](q10-operator-steps.md)). Until then the code is done and prod setup stays closed.
- **Status (2026-11-25): prep done, operator step open.** Operator decision Q10: the hash lives in the GitHub `prod` environment secret `SETUP_TOKEN_HASH` (declared in `tests/architecture/ci_environments.toml`) and Terraform passes it as the optional sensitive variable `setup_token_hash` into the instance compose env `BUDGET_PLANNER_SETUP_TOKEN_HASH` (ADR-0111 metadata path; empty = not set, setup stays closed). `terraform.yml` already passes `toJSON(secrets)` and `scripts/ci/tf_env.py` now maps `SETUP_TOKEN_HASH` (prod only), so no workflow edit is needed: the operator only adds the secret and runs the approved prod apply ([q10-operator-steps.md](q10-operator-steps.md)).
- The drill workflow (and the prod bootstrap path, if any) generates the one-time setup token, prints it only in the workflow output, and passes only its sha256 hex as `BUDGET_PLANNER_SETUP_TOKEN_HASH` to the app (instance metadata / env, per ADR-0111); nothing sets it today, so setup stays closed. Needs an operator decision on where the hash lives for prod.
- Must land before T-UR21 (`/setup` page) can be exercised on a drill.
- ADR-0134 §9, ADR-0099, ADR-0111.

### ✅ T-UR21 [P] First-run `/setup` page with one-time token → T-UR05, T-UR32, T-UR21a
- Token service and "setup open" predicate shipped in Phase P (T-UR32, ADR-0148); this task adds the page and route. Page on `/setup` (not `/auth/register*`), reachable only while no users exist and no bootstrap admin is configured, and only with a valid single-use setup token; 404 without it (no oracle). Token invalidated once the first admin is created, never committed, never logged. Errors: invalid email, credential under 12 characters, mismatch. Once any user exists it redirects to sign in. ADR-0134 §9.
- Done (2026-11-25): UR21 first-run `/setup` page (ef3458b2, ADR-0134 §9).

### ✅ T-UR21d [P] Redact the `/setup` query string in the access log → T-UR21
- Operator decision Q28 (2026-11-25): the access log keeps the `/setup` path and never the query string, so the setup token (`/setup?token=...`) never reaches the logs. The existing `strip_access_query` processor (`logging.py`, T-D59) already drops the query of every `uvicorn.access` request line and is wired into the formatter's pre-chain; this task pins the behaviour for `/setup` with a test and records it in ADR-0134 §9. No new code path, no allowlist entry.
- ADR-0134 §9, ADR-0078 §5.

### ◻ T-UR22 [S] Drills: bootstrap admin off by default, setup token in workflow output → T-UR21
- Keep `BUDGET_PLANNER_ADMIN_EMAIL` and Terraform `admin_email` (ADR-0061 §3) but off by default for drill deploys. Drill pipeline generates the per-deploy setup token and surfaces it in the job summary or the explore-drill URL (`/setup?token=...`). Prod behaviour unchanged. ADR-0134 §9, ADR-0099.
- Operator 2026-11-26: before the release (T-UR17).

### ✅ T-UR23 [P] Account delete rule (blocked dialog) → T-UR08, T-UR33
- Service rule shipped in Phase P (T-UR33, ADR-0148); this task builds the blocked and confirm dialogs on the returned counts. Original scope: service refuses delete while any transaction, planned or recurring item references the account; dialog links to them; state blocked by recurring only; final confirm otherwise. Tests assert DB state and audit. Requirement F2.8. ADR-0134 §3.
- UR23 scope (2026-11-25): the dialogs already shipped with T-UR08b (`pages/accounts/dialog-delete.html`, `accounts_view.delete_dialog`, `GET /accounts/{id}/edit?intent=delete`, 404 for unknown or foreign ids); no new route or template. This item pins the rule with `tests/integration/web/test_accounts_delete_rule.py`: counts text and link per state (transactions with others, planned, recurring only: `view=recurring`), planned-only and balance-only ("Its balance is X. Bring it to zero first.", no link, no form) variants, a foreign account id is 404 on GET and POST and stays live (user 2 cannot reference user 1's account: `require_owned` refuses cross-user FKs, so a cross-user count scenario does not exist and is not claimed), confirm POST soft-deletes with one audit row, a POST while blocked (recurring, transaction or balance) is a 409 that writes nothing. Counts derive from `services/accounts.account_references` (no new derived value).

### ✅ T-UR24 [P] Remove inline promote routes → T-UR07, T-UR10
- Delete `GET /planned/{planned_id}/promote/inline`, `GET /recurring/{rule_id}/promote/inline`, their templates, UI-map names and route allowlist entries. ADR-0134 §5.
- UR24 scope (2026-11-25): also drops the legacy non-dialog branch of `GET .../promote` (`form_responses.promote_planned_dialog`, `recurring_views.render_promote_modal`, templates `_promote_modal.html`); the dialog (`pages/entries/promote.html`, UR10a) is the only promote UI and its flash toasts stay. The removed routes return 404.

### ✅ T-UR25 [P] Offline save-failure handling → T-UR04
- HTMX request failure (no response) keeps an open dialog's typed input and shows the offline state (`errors/offline` markup); no service worker. ADR-0134 §4, ADR-0113.
- Done (2026-11-24): `static/rd/js/offline.js` (module; `htmx:sendError` / `htmx:timeout` show the offline state cloned from `<template id="rd-offline-template">` in `layouts/base.html` at the top of the enclosing form, or in `#flash-region` outside a form; focus moves to it; "retry now" resubmits; cleared on the next successful request; no service worker, T-UR26 deferred); `fragments/states/offline.html`; dev-only dialog `GET`/`POST /dev/shell/dialog` (404 in production, contract-covered) exercised by `tests/e2e/test_rd_offline.py` (`route.abort`, input kept, retry). Audit `docs/audits/2026-11-24-t-ur25-offline.md` (clean).

### ◻ T-UR26 [deferred] Service worker for failed full page loads
- Deferred beyond the redesign release; needs its own ADR (ADR-0123, ADR-0113 CSP). Tracked here so the offline page is not wired to full-page failures until then. ADR-0134 §4.

### ✅ T-UR27 [P] Theme switch → T-UR13
- Preferences Appearance control (system, light, dark), default system, per browser, full light set. ADR-0134 §8.
- Done (2026-11-25): UR27 theme switch e2e, ui_map entries and audit (427f6c17, ADR-0134 §8).

### ✅ T-UR28 [P] Ledger export menu and credit-limit line → T-UR09
- `export` menu beside the Ledger Actual and Planned tabs (csv, parquet, current tab and filters, kept on phone, none on Recurring); credit-limit line under the account in new entry, edit and phone sheet (pink with `role=alert` over limit, saving allowed). ADR-0134 §2, §6.
- Done (2026-11-25): the pieces landed with T-UR09, T-UR07b, T-UR34b and the edit dialog; T-UR28 pins them with `tests/integration/web/test_ledger_export_credit.py`: the Planned tab export hrefs follow `date_from` and `q` (`/planned/export?...&format=csv|parquet`), Recurring renders no menu, and the edit dialog's credit line is the service text, `role=alert` and pink over the limit (`▲ Card · 250.00 over the credit limit (1,000.00 left)`), saving allowed. No template or CSS change, so no new audit record.

### ✅ T-UR28b [P] Hero figures through `format_figure` → T-UR09
- The static hero figure (the formula's next amount, shown in the new-entry repeats tab and the edit-recurring dialog) is formatted by `domain.money.format_figure` (thousands separator), like the edit-transaction hero. The amount inputs of the new-entry, edit-planned and edit-recurring heroes keep `format_major` (a bare decimal the parser reads back; `parse_amount_str` takes no grouping).

---

## Phase 3 — Cutover

### ✅ T-UR15 [S] Delete the old frontend (final sweep) → T-UR05..T-UR14
- **Files**: every remaining `removal.md` row: old `base.html`, what is left of `_partials/`, `partials/` and the per-feature template directories, `app.css`, `rising-dough.css`, `tailwind.css`, `tailwind.src.css`, `tokens.css`, `fonts.css`, `auth.css`, `settings-*.css`, old fonts, `favicon.svg`, old `static/js/*` (the kept behaviour JS already moved to `rd/js/` in T-UR04), remaining old visual baselines. Port `dev/components.html` from the handoff's `components.html`.
- **Toolchain**: Tailwind npm dependency and config, `just css-watch` and the Tailwind part of `just css`, the `tailwind-check` pre-commit hook, the old stylelint config, Tailwind steps in CI workflows and the Dockerfile.
- **Dead Python**: anything only the old frontend used (old-template view-model fields, helpers, filters, the v2 legacy redirects if T-UR00 decides they have served their purpose), found with `vulture` plus coverage on the full suite.
- **Harness leftovers**: allowlist entries and UI-map names that pointed at old markup; the old-UI `xfail`s that no longer apply.
- **Docs**: `CLAUDE.md` (stack: Tailwind gone), `docs/requirements.md` §3 stack and tooling lines, the `frontend-visual-audit` skill and any agent briefs that name old paths; ADR-0052, ADR-0053, ADR-0055 marked `Superseded by ADR-0107` and ADR-0050 marked superseded for visual direction, in the files and in `docs/adr/README.md`.
- **Operator**: delete the untracked `data/rising-dough-frontend/` copy from the main checkout (if not done after T-UT01).
- **Progress**: UR15a done (2026-11-25): old Budget and Forecast pages retired (`budget/index.html`, `budget/_yearly.html`, `forecast/index.html`, `partials/forecast/*`, `web/forecast_data.py`); `GET /budget`, `/budget/yearly`, `/forecast`, `/forecast/view` redirect (307) to `/plan?tab=budget|year|forecast` keeping `year`, `month`, `horizon_months`->`horizon` only when it is 6/12/24/60, otherwise dropped so the bookmark lands on the default horizon (`web/plan_redirects.py`; direct `/plan?tab=forecast&horizon=7` stays 422); the plan forecast hero refetches on `forecast-stale`; budget/forecast page tests ported to `/plan`. Remaining: UR15b (old transaction/planned/recurring forms), `dev/components.html` port (UR15c), old CSS/JS/fonts, Tailwind toolchain, docs, dead-Python sweep.
- **Progress UR15d (2026-11-25, old assets removed)**: `d8e57560` removed the old CSS, fonts, Tailwind toolchain and dead helpers and relocated the kept JS (ADR-0107 §2; `csrf.js`, `htmx-2.0.11.min.js` and `passkeys.js` kept). Acceptance evidence: `template_logic.toml` is empty; CI `success` on `d8e57560` (full suite, includes `test_old_frontend_removed`). `e2e` failed on that tip (see the run log).
- **Remaining (operator)**: two edits to `.github/workflows/ci.yml` that the token could not push: the Tailwind steps ([q-ci-tailwind-removal.md](q-ci-tailwind-removal.md)) and the guard checkout depth ([q2-ci-checkout.md](q2-ci-checkout.md)).
- **Acceptance**: `tests/architecture/allowlists/template_logic.toml` is empty (ADR-0130 amendment 2026-11-21); every `removal.md` row is `deleted` or `keep` with an ADR-0107 §2 reason; `test_old_frontend_removed.py` green; `grep -r` finds no reference to a removed path, `tailwind`, `app.css` or `rising-dough.css` outside `docs/adr/` and `docs/CHANGELOG.md`; `just ci` green; crawler inventory diff reviewed.
- **Progress UR15b (2026-11-25, legacy entry flows)**. Survey (callers over templates, `static/rd/js`, `tests/e2e`, `tests/ui_map`):
  - `GET /transactions/new`, `/planned/new`, `/recurring/new`: callers were only the shell's own links (`layouts/base.html` x2, `layouts/_palette.html`, `pages/ledger/index.html`, `fragments/states/*-empty|ledger-first-run`, `fragments/ledger/*-table`) and tests; all three only rendered the `/add` dialog. Repointed the links to `/add?when=happened&dialog=1` and deleted the three routes (`render_new_form`) with their contract/integration tests, the crawl inventory rows and the `mockup_routes` rows.
  - `POST /transactions`, `/planned`, `/recurring` create answers rendered the old `_row.html` partials (swap `none`, so never shown): now `saved_response` (dialog closes, flash, same stale events, reload off the ledger). Deleted `partials/{transactions,planned,recurring}/_row.html`, `ledger_data.planned_row_from_persisted`, `created_*_response` row arguments and 4 `template_logic.toml` entries.
  - `partials/_slideover.html` and `_slideover_page.html`: no route rendered them; deleted with the slide-over branch of `web/rendering.py`.
  - LIVE, kept: `GET /transactions/{id}/edit`, `/planned/{id}/edit|promote`, `/recurring/{id}/edit|promote|overrides/new`, skip-next, `/planned/batch/promote-due`, `/transactions/_limit_preview` (credit line), `/recurring/formula/preview` (all dialog-only, called by `fragments/rows/upcoming-row.html`, `open-edit.html`, `new-entry.html`).
  - REMAINS (needs UR15a to port `budget/index.html`, `forecast/index.html`, `dev/components.html`, still on the old `base.html`): `GET /add` without `dialog=1` (`form_responses.open_legacy_overlay`) with `partials/_add_entry_overlay.html`, `partials/{transactions,planned,recurring}/_form.html`, `transactions/_limit_preview.html`, `static/js/recurring-form.js`, `static/js/palette.js`, and the non-dialog 422 branches (`txn_form_errors`, `planned_form_errors`, `render_form_errors`). They go in the final T-UR15 slice once the three pages are migrated.
- **Progress UR15c (2026-11-25, old shell removed)**: `dev/components.html` ported from the handoff `components.html` to `pages/dev/components.html` on `layouts/base.html` (no template extends the old `base.html` any more; the page has no `template_logic.toml` entry). Deleted the old `base.html`, `_partials/**`, `partials/**` (nav, tabbar, palette, shortcuts, flash, add overlay, the three old entry forms, `_limit_preview`), and the old `static/js/*` except `passkeys.js`. `GET /add` always answers the new-entry dialog (the `dialog` flag is gone); non-dialog 422s of `POST /transactions`, `/planned`, `/recurring` answer the dialog 422 (`txn_form_errors`, `planned_form_errors`, `render_form_errors`, `open_legacy_overlay` deleted); `GET /transactions/_limit_preview` always answers `fragments/fields/credit-line.html`; htmx errors always use `fragments/flash/error.html` (the `X-Shell` switch is gone). `template_logic.toml` is empty. Remaining: UR15d (CSS, fonts, favicon, Tailwind/stylelint toolchain, CI, docs), dead-Python sweep.
- Design parity 2026-11-25: PAR-A (Q17, Q23) done on wi/ui/sourdough/PARA: topbar email removed (handoff shows none); session badge reads `THIS DEVICE`; pins in test_auth_sessions.py and contract test_settings.py updated; derived.md rows marked resolved.
- Design parity 2026-11-25: PAR-B (Q18) on wi/ui/sourdough/PARB: dialogs drop the `N fields need attention` summary box (handoff has none); `fragments/dialogs/dialog.html` renders a dialog-level `▲ Label: message` line (`rd-dialog__error`) for any error with no field line, so every failed save stays visible; non-dialog callers (errors/422, password forms) keep the summary; pins re-asserted through `tests/ui_map/_html.error_lines`.

### ◻ T-UR16 [S] Full validation → T-UR15
- Crawler, all journeys, `just test-e2e-browsers` (Firefox, WebKit), axe on every page at 375 and 1440 in both themes, visual diff on every handoff page, `frontend-visual-audit` sweep at 320 / 375 / 768 / 1024 / 1440 / 1920 on every route, budgets from README (gzip sizes, LCP / CLS / INP on `/today`, `/ledger`, `/plan`), keyboard map (`g t/l/p/a/s`, ADR-0147 §5, `n`, `/`, `[` `]`, `?`, `⌘K`), reduced motion.
- Findings fixed or triaged with the operator; results attached to the release PR.
- **Hardening (from v3 T-D140d, ADR-0113)**: drop inline `style=` attributes and remove `'unsafe-inline'` from `style-src` in the prod CSP (from v3 T-D140d, ADR-0113). The Caddyfile CSP lives in `terraform/cloud-init/compose/Caddyfile.tpl`; the e2e CSP guard (T-D140c) parses it. Acceptance: no `style="` attribute in any rendered page (crawler and axe runs), and the CSP guard passes with `style-src 'self'` only.
- Progress (2026-11-26): CSP style-src hardening attempted on branch wi/ui/sourdough/CSP (not merged): nonce'd `<style>` in swapped fragments mismatched the page nonce (fixed there via `data-color-rules` + `color-rules.js`), but WebKit still reports style-src-attr violations from an unidentified source; parked until after the drill.

### ◻ T-UR17 [S] Release → T-UR16
- PR `ui/sourdough` → integration branch, then to `main` with a green `drill-gate` on its head SHA (ADR-0099). Smoke on drill (`mode=explore`) with the operator clicking through.
- ADR-0107 flipped to Accepted (if not already), `docs/CHANGELOG.md` entry, `derived.md` final.
- Operator 2026-11-25 (Q11): the run stops at a ready PR; the operator dispatches the explore drill and clicks through.

---

## After the migration (operator 2026-11-24)

### ◻ T-UR40 [S] Promote Firefox and WebKit e2e to required checks → T-UR17
- **Rule**: ADR-0120 "Promotion rule": after 3 consecutive green PR runs of a browser's context. During the migration the redesign keeps both browsers green but does not promote them. Quality-audit follow-up (d).
- **Agent PR**: remove "advisory" from the two job names in `.github/workflows/e2e.yml` (`tests/e2e (${{ matrix.browser }}, Playwright container, advisory)`); update everything that pins the required check names (`REQUIRED_CHECKS` in `scripts/check_github_settings.py`, `tests/architecture/test_e2e_required_check.py`, the ADR-0099 required-contexts list); ADR-0120 amendment recording the 3 green runs.
- **Operator**: add both contexts to the `protect-main` ruleset with `integration_id` 15368; refresh the ruleset evidence file.
- **Acceptance**: `scripts/check_github_settings.py` passes against the live ruleset; architecture guards green.

### ✅ T-UR41 [S] Re-run the T-Q316/T-Q317 frontend audit on the migrated templates → T-UR17
- Re-run `frontend-visual-audit` for the flows audited in `docs/audits/2026-11-23-t-q316-t-q317.md`: Undo reload waiting on in-flight htmx requests (T-Q316) and the passkey journey (T-Q317), on the migrated templates at 1440 / 1024 / 375. Step 3b (behaviour contract) included.
- Commit the result as `docs/audits/<date>-t-ur41.md`. Quality-audit follow-up (h); deferred because the redesign replaces the templates the original audit covered.

### ✅ T-UR42a [S] Visual compare decode speed: Pillow dev dependency (operator Q14, 2026-11-25)
- Operator decision Q14: add a dev-only dependency for the screenshot decode, with an ADR. See [ADR-0153](../../adr/0153-pillow-dev-dependency-for-visual-compare-decode.md) and [operator-decisions-2026-11-25.md](operator-decisions-2026-11-25.md).
- **Change**: `pillow` in the `dev` group (`pyproject.toml`, `uv.lock`); `tests/visual/handoff.py` `_decode` uses it; diff mask, ratio and cluster semantics unchanged.
- **Acceptance**: `tests/visual/test_compare.py` and `tests/visual/test_reference_mapping.py` green with unchanged expectations; before/after timings in the commit.

### ✅ T-UR42 [P] FX rates table (derived screen, handoff) → T-UR15
- Operator decision Q20, 2026-11-25: build the FX rates table now in v1, as a new task after T-UR15, per the handoff's derived screen. See [operator-decisions-2026-11-25.md](operator-decisions-2026-11-25.md).
- Operator 2026-11-26: before the release (T-UR17).
- Progress (2026-11-26): Done by T-UR13 (6edbed8c, a57630ce); verified 2026-11-26. The table lives at `/settings?tab=fx` (see [derived.md](derived.md), Currency & FX row).

### ✅ T-UR43a [S] Stored formula cycle: 0.00 with a warning, saves must remove it (Q25)
- Operator decision Q25 ([operator-decisions-2026-11-25.md](operator-decisions-2026-11-25.md)); rule and exact wording in the [ADR-0047](../../adr/0047-recurring-formula-linear-combination-and-chaining.md) amendment 2026-11-25.
- `live_rule_amount` (services/recurring_formula.py) returns `(0, True)` for a stored cycle, replacing the web `live_amount` fallback to the saved snapshot, so the expansion (`rt_expand`), the ledger recurring row and the promote prefill agree (handover follow-up "live_amount vs rt_expand"). The ledger recurring view no longer 500s on a stored cycle and marks it `formula cycle`.
- Saves that keep or create a cycle are 422 with the cycle error and write nothing; an edit that removes it succeeds.

### ✅ T-UR40a [S] Operator decisions 2026-11-25: docs and CI checkout
- Applies four operator decisions from [operator-decisions-2026-11-25.md](operator-decisions-2026-11-25.md), docs first, no code logic:
  - Q1: `csrf.js` and vendored `htmx-2.0.11.min.js` are KEEP: rows in [removal.md](removal.md) and an ADR-0107 §2 amendment.
  - Q2: blocked: needs a push with workflow scope; operator applies [q2-ci-checkout.md](q2-ci-checkout.md): `.github/workflows/ci.yml` `ci` job (the job that runs the guards) checkout gets `fetch-depth: 0` and `filter: blob:none`.
  - Q16: ADR-0152 confirmed by the operator (Status line).
  - Q9: ADR-0134 amendment: invite email NO-GO for v1 (T-UR18 and requirements wording aligned).

### ✅ T-UR44 [S] New-entry tabs carry typed values (D5-b)
- Progress (2026-11-26, wave SCR1): D5 merged (tab carry, QFIX10 regression test, tab-carry e2e test); the QFIX11/12 diagnostics are still in place, so the task stays open.
- Scope: switching the new-entry tab (happened, planned, repeats) keeps the typed amount, category, account and note; tab-only fields (due date, cadence) reset. The tab links add `hx-include` with the CSRF token excluded and `form_responses.open_new_entry` reads the values as `posted`. Then finish QFIX10's regression test on the new behaviour; QFIX11/12 diagnostics may be deleted once the lost-note scenario passes without `fill_stable` retries. Requirement F1.1a.
- Decision: D5 in [operator-decisions-2026-11-26.md](operator-decisions-2026-11-26.md). ADR-0030, ADR-0040.

### ✅ T-UR45 [P] Reconcile dialog: live hero, no extras (D8-R)
- Scope: the reconcile dialog has one balance field; the hero shows the difference live while the balance is typed; `record as` is removed and the adjustment is always booked to the system Reconciliation category; a balance snapshot is always saved (no checkbox); the `preview` button is removed; seed snapshots per the handoff. Service behaviour changes: requirement F2.5 is amended first (done in `docs/requirements.md`); the reconcile ADR amendment is the orchestrator's. Template start: `D8-R-reconcile-extras-out.patch`.
- Decision: D8-R in [operator-decisions-2026-11-26.md](operator-decisions-2026-11-26.md). ADR-0011, ADR-0008 (T-Q217 category choice superseded for the dialog), ADR-0125 §7.

### ✅ T-UR46 [S] Grouped digits accepted in amount inputs
- Scope: `domain/money.parse_amount_str` strips thousands separators (comma, space, no-break space) before the `.` decimal; amount inputs keep rendering the bare value. Tests: exact minor units for each separator, and that a lone decimal comma (`12,5`) still parses as before. Requirement F1.1.
- Decision: "Other decisions" in [operator-decisions-2026-11-26.md](operator-decisions-2026-11-26.md). ADR-0006.

### ✅ T-UR47 [P] Logged validation bugs: 500s and bad values saved
- Scope: bad dialog input answers 422 with a visible field error, never 500 and never a stored bad value. Fix the 500s on bad `day_of_month`, year and opening balance (`abc`) and on a duplicate category name in dialogs; reject `day_of_month=45` on edit recurring and an empty or `abc` budget override amount. Tests assert the 422 body, the field error and that no row or audit entry is written. Requirement F1.1a. Fix before the release (T-UR17).
- Decision: "Logged bugs" in [operator-decisions-2026-11-26.md](operator-decisions-2026-11-26.md); list in "Follow-ups logged 2026-11-25". ADR-0030.

### ✅ T-UR48 [P] Logged HTMX and route bugs
- Scope: `/today` promote success toast is not lost to `HX-Refresh`; a service-raised `ValidationError` flash (`handle_validation`) sends `HX-Reswap: none`; removed routes such as `/transactions/new` answer 404, not 405; `/accounts/9999/edit` answers the shared 404 page, not a bare `account not found` body; palette and tab-bar `+` / `n` open a new entry in place on `/ledger` instead of navigating to `/today`. Fix before the release (T-UR17).
- Decision: "Logged bugs" in [operator-decisions-2026-11-26.md](operator-decisions-2026-11-26.md). ADR-0143, ADR-0040, T-UR41a (Q12 404 pages).

### ✅ T-UR49 [S] 1024 px clipped actions column of planned and recurring tables
- Scope: at 1024 px the actions column of the planned and recurring tables is fully visible (no clipping, no horizontal scroll); `frontend-visual-audit` at 1440 / 1024 / 375. Fix before the release (T-UR17).
- Decision: "Logged bugs" in [operator-decisions-2026-11-26.md](operator-decisions-2026-11-26.md). ADR-0027.

### ◻ T-UR50 [S] Intended differences xfail and remaining unexplained reds
- Scope: `tests/visual/test_reference.py` marks the intended differences listed in `derived.md` as `xfail(strict=True)` (ADR-0147 amendment, the orchestrator's); fix the harness channel mismatch (RGBA vs RGB, OVL1) and investigate the remaining unexplained reds: errors/422 pages, `edit-recurring--picking`, `new-entry--error`. Source: visual.yml run 45817258129 on bd0f6e20 (newest completed reference run, 2026-11-26): these pages fail on all six shards and are not covered by D1-D11; `new-entry--repeats-fixed` / `--repeats-formula` pass there (no longer red). Operator decision 2026-11-26 "Reds outside D1-D11": investigate and fix. The comparison stays advisory.
- Decision: "Intended differences and the gate" and "Reds outside D1-D11" in [operator-decisions-2026-11-26.md](operator-decisions-2026-11-26.md). ADR-0147.
- Progress (2026-11-26, wave SCR1): OVL1 merged (RGBA/RGB channel compare in the harness); the xfail marking and the unexplained reds stay open.
- Progress (2026-11-26, wave SCR3, INV1 5301de28): still open: two pages red pending designer (`new-entry--error`, `edit-recurring--picking`); plus small corner clusters on category-picker 1024 and reconcile 375 light.

### ✅ T-UR51 [S] Dead-Python sweep
- Scope: delete the unused template filters `money_whole`, `money_major`, `major_float`, `bps_percent`, `bar_spans`, `year_cell_state` (and their tests); key the `_orphans` macro by field name instead of message text and drop its unused `field_count` argument; delete the unused ui_map locators `any_recurring_row` and `plan_year.disclosure`. No allowlist entry added; entries of deleted code are removed.
- Decision: "Follow-ups logged 2026-11-25" (confirmed in [operator-decisions-2026-11-26.md](operator-decisions-2026-11-26.md)). ADR-0130, ADR-0123.
- Progress (2026-11-26, wave SCR3, DEAD ec9131d5): merged. Remaining: `_orphans` is keyed by message text; `plan_year.disclosure` kept as used.

## Follow-ups logged 2026-11-25

- → T-UR48: /today promote success sends `HX-Refresh`, so the success toast is lost.
- → T-UR49: At 1024 px the actions column of the planned and recurring tables is clipped.
- Double `role=alert` (the wrapper in `layouts/base.html` line 89 and `fragments/flash/error.html` line 8): accessibility.
- WebKit e2e (advisory) failures: `test_crawl[ledger]` (export as parquet, frame load interrupted), `test_crawl[today]` (cancelled GET `/today/upcoming`), `test_csp_buttons` (x2), `test_setup_page` (timeout).
- → T-UR46: Amount inputs stay ungrouped (`parse_amount_str` accepts no grouping). Operator question: are grouped digits wanted in amount inputs?
- `merge-item` remote-branch deletion returns 403 (token). Stale `wi/**` branches on origin to be pruned by the operator.
- GET 422 page copy is form-oriented for plain GETs (for example `/plan?horizon=100000`).
- → T-UR51: The `_orphans` macro matches on message text; fragile. Key it by field name.
- → T-UR51: `dialog.html` `_orphans` takes an unused `field_count` argument.
- → T-UR47: 500s on bad `day_of_month`, year or opening balance (`abc`), and on a duplicate category name, in dialogs.
- → T-UR47: Bad values are accepted and saved: edit recurring with `day_of_month=45`; budget override amount empty or `abc`.
- → T-UR48: A service-raised `ValidationError` HTMX flash (`handle_validation`) lacks `HX-Reswap: none`.
- → T-UR48: Palette and tab-bar `+` / `n` navigate to `/today` to open a new entry, instead of opening it in place on `/ledger`.
- → T-UR48: Removed routes such as `/transactions/new` answer 405, not 404.
- → T-UR48: `accounts/9999/edit` answers a bare `account not found` body.
- Invite links use the configured public base URL, not the request host (see the T-UR20 note). There is no `copy link` for invites: the token is stored hashed.
- Intermittent required Chromium e2e failure, 'note typed but not posted' (QFIX10/11/12). Root cause under investigation; QFIX10 is not merged (its branch exists on origin).
  - QFIX13: root cause NOT proven. QFIX12 scenarios: the tab swap is not the cause (filling after the planned tab is `aria-current` passes) and a hero swap alone never clears the note. Untested hypothesis: htmx 2 re-focuses the new element with the same id when a swap removes the focused element; a hero refresh swap landing between Playwright's `fill` focus step and its text-insert step, while the amount input inside the swapped `.rd-dialog__hero` still has focus, sends the typed text to the amount input about to be replaced (amount intact, note empty).
  - QFIX13 hardening applied (test side only): `tests/e2e/ui_actions.py` `quiesce` (no `.htmx-request`/`.htmx-swapping`/`.htmx-settling`, no in-flight request counted by the `window.__htmxPending` init script, stable across two animation frames) replaces the fixed 300 ms `_settle` wait; `fill_stable` quiesces, fills, checks the value, re-quiesces and retries up to 3 times. Retries are not failures: the e2e pytest terminal summary prints `e2e fill_stable retries: N` so CI logs show how often a swap beat a fill.
  - QFIX13 operator/design question (docs first, no code change yet): should typed values survive a tab switch? QFIX12 scenarios A, B2 and D lose a note typed on the happened tab when the tab swap replaces `#modal-root`: the tab links are plain `hx-get` without `hx-include`.
- → T-UR51: Unused ui_map locators: `any_recurring_row` and `plan_year.disclosure`.
- → T-UR51: Dead-Python sweep incomplete (`vulture` not installed): filters `money_whole`, `money_major`, `major_float`, `bps_percent`, `bar_spans` and `year_cell_state` are unused by templates.
- Commit subjects that deviate from the item-id rule (history not rewritten): PAR-A audit `docs(PAR-A)`; UR10a `wip(UR10a)`.

## Operator drill review 2026-11-26

Source list: [operator-review-2026-11-26.md](operator-review-2026-11-26.md).

### ✅ T-UR52 [P] New account button redirects to an empty page
- Scope: bug: New account button redirects to an empty page.
- Source: operator-review-2026-11-26.md R1.

### ✅ T-UR53 [P] New income category missing from the anchor dropdown until reload
- Scope: bug: New income category missing from the anchor dropdown until reload.
- Source: operator-review-2026-11-26.md R2.

### ✅ T-UR54 [P] Category picker ignores mouse clicks on desktop
- Scope: bug (likely regression of WEBKIT bea9ce19 combobox.js): Category picker ignores mouse clicks on desktop.
- Source: operator-review-2026-11-26.md R3.

### ✅ T-UR55 [S] Plan/budget: make setting the default budget discoverable
- Scope: design decision (proposal pending): Plan/budget: make setting the default budget discoverable.
- Proposal pending before any code (docs first).
- Source: operator-review-2026-11-26.md R4.

### ✅ T-UR56 [S] Plan/year: cell edit scopes (one-off, every year, default) (superseded by T-UR77)
- Scope: design decision (proposal pending): Plan/year: cell edit scopes (one-off, every year, default).
- Proposal pending before any code (docs first).
- Source: operator-review-2026-11-26.md R5.

### ✅ T-UR57 [S] Month picker arrows change the picker year only
- Scope: spec change + fix: Month picker arrows change the picker year only.
- Source: operator-review-2026-11-26.md R6.

### ✅ T-UR58 [P] Recurring formula always warns non-positive amount
- Scope: bug: Recurring formula always warns non-positive amount.
- Source: operator-review-2026-11-26.md R7.

### ✅ T-UR59 [S] Answer: promoted planned payments in Ledger
- Scope: question (answer pending): Answer: promoted planned payments in Ledger.
- Proposal pending before any code (docs first).
- Source: operator-review-2026-11-26.md R8.
- Done 2026-11-26: documented, no code change (F3.10, dc994669).

### ✅ T-UR60 [S] Account kind read-only after creation (UI and server)
- Scope: spec change + fix: Account kind read-only after creation (UI and server).
- Source: operator-review-2026-11-26.md R9.

### ✅ T-UR61 [S] No auto-zoom on input focus on touch widths
- Scope: spec change + fix (inputs >= 16px on touch widths; do NOT disable pinch zoom: a11y): No auto-zoom on input focus on touch widths.
- Source: operator-review-2026-11-26.md R10.

### ✅ T-UR62 [S] Mobile overlays squeezed (formula row, override scope)
- Scope: bug: Mobile overlays squeezed (formula row, override scope).
- Source: operator-review-2026-11-26.md R11.

### ✅ T-UR63 [P] Mobile ledger filter from/to overlap
- Scope: bug: Mobile ledger filter from/to overlap.
- Source: operator-review-2026-11-26.md R12.

### ◻ T-UR64 [S] Mobile-first redesign of wide views (plan/year, plan/forecast)
- Scope: follow-up (designer change request: mobile-first redesign of wide views; not in this release): Mobile-first redesign of wide views (plan/year, plan/forecast).
- Deferred follow-up (operator): not in this release; needs a designer change request.
- Source: operator-review-2026-11-26.md R13.

### ◻ T-UR65 [S] Accepted UI becomes the visual reference (ADR-0154)
- Scope: after the operator accepts the UI (explore drill): operator dispatches `visual.yml` with `update_baselines=true`; an agent commits the artifact under `tests/visual/__snapshots__/`; operator patch removes the `reference` job from `visual.yml` ([q-visual-reference-trigger.md](q-visual-reference-trigger.md) part 2); overlay rows and "Intended differences" xfails removed from `tests/visual/test_reference.py` and `derived.md`; render script kept as a manual tool.
- Blocked on: operator acceptance of the UI; operator workflow patch.
- Source: operator-decisions-2026-11-26.md "Intended differences and the gate"; ADR-0154.

### ◻ T-UR66 [P] Advisory reference comparison off the per-PR path until T-UR65
- Scope: operator patch doc [q-visual-reference-trigger.md](q-visual-reference-trigger.md) part 1: `reference` job runs on `schedule` and `workflow_dispatch` only (`if: github.event_name != 'pull_request' && ...`), `needs: changes` kept. No app change. Done when the operator applies it.
- Source: operator ask 2026-11-26 (b); ADR-0154 §5.

### ✅ T-UR67 [S] Accounts: duplicate name on create or rename is a 422 on name (F2.1c)
- Scope: duplicate account name on create or rename is a 422 with a name field error, not a 500 (fix 8f88c7b1, merge 4c97e651).
- Source: ACCDUP, F2.1c.

### ◻ T-UR68 [S] New category from the entry dialog without losing the open dialog
- Scope: nested flow; the ACCFIX review kept the plain link.
- Source: ACCFIX review (734270aa).

### ◻ T-UR69 [S] EUR account save without a cached FX rate
- Scope: EUR account save with no cached FX rate leaves "No accounts yet" and shows "Exchange rate unavailable".
- Source: ACCFIX audit.

### ◻ T-UR70 [S] Budget hero "N over" and Total exclude unbudgeted rows
- Scope: "N over" counts unbudgeted rows over a zero budget; Total excludes unbudgeted spend. Operator decision needed. Pre-existing.
- Source: BUDUX audit.

### ◻ T-UR71 [S] Year grid table.rd-year overflows at 1024 and 375
- Scope: table.rd-year overflows at 1024 and 375. Pre-existing; relates to T-UR64.
- Source: PYEAR and BUDUX audits.

### ◻ T-UR72 [S] agent_guard: single-file pytest denied unless the brief names the file
- Scope: single-file pytest is denied unless the brief names the file; pytest with `2>&1` or pipe redirects is misread (orchestrator tooling).
- Source: ADR-0150.

### ◻ T-UR73 [S] Stale "Left open (F4b)" line in derived.md
- Scope: derived.md:200 stale "Left open (F4b)" line.
- Source: derived.md:200.

### ◻ T-UR74 [S] /ledger search placeholder cut at 375
- Scope: /ledger search placeholder "search description…" is cut at 375 with 16px inputs (cosmetic).
- Source: MOBILE re-audit.

## Operator drill review 2 2026-11-27

Source: [review, Drill review 2](operator-review-2026-11-26.md). R22 needs no new task: see T-UR64 (T-UR71 relates).

### ✅ T-UR75 [S] Plan budget and year list all live expense categories (R14)
- Scope: rows are all live expense categories whether or not they have ledger records (archived per ADR-0136 unchanged). Req: F4.6c, F4.8.

### ✅ T-UR76 [S] Edit budget overlay: scope selector on one row (R15)
- Scope: the scope selector, split over 2 rows, renders on one row. Req: F4.6c.

### ✅ T-UR77 [S] Year chips: two options, hover popover under the cell (R16, R17)
- Scope: "this month only" / "every <Month-Name>", this month always preselected, the year cell never changes the default tier; no outer box; overlay right beneath the clicked cell, rows below do not move, inside the viewport; light-mode colours. Supersedes the T-UR56 scope set. Req: F4.8a; ADR-0107 amendment 2026-11-27.

### ✅ T-UR78 [S] Recurring empty-state new entry submit lands on an empty page (R18)
- Scope: bug; "new entry" under an empty recurring list saves and returns the recurring list. Req: F3.2.

### ✅ T-UR83 [S] Empty-state new-entry links on planned and ledger first-run open the dialog in place
- Scope: same bug as R18 (T-UR78); reviewer finding 2026-11-27. Both links get `hx-get` / `#modal-root` like the recurring empty state. Req: F3.2.

### ✅ T-UR79 [S] Recurring day of month defaults from the start date (R19)
- Scope: day of month follows the start date until the user edits it; a manual value is kept. Req: F3.2.

### ✅ T-UR80 [S] Set budget in the status column (R20)
- Scope: "set budget" for unbudgeted rows moves from the budget cell to the status column. Req: F4.6c.

### ✅ T-UR81 [S] No auto-zoom on any touch-width input (R21)
- Scope: every focusable text input, select, textarea and contenteditable (incl. Today hero amounts) at least 16px on touch widths; pinch zoom stays. Req: §5 touch-width line; extends T-UR61.

### ✅ T-UR82 [S] Today bar legend swatches for spent and left (R23)
- Scope: spent and left get a legend swatch like committed. Req: §5 Today bar line.

### ◻ T-UR84 [S] Year-cell override dialog opened without JS renders a bare fragment
- Scope: the year-cell override dialog opened without JS (direct `/budget/rules/<id>/overrides/new` link) renders a bare unstyled fragment.
- Source: BUDSCOPE audit 2026-11-27.

### ◻ T-UR85 [S] Plan/budget unbudgeted list: spent and status columns aligned with the main table
- Scope: spent and status columns of the unbudgeted list are not aligned with the main table at 1440 and 1024 (1440: spent 965 vs 995, status 1170 vs 1085).
- Source: PLANCAT audit 2026-11-27.

### ◻ T-UR86 [S] ui_map locators for the 12 dialog-opening links
- Scope: add ui_map locators for the 12 dialog-opening links so `tests/e2e/test_mobile_layout.py` clicks them instead of `htmx.ajax`.
- Source: ZOOM review 2026-11-27.

### ◻ T-UR87 [S] /today afford input clips long amounts at 375 (low)
- Scope: the /today afford input at 375 clips amounts of 10+ characters, e.g. formatted "12,345,678.00".
- Source: ZOOM audit 2026-11-27 (low).

### ◻ T-UR88 [S] Crawl no longer reaches the set-budget dialog behind the collapsed list (low)
- Scope: the crawl no longer reaches the set-budget dialog behind the collapsed unbudgeted list.
- Source: PLANCAT review 2026-11-27 (low).

### ◻ T-UR89 [S] /recurring/formula/preview answers 422 while the formula is empty (low)
- Scope: `/recurring/formula/preview` answers 422 while the formula is empty, which is console noise. Pre-existing.
- Source: RECUR audit 2026-11-27 (low).
