# ui/sourdough handover, 2026-11-25 (local orchestrator → remote session)

The local orchestrator session ends here; a remote Claude Code session continues the run. Plan: `docs/plans/ui-redesign/`. Operator decisions from the end-of-run QA: `docs/plans/ui-redesign/operator-decisions-2026-11-25.md` (binding; they answer every deferred question so far).

## State

- `ui/sourdough` at `aa771d57`, pushed. It includes `main` up to `4baabf1f` (PR #58: agent_guard hooks, ADR-0150 amendment "hook-enforced rules").
- Draft PR #54 (`ui/sourdough` → `main`) is open.
- The wave 6 tester at `e6daa30c` was RED with two failures, both since fixed but not re-verified:
  - `test_crawl.py::test_every_get_route_is_classified` (`/setup`): fixed by UR21c (`f6fd3573`).
  - `test_htmx_error_flash.py::test_network_failure_shows_flash`: fixed by UR02d (`2c6f39f5`). Decision Q29 changes this behaviour again (item 4 below).
- No local worktrees with unpushed work. Every branch below is on origin.

### Merged this run (wave 6, after wave base `175b41d1`)

UR04e `8f958ecd`, UR00c `59d19398`, UR04f `5be4c7c1`, UR12 `8de349c3`, UR13 `15aa38f6`, UR07b `2540995c`, UR11b `dd99961c`, UR02c `faff04b2`, UR27 `427f6c17`, UR21 `ef3458b2`, UR04g `4d4bd510`, QOR1 `82344851`, QCI1 `ca6768e2`, UR21b `4fd9dd4c`, SCRIBE6 `db2c1054`, UR09a `adff8da9`, UR10b `e6daa30c`, UR21c `f6fd3573`, UR12b `294bbbce`, UR00d `2e2457f6`, UR00e `2dbf6502`, UR02d `2c6f39f5`, main merge `aa771d57`. Earlier waves: `git log --merges --first-parent ui/sourdough`.

### Branches on origin waiting for work

| Branch | Head | State | Next |
|---|---|---|---|
| `wi/ui/sourdough/UR10a` | `3a458818` (WIP) | Ledger planned/recurring/recently-deleted views. Review findings fixed at `d62c651f`. Audit record `1d71bf52`: FINDINGS F1–F3. WIP commit is unverified. | Finish F1–F3 (details below), re-audit, re-review, merge. |
| `wi/ui/sourdough/UR08b` | `71d412f6` | Accounts dialogs. Parked on the contract-test decision. | Q21 approved: apply its 6 contract-test edits, merge `ui/sourdough` in, re-review, merge. |
| `wi/ui/sourdough/UR14` | `9281c651` | Security and users pages. Parked on the contract-test decision. | Q21 and Q22 approved: apply its 6 contract-test edits, merge `ui/sourdough` in, re-review, merge. |
| `wi/ui/sourdough/UR09b` | `9030a4a2` | Edit-transaction dialog. Reviewer MERGE, parked on Q26. | Q26 accepted: merge `ui/sourdough` in, re-review the merge, merge. |

UR10a's F1–F3, from its implementer:
- **F1** (hero and tab counts go stale after row actions): started. `fragments/ledger/hero.html` and `tabs.html` are extracted with `oob` support, and `pages/ledger/index.html` includes them. Still to do:
  - pass `title`, `hero`, `tabs` and `oob` from `ledger_data.table_context`;
  - include the two fragments beside the export menu in `actual-table.html`, `planned-table.html` and `recurring-table.html`;
  - build the hero through `_sched_page` (actual: `period_spent_minor`);
  - integration test: hero and count after a rule delete.
- **F2** (no flash for recurring skip-next, deactivate, and both promotes): untouched. The old UI had none either, and no rule undo existed.
  - Plan: return `saved_response(request, None, {}, message=..., events=<same>)` from `skip_next`, `deactivate_rule` and both `promote_submit`s.
  - Don't use `removed_response`: its `HX-Reswap: delete` would delete the menu button.
  - `render_rule_row` then becomes dead.
  - Add per-action flash tests.
- **F3** (recently-deleted restore leaves the row, count and header): untouched. Restore answers 204 or an empty body. Plan: a self-refetching deleted panel or a re-rendered panel on restore, plus a toast; tests for the count and the empty state.
- **F4/F5**: handoff parity, no action.
- Screenshots were local; the audit record has the descriptions.

## Queue for the remote session (in order, parallel where files are disjoint)

1. UR10a finish (above).
2. UR08b and UR14: apply the Q21 contract-test edits, then merge. Unblocks T-UR23 (after UR08b) and T-UR20 (after UR14).
3. UR09b merge (Q26). Unblocks T-UR28 and the hero thousands-separator follow-up.
4. UR02e (Q29): outside forms, the offline banner shows alone, with the assertive network flash suppressed while the banner shows. Edit `test_network_failure_shows_flash` to assert the banner text (approved).
5. Wave 6 re-verification: one tester pass on `ui/sourdough` after items 1–4 (wave base `175b41d1`), then a scribe for wave 6b bookkeeping. T-UR10 ✅ only after UR10a merges.
6. T-UR24: remove the inline promote routes (after UR10a). Also drop the legacy `?dialog=` promote branches (`form_responses.promote_planned_dialog`, `recurring_views.render_promote_modal`).
7. T-UR28: planned-tab export menu and credit-limit line (after UR09b).
8. Hero figures through `format_figure` (thousands separator in the new-entry, edit-planned and edit-recurring heroes; after UR09b).
9. Decision items from the QA, each docs first:
   - **Q12:** HTML 404 for browsers, JSON for API clients. Update `tests/contract/test_errors.py:55-58`.
   - **Q15:** unknown or foreign account delete returns 404 with no toast. Update `tests/contract/test_accounts.py:383`.
   - **Q25:** a cyclic stored formula shows 0.00 with a warning; saving such a rule is rejected unless the save removes the cycle. Needs an ADR amendment.
   - **Q28:** redact the query string of `/setup` in the access log.
   - **Q1:** keep rows for `csrf.js` and `htmx-2.0.11.min.js`, plus an ADR-0107 §2 amendment.
   - **Q2:** `ci.yml` guard job checkout gets `fetch-depth: 0` and `filter: blob:none`.
   - **Q14:** a dev-only Pillow or numpy dependency for screenshot decode, with an ADR.
   - **Q16:** note the operator's confirmation in ADR-0152.
   - **Q9:** ADR-0134 amendment recording the invite email NO-GO for v1.
   - **Q10:** T-UR21a. Setup-token hash as a GitHub `prod` env secret, with a `ci_environments.toml` entry and the Terraform pass-through. The operator adds the secret; ask before any settings change.
   - **Design parity: follow the handoff**:
     - overlay placeholder, bar labels, empty/future values, the 22nd picker entry;
     - topbar email placement; no 422 summary box; the category palette;
     - "THIS DEVICE"; "Enter an amount above 0.00";
     - seed data: 23 upcoming rows, no header email, chip colours, afford-it states, accounts--empty.

     Contract tests that conflict may be edited under this decision. Keep the current wording where the handoff is silent ("no budget" aria).
   - **Q20:** build the FX rates table (new task, after T-UR15).
10. T-UR00b remainder: map the 59 unmapped overlay pages (needs id-aware routes or ui_map opener clicks); 409/500 reference pages; gate the reference job once surfaces migrate (ruleset change = operator).
11. T-UR15 cutover, T-UR16 full validation, T-UR17 release.
12. T-UR40 and T-UR41 after T-UR17.

## Release end point (Q11)

Get PR #54 green: CI, `e2e.yml` and a passing `drill-gate` on the head SHA. The drill-gate goes through `mode=gate` only, after checking that no drill-group run is queued. Then stop and report.
- Do NOT dispatch an explore drill; the operator does that and clicks through.
- Marking the PR ready and merging to `main` are operator steps (human contract).

## Follow-ups (no operator input needed)

- ADR-0147 §4 amendment should mention the planned "Annual bonus" seed item (UR12b review).
- `tasks.md:161` still says "tab counts 616/27"; the seed now has 32 actual rows.
- UR04g caret double mechanism; e2e fixed sleeps.
- `created_txn_response` should send DIALOG_CLOSE, after which `app-ledger.js` can drop its close.
- Recurring create returns the raw "invalid account/category".
- live_amount vs rt_expand for stored cycles (ties to Q25).
- Setup 429 copy says "sign-in attempts"; no concurrent-setup HTTP test beyond UR21b.
- Shared confirm width (440 vs 520) and focus ring; picker "+ new category"; 1024 topbar wrap; filter truncation; topbar settings active state; topbar `hx-get`.
- `view_models.py:67 _SIGN_MARKS`; `settings_view._local`; money_num → format_figure; narrow the money-scope guard; visual fixture keying; dev/components vs T-UR15; test_passkeys fixture clash; F3 loaf overflow at 375.
- Unmapped overlays list in `tests/visual/test_reference.py` (`UNMAPPED_OVERLAYS`).
- The handoff "visual suite" snapshot job (test_snapshots) fails on settings and recurring at 100%; not investigated.

## Run-log deviations so far (for `docs/runs/2026-11-24-ui-sourdough.md`)

- UR09a ran about 3 h against the 1 h budget; UR10a about 37 min plus fixes, stopped at handover.
- The UR04g auditor's shell heredoc hung for 88 min and was killed; earlier, the UR07b hung shell was killed after 44 min.
- The UR27 agent sent read-only GETs to port 8000 (the operator's dev server).
- UR21 merged with check-item's allowlist FAIL overridden (permanent `[[framework]]` row; ADR-0130 list amended 20→21; QCI1 later added `--allow-framework-rows`).
- Orchestrator idle stall 07:46–09:17 (one agent in flight). Fixed by QOR1 and the main amendment.
- Lock removals by agents; load 24.5 delaying dispatch; implementers self-auditing; UR12 38 min, UR07b about 78 min, UR14 about 62 min.
- Wave 6 tester RED (2 failures, fixed by UR21c and UR02d, re-verification pending).
- UR12b edited two test files outside its Owns list (forced by the seed change; the reviewer accepted it).
