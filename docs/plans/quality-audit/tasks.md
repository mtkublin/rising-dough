# Post-v3 Code-Quality Audit — Tasks

> Flat index. The method for each task is in [implementation_plan.md](implementation_plan.md).
> Legend: `[P]` parallel-safe within its phase, `[S]` sequential, `→ T-Qxx` depends on upstream task.
> Acceptance = output file complete against its checklist + the guardrails in implementation_plan §11 respected + `✅` prefix added here.
> **Not started.** Blocked until v3 ships. Must complete before v4 starts (v4 T-E00 gate).

---

## Phase 0 — Preconditions

### ✅ T-Q01 [S] Pin the audit commit and set up the environment
- Blocked on v3 shipping (v3 Phase 4 ✅, prod cut over) and on the faster-CI effort (`docs/plans/ci-speed/`, T-CS06 ✅, ADR-0108), so the audit reviews the new test and CI setup.
- `AUDIT_SHA` recorded; worktree and branch `audit/quality`; scratch DB `/tmp/audit.sqlite` copied from `data/demo.sqlite`.
- `findings.md` header filled in: SHA, date, tool versions, LOC per package.
- `just ci` green at `AUDIT_SHA`. If it is red, log the failure as Q-000.

## Phase 1 — Automated baseline → T-Q01

### ✅ T-Q02 [P] Static tool baseline
- Every tool in implementation_plan §2 has been run in report-only mode, with raw output in `baseline/<tool>.txt` and summaries in `baseline/README.md`.
- No dependency or config changes committed (tools run through `uv run --with`).

### ✅ T-Q03a [P] Mutmut spike
- `domain` only, unit tests, `--no-cov`. Record mutant count, wall time, kill / survive / timeout counts and fixture breakage.
- Prod-DB safety check passed.
- Go / no-go decision recorded in `baseline/README.md`.

### ✅ T-Q03b [S] Mutmut baseline and triage → T-Q03a (if go)
- `domain` and `services` baseline score per package in `baseline/mutmut.txt`.
- Survivors sorted into real gap (→ track F finding), equivalent (→ `baseline/mutmut-equivalent.md`) or low value (→ exclusion proposal).

## Phase 2 — Review tracks → T-Q02, T-Q03b

Each task writes only `tracks/<file>.md` and contains a coverage statement, findings in the §4 schema, and a questions list.

### ✅ T-Q04 [P] Track A — duplicated domain logic → `tracks/A-duplication.md`
- Concept map for every concept in plan §3 Track A, plus any new concept found, with implementations, behavioural differences and canonical home.
- Differential-invariant candidates listed; each one executed on the scratch DB.

### ✅ T-Q05 [P] Track B — layering and architecture → `tracks/B-layering.md`
- Every SQL site outside `repositories/`, every `PLC0415` and `PLR0917` suppression, and every file over 800 lines has been classified.

### ✅ T-Q06 [P] Track C — correctness risks → `tracks/C-correctness.md`
- Every clock call site and every broad `except` / fallback in money paths has been classified. Query counts per route recorded.

### ✅ T-Q07 [P] Track D — security → `tracks/D-security.md`
- Done by the security-reviewer agent. Route-by-route authz/IDOR table. CSRF, CSP, headers, XSS and SQLi checks done. Scanner results triaged.

### ✅ T-Q08 [P] Track E — frontend → `tracks/E-frontend.md`
- HTMX emitter/listener matrix; template-logic list; CSRF/CSP handling; kept behaviour JS (`htmx-csrf.js`, `passkeys.js`). Any runtime claim backed by a `frontend-visual-audit` run (1440 / 1024 / 375).
- Markup, CSS, token and presentational-JS findings are out of scope: the Sourdough redesign replaces them (ADR-0107, implementation_plan Track E note).

### ✅ T-Q09 [P] Track F — tests → `tracks/F-tests.md`
- Mutmut real gaps carried in. Redundant-test candidates (coverage contexts + Mutmut) checked by hand. Over-mocking, weak assertions, fixture duplication, flakiness (randomised order run) and coverage gaps listed. Prod-DB path grep clean, or flagged as a finding.

### ✅ T-Q10 [P] Track G — dead code and doc drift → `tracks/G-drift.md`
- Vulture results checked by hand. Every Accepted ADR checked against the code (still true / drifted / should be superseded). Pre-commit vs `just ci` vs CI parity table.

### ✅ T-Q18 [S] Track H — red team → T-Q07 → `tracks/H1-ci-supply-chain.md`, `H2-isolation.md`, `H3-auth.md`, `H4-infra.md`
- Four agents per plan §3 Track H, white-box, with Track D's authz table and Questions as leads. H1–H3 in parallel locally on a seeded synthetic scratch DB; H4 on a fresh operator-triggered drill (`mode=explore`) after a recorded check that it holds no restored prod data.
- Done 2026-11-19: H1, H2, H3 and H4 all complete. H4 ran on explore drill 44609305750 (Step 0: no restored prod data, drill DB empty); the drill was torn down after. Folded into `findings.md` by T-Q11 (H4-01 into Q-027, H4-03 into Q-012, H4-04 into Q-068, new Q-078 to Q-080).
- Rules of engagement (plan §3.1) followed: never prod, no outward actions on the real repo or accounts, no DoS, stop and report on a Critical.
- Every finding has a repro under `repro/H<n>/` (failing pytest or script with recorded output); suspicions without a repro are in Questions. Each file states which goals were attempted and which were not.

## Phase 3 — Verify and consolidate → T-Q04…T-Q10, T-Q18

### ✅ T-Q11 [S] Adversarial verification and consolidation
- Done 2026-11-19: V1, V2, V3 folded into `findings.md` (77 Q-ids from 149 track findings). Track H4 (infra red team on drill 44609305750) folded in afterwards (follow-up commit, T-Q18): 80 Q-ids from 155 track findings, 0 Critical, 20 High, 41 Medium, 19 Low.
- Every Critical and High finding, plus at least 20% of Mediums, independently re-verified. Dismissed findings listed with reasons.
- Duplicates merged; severities calibrated; one best mitigation per finding; summary and histograms written.

### ✅ T-Q12 [S] Operator review → T-Q11
- The operator has accepted, adjusted or dismissed every Critical and High finding. `findings.md` frozen. **Deliverable 1 done.**

## Phase 4 — Prevention (sequential, only after T-Q12)

### ✅ T-Q13 [S] Audit of the guidance surface → `prevention.md` §1
- Every artefact in plan §7.1 reviewed against the root-cause classes that have Critical or High findings (always including `duplicate-logic`).

### ✅ T-Q14 [S] Control design → `prevention.md` §2 → T-Q13
- Prevention matrix: class → findings → control → artefact → verification. Strongest feasible control chosen for each class.

### T-Q15 [S] Apply controls → T-Q14
- Docs first: prevention ADR(s) (next free numbers; the mutation-testing ADR is **not** 0095), requirements §3.3 / §3 tooling, then CLAUDE.md, skills and briefs.
- Guards in allowlist mode with CI green. Mutmut setup committed (`pyproject`, `just mutate*`, `.gitignore`, fixture fixes). Nightly job decided.
- CLAUDE.md and skill edits reviewed by the operator.
- **T-Q15b tooling landed** (2026-11-20, ADR-0130/ADR-0131): mutmut + import-linter pinned, `[tool.mutmut]`, `[tool.importlinter]` (40 allowlisted imports), TID251 clock ban (per-file allowlist) and `PGH`, `clock.py` scaffold, `just mutate*`/`guards`/`lint-imports`, `scripts/mutate_report.py`, `scripts/check_github_settings.py`, CI runs `pre-commit run --all-files` (`SKIP=pytest-fast`), weekly `mutation.yml`. Timings: `baseline/precommit-timing.md`. Open: T-Q15a guards, T-Q15c CLAUDE.md/skills.
- Progress: **T-Q15a guards landed** (2026-11-20, ADR-0130): `tests/architecture/` exact-ratchet guards G1-support, G2, G4, G5, G6, G7 (invariants registry), G7b, G9, G10, G12, G14, G15, G16, G17-repo and G18 to G27 with `allowlists/*.toml`, `canonical_modules.toml` (S1), S3 isolation registry; `repro/allowlist_by_qid.py` lists entries per Q-id and epic. T-Q15b (config, CI, hooks) and T-Q15c (CLAUDE.md, skills) remain; T-Q15 is not done.

### T-Q16 [S] Prevention dry run → T-Q15
- A fresh agent working on a synthetic duplication-prone task uses the canonical module, or the guard trips. Result recorded. `just ci` green. **Deliverable 2 done.**

## Phase 5 — Remediation backlog → T-Q12 (may overlap T-Q13…T-Q16)

### T-Q17 [S] Write the remediation backlog
- Accepted findings turned into `T-Q2xx` tasks in this file, ordered Critical → High → allowlist burn-down → Medium → Low. Each task lists its finding ids, ADRs, acceptance criteria and the allowlist entries it removes.
- Tasks that must be ✅ before v4 Phase 3 are tagged `[pre-v4-P3]`: Critical/High `duplicate-logic`, `repo-bypass` and `scoping-gap` (implementation_plan §9).

---

## Remediation (T-Q2xx) (draft — pending T-Q12 operator review)

Source: [findings.md](findings.md) (80 Q-ids, 0 Critical, 20 High, 41 Medium, 19 Low). Method: [implementation_plan.md](implementation_plan.md) §5, §7.3, §8, §9. Execution happens after T-Q12 and follows the normal handoff checklist (CLAUDE.md), one task at a time or in orchestrator mode.

**Counts: 59 tasks, covering all 80 Q-ids.** Band 1 (before a second user) 5; band 2 (Highs biting current PLN data) 6; band 3 (other High money and security) 7; band 4 (test-gap Highs) 8; band 5 (guard allowlist burn-down) 6; band 6 (Medium) 20; band 7 (Low) 7. Every High Q-id has its own task or is the lead of a tightly coupled cluster (Q-007 epic with its aliases; Q-011 with Q-029; Q-002 and Q-010 are split in two because step 1 or one half is a quick hotfix and the rest is a refactor).

**Ordering rationale.** (1) Operator facts of 2026-11-19: one user now, more soon, so scoping and abuse-control items come first, Q-001 first of all (High now, Critical the day a second user exists). (2) Then the Highs that bite on current PLN-only data (Q-002, Q-003, Q-010 sign part, Q-004, Q-006), because they need no FX to produce a wrong number or a 500. (3) Then the latent High money and security work: the canonical FX converter (Q-007) and everything that hangs off it, the currency renderer, reconcile, and the ungated environments. (4) Then the test-gap Highs, which lock the fixes in; each fix task already writes its own failing test first, so band 4 adds the shared harness and the mutant-cluster work, not the first regression test. (5) Then the guard allowlist burn-down (guards from T-Q15 run in allowlist mode, see §7.3; prevention.md §2 lists the allowlists by class). (6) Medium, (7) Low.

**Allowlist convention.** The guards are designed in `prevention.md`; this backlog names them generically. "per prevention.md §2 allowlist for `<class>`" means: remove from that allowlist exactly the entries that match the task's locations, run the guard, and keep it green. Task T-Q232 is the closing gate: every allowlist must be empty and every guard strict.

**Acceptance convention (applies to every task).** Docs-first step done and committed first (CLAUDE.md change policy). A failing test that reproduces the finding is written first and committed or staged before the fix; where a `docs/plans/quality-audit/repro/` script exists, it is ported into `tests/` (as an integration or invariant test) and the original script stays as evidence. Pre-commit hooks green; frontend-touching tasks run `frontend-visual-audit` (desktop 1440 / tablet 1024 / mobile 375); `docs/CHANGELOG.md` line; no writes to `data/budget.sqlite`. The per-task Acceptance below lists only what is specific.

**`[pre-v4-P3]` subset (implementation_plan §9; must be ✅ before v4 Phase 3 starts, T-E00 gate):** T-Q201 (Q-001), T-Q206 and T-Q207 (Q-002), T-Q208 (Q-003), T-Q209 and T-Q215 (Q-010), T-Q212 (Q-007), T-Q213 (Q-008), T-Q214 (Q-009). Recommended additionally, not mandatory by the rule (Medium, but same classes and repository-layer or aggregate code that Phase 3 sweeps): T-Q227 (Q-030, Q-032, Q-036, Q-075), T-Q228 (Q-024, Q-049), T-Q241 (Q-045). Tagged `[pre-v4-P3-rec]` below.

**`[before-2nd-user]` list:** T-Q201 (Q-001), T-Q202 (Q-028), T-Q203 (Q-027), T-Q204 (Q-025, Q-063), T-Q205 (Q-034), T-Q221 (Q-015). Also keep in mind: an admin password reset equals account takeover until v4 envelope encryption (accepted v3 risk), and OQ-2 (when the second user arrives) decides how urgent band 1 is.

**`[pre-first-non-PLN]` list:** T-Q212, T-Q213, T-Q214, T-Q215, T-Q216 (Q-007 to Q-011, Q-029). Prod is PLN-only today (OQ-1 asks the operator to confirm with a read-only count on a copy); nothing in this set may be skipped before the first non-PLN, non-base or zero-decimal account exists.

---

### Band 1 — Before a second user is onboarded

### T-Q201 [S] Income-anchor endpoint uses the signed-in user
- Findings: Q-001 (D-01, H2-01).
- Tags: `[pre-v4-P3]` `[before-2nd-user]`
- Depends on: none.
- Docs-first step: none (requirements 6.9 and ADR-0061/0025 already require per-user scoping); add one line to `docs/CHANGELOG.md`.
- Acceptance: failing two-user integration test first, ported from `repro/H2/h2_01_anchor_oracle.py` (user 2 writes own row, user 1's row untouched, user 2 gets no 200/422 oracle on user 1's category ids); then `Depends(current_user_id)` on `set_income_anchor` and pass it to both service calls (`web/routers/budget.py:375-399`). New architecture test under `tests/architecture/` fails on an integer literal passed as `user_id` anywhere under `web/` and `services/`.
- Allowlist entries removed: none expected (guard lands strict for this class); if prevention.md §2 lists literal-`user_id` hits, remove per prevention.md §2 allowlist for `scoping-gap`.
- Effort: S.
- Operator question blocking it: none (OQ-2 only sets urgency).

### T-Q202 [S] Recurring-rule save path validates source categories and positive amounts
- Findings: Q-028 (H2-02).
- Tags: `[before-2nd-user]`
- Depends on: none (reuses the two-user fixture; T-Q221 generalises it).
- Docs-first step: none.
- Acceptance: failing test first from `repro/H2/h2_03_formula_foreign_sources.py` extended to create and update (foreign or nonexistent category id and a zero-amount formula rule are rejected with 422 and nothing is persisted); then move `_invalid_source_ids` to a shared service function and call it from `_resolve_amount_inputs` (`web/routers/recurring.py:181-230`, used at create `:268` and update `:632`).
- Allowlist entries removed: per prevention.md §2 allowlist for `scoping-gap` (if any hit in `web/routers/recurring.py`).
- Effort: S.
- Operator question blocking it: none.

### T-Q203 [S] Authentication abuse controls: trusted proxy identity, bounded audit text, per-IP lockout
- Findings: Q-027 (D-06, H3-01, H3-05, H3-07, H2-04, H4-01).
- Tags: `[before-2nd-user]`
- Depends on: none.
- Docs-first step: ADR (next free number) or ADR-0072 amendment recording that the rate-limit identity is the proxy-set client address and that attacker text written to `audit_log` is truncated and escaped; requirements §6.7 line. OQ-25 is answered by H4: Caddy overwrites `X-Forwarded-For` and `X-CSP-Nonce`, so header rotation is not exploitable via Caddy; the remaining work is the real-IP chain (H4-01: host-networking or no-MASQUERADE for Caddy, Caddy `trusted_proxies`, `--forwarded-allow-ips` pinned to Caddy's address) plus the per-email cap and bounded audit text.
- Acceptance: failing tests first from `repro/H3/h3_rate_limit.py` (spoofed leftmost `X-Forwarded-For` does not change the bucket) and `repro/H2/h2_07_login_lockout_and_audit_tail.py` (one user cannot lock out another behind the same IP; the audit row length is bounded); then `--forwarded-allow-ips` pinned to the proxy address in the `Dockerfile` and compose template, proxy overwrites `X-Forwarded-For`/`X-Real-IP`, bucket keyed on (IP, username) with a global IP ceiling, truncation of persisted text (`web/routers/auth.py:85-203`).
- Allowlist entries removed: none expected (security-control class has no allowlist in v1 of the guards; confirm in prevention.md §2).
- Effort: M.
- Operator question: OQ-25 answered by H4; OQ-30 (which MASQUERADE rule) shapes the fix.

### T-Q204 [S] One transaction for compound mutations, immediate write locks, admin edge cases
- Findings: Q-025 (C-09, B-07), Q-063 (H2-05).
- Tags: `[before-2nd-user]`
- Depends on: none.
- Docs-first step: ADR (next free number) deciding `BEGIN IMMEDIATE` in `repositories/_shared.transaction` and that guard reads live inside the transaction; update ADR-0019 cross-reference.
- Acceptance: failing tests first from `repro/C/repro_concurrency.py` (double-submit promotes once, concurrent writers wait instead of 'database is locked') and `repro/H2/h2_04_admin_chain.py` (absent `is_admin` leaves the target unchanged; concurrent admin changes map to the 409 flow, not 500); then `BEGIN IMMEDIATE`, guard reads moved inside the transaction in `services/planned.py`, `services/recurring.py`, `services/reconciliation.py`, `services/users.py`, and `web/routers/settings_users.py` treating a missing `is_admin` as unchanged.
- Allowlist entries removed: none expected.
- Effort: M.
- Operator question blocking it: none.

### T-Q205 [S] `user_id`-leading indexes and the per-request session write
- Findings: Q-034 (C-11).
- Tags: `[before-2nd-user]`
- Depends on: none.
- Docs-first step: none beyond a CHANGELOG line (migration only); note in `docs/requirements.md` data section if indexes are listed there.
- Acceptance: failing test first: `repro/C/explain_plans.py` ported to an integration test asserting `EXPLAIN QUERY PLAN` for the hot queries uses the new indexes (no full scan of `transactions`, `planned_transactions`, `audit_log`, `recurring_rules`); then the migration (`(user_id, operation_date) WHERE deleted_at IS NULL`, `(user_id, id)` on `audit_log`, `(user_id, active)` on `recurring_rules`) and, if cheap, throttle the session `last_seen` write. Migration runs on a scratch DB only; prod applies it through the normal release.
- Allowlist entries removed: none.
- Effort: S-M.
- Operator question blocking it: none.

---

### Band 2 — Highs biting current PLN data

### T-Q206 [S] Hotfix: forecast overlay stops double-counting linked recurring occurrences
- Findings: Q-002 step 1 (A-04).
- Tags: `[pre-v4-P3]`
- Depends on: none.
- Docs-first step: none (ADR-0087 amendment already states the rule); CHANGELOG line.
- Acceptance: failing test first ported from `repro/A/output/inv_03b*` and `repro/verify/V1/v_a04.py` (rule 1530 plus a linked planned row: budget committed 1530 and forecast overlay 1530, not 3060); then `_committed_future_for_category` (`services/forecast.py:345-390`) delegates to `budget._committed_by_category`, deleting the second implementation.
- Allowlist entries removed: per prevention.md §2 allowlist for `duplicate-logic` (the `forecast._committed_future_for_category` entry).
- Effort: S.
- Operator question blocking it: OQ-6 only affects overdue policy (T-Q227), not this fix.

### T-Q207 [S] One occurrence expander for all seven consumers
- Findings: Q-002 step 2 (A-04, A-17).
- Tags: `[pre-v4-P3]`
- Depends on: T-Q206, T-Q212 (FX per-item conversion goes through the canonical converter), T-Q208 (half-open window helper).
- Docs-first step: ADR (next free number, amends ADR-0087/0085): `pending_occurrences(conn, user_id, *, start, end, include_overdue, category_ids)` in `services/recurring.py` as the single "rules x overrides x linked-dedup x window" implementation.
- Acceptance: failing tests first: the invariant tests of T-Q220 for overlay-versus-budget parity stay red until each consumer is switched; then migrate `services/budget.py:296-310`, `forecast.py:262-283,373-381,737-770`, `account_planned.py:106-116`, `income.py:25-93`, `upcoming.py:74-174`, `recurring_formula.py:146-190` and delete the hand-rolled loops.
- Allowlist entries removed: per prevention.md §2 allowlist for `duplicate-logic` (all occurrence-expansion entries).
- Effort: L.
- Operator question blocking it: OQ-6 (overdue policy) for the `include_overdue` default.

### T-Q208 [S] Canonical budget period window (`domain/periods.py`)
- Findings: Q-003 (A-05, A-14, B-05).
- Tags: `[pre-v4-P3]`
- Depends on: none.
- Docs-first step: ADR (next free number, amends ADR-0041/0064/0085): half-open `[start, end)` fiscal window, no-anchor fallback is first-of-next-month; requirements note on the days-remaining divisor.
- Acceptance: failing tests first from `repro/A/output/inv_07*` (item on Nov 30: budget delta 0 vs `account_planned` 5000; divisor 11 vs 12) and `repro/B/b_router_logic.out` (plan router period differs for anchors on day 29-31); then `domain/periods.py` (`month_bounds`, `shift_month`, `fiscal_window`) used by `_resolve_anchor`, `account_planned.resolve_window`, analytics, forecast and `recurring_formula`; `web/routers/plan.py:68-251` logic moves to `services/budget.py:month_summary_for_picker`. The five month-bounds copies are deleted. Plan page covered by tests from T-Q252.
- Allowlist entries removed: per prevention.md §2 allowlist for `duplicate-logic` (period and month helpers) and for `layer-leak` (plan router period logic).
- Effort: M.
- Operator question blocking it: OQ-14 (payday divisor `max(..., 1)`, fiscal-month label) answers the edge-case behaviour.

### T-Q209 [S] Planned strip and formula-source sums are signed by direction
- Findings: Q-010 sign part (B-01, C-04, E-04).
- Tags: `[pre-v4-P3]`
- Depends on: none (the currency part is T-Q215).
- Docs-first step: none (ADR-0008 already defines direction-derived sign); CHANGELOG line.
- Acceptance: failing test first from `repro/B/b_router_logic.out` and `repro/E/fx_probe.out.json` (planned strip sums income and expense together today on PLN data); then move `_recurring_summary` and `planned_total_minor` (`web/routers/ledger.py:343-414`) into `services/ledger_totals.py` as `recurring_monthly_totals` / `planned_totals` using the direction sign helper; the template stops hard-coding `PLN` and `/ 100.0` (the currency-correct part lands in T-Q215/T-Q216).
- Allowlist entries removed: per prevention.md §2 allowlist for `layer-leak` and `duplicate-logic` (ledger router aggregates).
- Effort: S.
- Operator question blocking it: OQ-8 (can formula inputs mix currencies) shapes T-Q215, not this task.

### T-Q210 [S] Transit shape is validated on every write path
- Findings: Q-004 (B-02).
- Tags: none (`layer-leak`; not in the §9 class list).
- Depends on: none.
- Docs-first step: ADR-0008 amendment or short ADR (next free number): one `validate_transit_shape(direction, account, dest)` rule for create, update, planned and reconcile; resolves OQ-9 either way.
- Acceptance: failing tests first from `repro/B/b_transit_validation.out`, `repro/B/b_reconcile_transit.out` and `repro/verify/V1/v_b02.py` (POST persists, then /accounts, /today, /forecast return 500); then extract `validate_transit_shape` from `_promotion.validate_promotion` and apply it in create, update, planned and reconcile (`web/routers/transactions.py:263-430`, `planned.py`, `accounts.py`); optional one-off check that no existing prod row has a transit without a destination (read-only count on a copy, with explicit operator go).
- Allowlist entries removed: per prevention.md §2 allowlist for `layer-leak`.
- Effort: M.
- Operator question blocking it: OQ-9.

### T-Q211 [S] Recurring schedule anchor day and start-date boundary
- Findings: Q-006 (C-06, C-13).
- Tags: none (`date-boundary`).
- Depends on: none.
- Docs-first step: ADR amendment (recurrence anchor): `day_of_month` defaults to `start_date.day` at create, `advance_next_due` takes the rule and anchors on `rule.start_date`.
- Acceptance: failing tests first from `repro/C/repro_recurrence_boundaries.py` and `repro/verify/V1/v_c06_c13.py` (drift after a clamped month; occurrences before the start date); then the create-service default, `advance_next_due(rule, ...)` (`services/recurring.py:130,272-306`), and a one-off data-fix step only if OQ-5 shows affected prod rules (read-only check on a copy; prod write only on explicit in-session go).
- Allowlist entries removed: none.
- Effort: S-M.
- Operator question blocking it: OQ-5.

---

### Band 3 — Other High money and security

### T-Q212 [S] Canonical FX converter (`FxConverter`), one missing-rate policy, working live fetch
- Findings: Q-007 (G-01, A-06, C-02, C-17, F-06): live fetch never succeeds (no `base_url`), four converter copies with five missing-rate policies, network I/O during page renders.
- Tags: `[pre-v4-P3]` `[pre-first-non-PLN]`
- Depends on: none.
- Docs-first step: ADR (next free number, amends ADR-0006): cache-only converter per request, explicit missing-rate policy (raise or flag, never rate 1/500), client factory with `base_url=settings.fx_api_url`, rate validation (`rate > 0`; OQ-17 decides a `CHECK`); `docs/requirements.md` FX section; resolves OQ-13 (`services/fx.convert` dead or reserved).
- Acceptance: failing tests first from `repro/A/output/inv_10*`, `repro/C/repro_fx_fallback.py`, `repro/G/fx_client_no_base_url.py` and `repro/verify/V2/g01_fx_relative_url.py` (UnsupportedProtocol, zero requests leave the client); then one `FxConverter` in `services/fx.py` built by `fx.converter_for(conn, settings, today)`, the four copies (`web/today_data.py:124`, `web/routers/forecast.py:49`, budget and analytics converters) deleted, page renders do no network I/O (refresh is a separate scheduled path), and a test injects an `httpx` transport into the same client factory as production (also closes the FX part of Q-058).
- Allowlist entries removed: per prevention.md §2 allowlist for `duplicate-logic` (FX converter copies) and for `silent-fallback` (missing-rate fallbacks).
- Effort: M.
- Operator question blocking it: OQ-1 (Sev, confirms latency), OQ-13, OQ-17.

### T-Q213 [S] Analytics and forecast "spent" convert to base currency
- Findings: Q-008 (A-02, A-03).
- Tags: `[pre-v4-P3]` `[pre-first-non-PLN]`
- Depends on: T-Q212.
- Docs-first step: none (ADR-0006 already says aggregates convert to base); refer to the T-Q212 ADR.
- Acceptance: failing tests first from `repro/A/output/inv_01*` (budget spent 85717 = ledger 85717, analytics 52717) and `inv_03a*` (budget spent 43000 vs forecast 10000); then inject the canonical converter into `services/analytics.py:123-243` (`_spend_by_category`, `_twelve_month_averages`, `_income_vs_expense_monthly`, `_largest_items`) and `forecast._spent_so_far`, ideally via the shared `aggregates.sum_by_category(txns, to_base)` (T-Q227).
- Allowlist entries removed: per prevention.md §2 allowlist for `duplicate-logic` and `money-arith` (native-minor sums).
- Effort: S-M (S for spent, M for the overlay account).
- Operator question blocking it: none (OQ-15 for archived-category policy is in T-Q227).

### T-Q214 [S] One net-worth computation
- Findings: Q-009 (A-07).
- Tags: `[pre-v4-P3]` `[pre-first-non-PLN]`
- Depends on: T-Q212.
- Docs-first step: requirements note on what "net worth, all accounts" means (converted total plus per-currency breakdown).
- Acceptance: failing test first from `repro/A/output/inv_02*` (+1000 EUR: `fortune.net_base` 3443969 vs `today_data.fortune_base` and forecast day 0 3873969); then `services/fortune.compute_fortune(..., converter)` returns per-currency and converted totals; `web/today_data.py:105-143` and forecast day 0 consume it; the unused `fortune_base` is removed.
- Allowlist entries removed: per prevention.md §2 allowlist for `duplicate-logic` (net-worth copy).
- Effort: M.
- Operator question blocking it: none.

### T-Q215 [S] Ledger strips and formula-source sums convert across currencies
- Findings: Q-010 currency part (B-01, C-04, E-04, A-16).
- Tags: `[pre-v4-P3]` `[pre-first-non-PLN]`
- Depends on: T-Q209, T-Q212, T-Q216.
- Docs-first step: none (follows the T-Q212 ADR).
- Acceptance: failing test first from `repro/E/fx_probe.out.json` (strip unchanged after flipping the main rule account to EUR); then `recurring_monthly_totals` and `planned_totals` convert via the canonical converter and render in the base currency through the currency renderer; `web/templates/ledger/index.html:93-114` has no literal `PLN`.
- Allowlist entries removed: per prevention.md §2 allowlist for `duplicate-logic` (ledger strips) and `template-logic` (literal currency).
- Effort: S.
- Operator question blocking it: OQ-8.

### T-Q216 [S] One money renderer and a complete currency exponent table
- Findings: Q-011 (A-01, C-03, E-03), Q-029 (A-09, C-15).
- Tags: `[pre-first-non-PLN]`
- Depends on: none (can run before T-Q212).
- Docs-first step: ADR-0006 amendment: `domain/money.py:minor_to_major(amount, currency)` is the only conversion, rounding policy statement (shared with T-Q229), exponent table generated from ISO 4217 beside `ISO_4217_CURRENCIES`.
- Acceptance: failing tests first from `repro/A/output/inv_06*`, `repro/C/repro_jpy_display.py`, `repro/E/money_format_repro.py` (PLN equal, JPY 1,234.56 vs 123,456) and `repro/verify/V1/v_money.py`; then replace every hard-coded `/ 100.0` and two-decimal format in 40+ templates, charts and services (`today/index.html`, `_afford_preview.html`, `_upcoming.html`, `ledger/*`, `_MINOR_UNITS_PER_MAJOR`) with `money`/`money_num(currency)` or `minor_to_major`; unit test that every offered ISO code has an explicit exponent entry (ISK and the 20 other mis-scaled codes). Visual audit on all affected routes.
- Allowlist entries removed: per prevention.md §2 allowlist for `money-arith` (hard-coded division) and `template-logic` (inline money math).
- Effort: M.
- Operator question blocking it: OQ-1.

### T-Q217 [S] Reconcile with an income or expense category cannot misstate the balance
- Findings: Q-005 (C-01, F-07).
- Tags: none (`money-arith`; latent, never triggered on prod per OQ-4).
- Depends on: none.
- Docs-first step: requirements and ADR-0008 amendment: reconcile category must be ADJUSTMENT, INCOME with `delta > 0`, or EXPENSE with `delta < 0`; the docstring promise of coercion at `services/reconciliation.py:80-87` is removed.
- Acceptance: failing test first from `repro/C/repro_reconcile_and_parse.py` (B1, B2) and `repro/verify/V1/v_c01.py` (balance ends at 50000 for a typed target of 150000); then `CategoryDirectionMismatchError` in `reconcile` mapped to 422 in `web/routers/accounts.py:481-492`; the reconcile e2e/transport test asserts the resulting balance equals the typed figure.
- Allowlist entries removed: none.
- Effort: S.
- Operator question blocking it: OQ-9 (transit direction category), OQ-4 answered.

### T-Q218 [S] Gate the CI environments that hold prod-grade secrets
- Findings: Q-012 (H1-01, H1-06, H4-03). Also drop `restore-source.env` and the prod age identity from explore drills (H4-03).
- Tags: none (`ci-trust-boundary`; High).
- Depends on: none.
- Docs-first step: ADR (next free number; amends ADR-0099/0100): split by data sensitivity (new `prod-restore-read` environment with required reviewers and `main`-only branch policy for `restore-drill` only; drill and teardown environments keep no prod-read material); update the runbook. Re-check against current `terraform.yml`/`drill.yml` first (audit branch absorbed T-D158 changes).
- Acceptance: **GitHub environment and branch-policy changes are made by the operator in repository settings** (agents have no admin credentials; this is a settings change, not code). Verification by evidence: `repro/H1/collect_gh_config.sh` re-run and the new `gh_api/environments.json` committed under the audit folder or the runbook showing required reviewers and `main`-only policies; workflow edits (environment names, `scripts/ci/tf_env.py`) land as normal code with a test that no workflow outside `main` can reference the gated environments; rotate the secrets listed in OQ-24 if they were real prod values.
- Allowlist entries removed: none (not a code guard; the `ci-trust-boundary` workflow guard, if any, per prevention.md §2).
- Effort: M.
- Operator question blocking it: OQ-24 (Sev).

---

### Band 4 — Test-gap Highs

### T-Q219 [S] Coverage config stops excluding every line containing `...`
- Findings: Q-014 (F-12).
- Tags: none.
- Depends on: none.
- Docs-first step: none (tooling correction); CHANGELOG line. Note the coverage gate (90%) can move: record the new percentage in the changelog.
- Acceptance: failing check first: `repro/F/coverage_without_ellipsis_exclusion.txt` shows about 790 statements and 16 functions hidden; then change `pyproject.toml:194` to the anchored `"^\\s*\\.\\.\\.$"` (or delete it) and add tests for the 49 newly visible uncovered statements (triage OQ-28), keeping the gate at 90%.
- Allowlist entries removed: none.
- Effort: S (config) + M (tests).
- Operator question blocking it: OQ-28 (untriaged statements).

### T-Q220 [S] Differential invariant tests (Track A, 16 invariants)
- Findings: Q-013 (F-14).
- Tags: none.
- Depends on: none to start (harness); each invariant is switched from `xfail(strict=True)` to a plain test by the fix task named in its docstring (T-Q206..T-Q216).
- Docs-first step: none (tests only); mention the new test tree in `docs/requirements.md` §3.3 if tests are listed.
- Acceptance: `tests/integration/invariants/` with one file per `repro/A/inv_*.py` script, the multi-currency seed from `repro/A/harness.py` as a conftest fixture (PLN, EUR, JPY, one cached rate, one archived category, one linked planned row); the 8 invariants expected to fail are `xfail(strict=True)` with the fixing task id and flip as those tasks land; the 6 currently passing ones are guards. Done when no strict-xfail remains after T-Q216.
- Allowlist entries removed: none.
- Effort: L.
- Operator question blocking it: none.

### T-Q221 [S] Two-user and tombstone fixtures for the money services
- Findings: Q-015 (F-09, F-10).
- Tags: `[before-2nd-user]`
- Depends on: none.
- Docs-first step: none.
- Acceptance: add a two-user fixture and `world_with_tombstones` (soft-deleted and inactive rows) to `tests/unit/services/conftest.py`; one parametrised test per money service function (balance, budget, forecast, analytics, recurring, planned, upcoming, today); re-run `just mutate` on the 40 listed mutants (`user_id`/`conn` as `None`, `include_deleted`, `active_only`) and record that they are killed (rows 5, 7, 22, 30, 43, 51, 60, 78, 101 of `baseline/mutmut-real-gaps.md`).
- Allowlist entries removed: none.
- Effort: M.
- Operator question blocking it: OQ-15 (archived and inactive policy per service).

### T-Q222 [S] Kill the `recurring_formula` mutant cluster
- Findings: Q-016 (F-02).
- Tags: none.
- Depends on: T-Q221.
- Docs-first step: none.
- Acceptance: tests from the real-gaps rows 234-304 in `tests/unit/services/test_recurring_formula.py`: HALF_UP tie cases, two-user same-name fixture, a category with two items and one inactive source rule; the 71 mutants drop to equivalents only (record the survivor count).
- Allowlist entries removed: none.
- Effort: M.
- Operator question blocking it: none.

### T-Q223 [S] Kill the `forecast` mutant cluster
- Findings: Q-017 (F-03).
- Tags: none.
- Depends on: T-Q207 (kill after the refactor, not before) and T-Q221.
- Docs-first step: none.
- Acceptance: tests in `tests/unit/services/test_forecast.py` for the horizon-end boundary (item on the last day and one day later), skipped-by-override item followed by a valid one, income/expense/transit legs on one day with the exact day balance, and the FX arguments; the 102 survivors drop to equivalents only.
- Allowlist entries removed: none.
- Effort: L.
- Operator question blocking it: none.

### T-Q224 [S] Kill the `budget` mutant cluster
- Findings: Q-018 (F-04).
- Tags: none.
- Depends on: T-Q208, T-Q221.
- Docs-first step: none.
- Acceptance: tests in `test_budget.py` and `test_budget_fx.py`: `_month_range` and fiscal start for the first of the month and the anchor day; committed item on the last day and the day after; empty and one-item `_mean_minor`; FX converter behaviour; the 53 survivors drop to equivalents only.
- Allowlist entries removed: none.
- Effort: M.
- Operator question blocking it: none.

### T-Q225 [S] Kill the `recurring` mutant cluster; assert audit attribution
- Findings: Q-019 (F-05).
- Tags: none.
- Depends on: T-Q211, T-Q221.
- Docs-first step: none.
- Acceptance: tests in `test_recurring.py` read the `audit_log` row after `promote_recurring` (user, entity, operation, prev/new JSON; helper `audit_rows` in `tests/integration/auth/conftest.py:41`), override ordering, boundary days; the 50 survivors drop to equivalents only.
- Allowlist entries removed: none.
- Effort: M.
- Operator question blocking it: none.

### T-Q226 [S] Kill the `balance` mutant cluster; cover series and yearly grid
- Findings: Q-020 (F-08, F-27).
- Tags: none.
- Depends on: T-Q219 (functions become visible), T-Q221.
- Docs-first step: none.
- Acceptance: tests in `test_balance.py` for two accounts with one transaction each (balances and `AccountStats.account_id`/`base_balance`), include-deleted choice, `sparkline_points`, `balance_series`, and `budget.yearly_grid`; the 10 survivors drop to equivalents only.
- Allowlist entries removed: none.
- Effort: S-M.
- Operator question blocking it: none.

---

### Band 5 — Guard allowlist burn-down (by class)

### T-Q227 [S] Residual `duplicate-logic`: categories policy, direction sign, balance rule, aggregates and tier
- Findings: Q-030 (A-11, A-12), Q-032 (C-14), Q-036 (A-10), Q-075 (A-20, A-22).
- Tags: `[pre-v4-P3-rec]`
- Depends on: T-Q207, T-Q212, T-Q213.
- Docs-first step: ADR (next free number) fixing the policies once: archived categories and inactive rules (OQ-15), overdue items in the forecast (OQ-6), future-dated actuals in "current" balance (OQ-16), the single "monthly average" definition (OQ-7); requirements section update.
- Acceptance: failing tests first from `repro/A/output/inv_09*`, `inv_03c*`, `inv_04a*`; then `services/categories.py:expense_category_ids`, `balance.as_of_today`, one `domain` `signed_legs(direction, amount, account, dest)` with exhaustive `match` and `assert_never` (the six copies become one-line adapters), `services/aggregates.py` (`mean_minor`, `sum_by_category`) and one `pick_tier`.
- Allowlist entries removed: per prevention.md §2 allowlist for `duplicate-logic` (all remaining entries in `services/` and `domain/`).
- Effort: M.
- Operator question blocking it: OQ-6, OQ-7, OQ-15, OQ-16.

### T-Q228 [S] `repo-bypass`: undo endpoints and audit-free repository helpers
- Findings: Q-024 (B-03, B-11, C-16, H2-03), Q-049 (B-10).
- Tags: `[pre-v4-P3-rec]` (raw SQL in routers on `audit_log` and `planned_transactions` would be missed by the Phase 3 repository sweep).
- Depends on: T-Q204 (transaction boundary).
- Docs-first step: ADR (next free number, supersedes the relevant part of ADR-0019 text): undo is an audited action (OQ-11), undo targets the specific audit row, and `user_preferences` writes are audited or explicitly exempt (OQ-10 on NULL `ip`/`session_id`/`user_agent`).
- Acceptance: failing tests first from `repro/B/b_undo_replay.out` and `repro/H2/h2_02_undo_chain.py` (replays the latest audit row of any operation, restores partial state, writes no audit entry); then SQL deleted from `web/routers/planned.py:112-181` and `web/routers/recurring.py:470-545` in favour of repository/service functions; the three helpers move to `repositories/_unaudited.py`, imported only by `services/recurring.py` (architecture test beside `tests/architecture/test_user_id_filter.py`).
- Allowlist entries removed: per prevention.md §2 allowlist for `repo-bypass` (all entries).
- Effort: M.
- Operator question blocking it: OQ-10, OQ-11.

### T-Q229 [S] `clock` and rounding policy
- Findings: Q-031 (A-13, C-08, F-21), Q-076 (C-18, C-19).
- Partial: ledger tests fixed in T-Q-TB1 (planned seed date is now `date.today()`-relative).
- Tags: none.
- Depends on: none.
- Docs-first step: ADR (next free number): `budget_planner/clock.py` with `utc_now()`, `today_local(settings)` and an injectable override; services never call `date.today()`; ADR-0006 amendment for the single rounding policy (`round_div` HALF_EVEN, `round_scaled`) and retention timestamp format (`utc_now_iso`). Resolves OQ-3 (zoneinfo in the image) and OQ-18 (only Europe/Warsaw).
- Acceptance: failing tests first from `repro/A/output/inv_08*` and `repro/C/repro_clock.py` (month-end and Warsaw midnight window); then replace the 16-18 `date.today()` sites (`baseline/clock-sites.txt`), add a `today` FastAPI dependency, route time-dependent tests and the visual suite through the override, unify the rounding helpers (`domain/money.py`, `services/recurring_formula.py`, `services/fx.py`, `services/today.py`, `web/routers/today.py`) and the retention comparison.
- Allowlist entries removed: per prevention.md §2 allowlist for `clock` (all entries) and for `money-arith` (rounding variants).
- Effort: M.
- Operator question blocking it: OQ-3, OQ-18.

### T-Q230 [S] Account archive refuses or cascades when references exist
- Findings: Q-026 (C-05).
- Tags: none.
- Depends on: T-Q228 (service/transaction conventions) optional.
- Docs-first step: requirements and ADR-0019 note: an account with a non-zero balance or live rules/planned rows cannot be archived (409 with message), or they are deactivated in the same transaction.
- Acceptance: failing test first from `repro/C/repro_deleted_refs.py` and `repro/verify/V1/v_c05.py` (promotion posts to a deleted account); then `services/accounts.archive_account()` used by `web/routers/accounts.py:348-354`, and promotion refuses a deleted target.
- Allowlist entries removed: per prevention.md §2 allowlist for `scoping-gap`.
- Effort: M.
- Operator question blocking it: none.

### T-Q231 [S] Test-suite tripwire against touching the prod DB
- Findings: Q-060 (F-20).
- Tags: none.
- Depends on: none.
- Docs-first step: none (testing hygiene; mention in CLAUDE.md "Databases" only if the operator approves the edit).
- Acceptance: failing meta-test first (a test that sets no DB URL must not resolve to `data/budget.sqlite`); then an autouse session fixture in `tests/conftest.py` pointing `BUDGET_DATABASE_URL` to a session temp path, unsetting `BUDGET_PLANNER_ADMIN_*`, and asserting the resolved path is not `data/budget.sqlite`.
- Allowlist entries removed: per prevention.md §2 allowlist for `scoping-gap` (test isolation entries, if any).
- Effort: S.
- Operator question blocking it: OQ-29 (Sev, Medium to High).

### T-Q232 [S] Closing gate: all guard allowlists empty, guards strict
- Findings: closes the loop for Q-001..Q-080 with a guard.
- Tags: `[pre-v4-P3]` check (verify before v4 Phase 3).
- Depends on: T-Q206, T-Q207, T-Q208, T-Q209, T-Q210, T-Q212, T-Q213, T-Q214, T-Q215, T-Q216, T-Q227, T-Q228, T-Q229, T-Q230, T-Q241, T-Q242, T-Q243, T-Q258.
- Docs-first step: update `prevention.md` status and the CLAUDE.md "Code conventions" pointer if wording changes (operator reviews CLAUDE.md edits).
- Acceptance: every allowlist described in prevention.md §2 is empty and the guards run in strict mode in `just ci` and pre-commit; a deliberately introduced violation (one per class) fails; the T-Q16 dry run is repeated and recorded.
- Allowlist entries removed: all remaining entries, any class.
- Effort: S.
- Operator question blocking it: none.

---

### Band 6 — Medium

### T-Q233 [P] One input parser and bounded parameters (no 500 on bad input)
- Findings: Q-023 (A-08, C-10, A-19, D-02, H3-03).
- Tags: none.
- Depends on: none.
- Docs-first step: ADR (next free number) or requirements §6 note: `parse_amount_str` is the only amount parser (no exponents, `NaN`, non-ASCII digits, magnitude above `MAX_MINOR`), shared `web/params.py` for date/year/month/id parsing.
- Acceptance: failing tests first from `repro/A/output/inv_05*`, `repro/verify/V1/v_c10.py`, `repro/verify/V2/d02_overflow.py`, `repro/H3/h3_csrf_preauth_output.txt` (C4), `repro/C/repro_input_boundaries.py` (each input returns 422/400, never 500); then replace the seven parsers.
- Allowlist entries removed: per prevention.md §2 allowlist for `duplicate-logic` (amount parsers).
- Effort: M.
- Operator question blocking it: none.

### T-Q234 [P] Remove N+1 query storms on /accounts and /forecast
- Findings: Q-033 (C-07).
- Tags: none.
- Depends on: T-Q207 (forecast loads once).
- Docs-first step: none (performance; add a query-count budget note to requirements §3.3 if the operator wants it).
- Acceptance: failing test first from `repro/C/query_counts.py` and `repro/verify/V1/v_c07.py` (about 2900 and 2800 statements per request) as an `assert_max_queries(route, n)` pytest helper; then `balance.balance_series` with one query and a running sum, and rules/overrides/planned rows/tiers loaded once and passed down.
- Allowlist entries removed: none.
- Effort: M.
- Operator question blocking it: none.

### T-Q235 [P] Bound work per request
- Findings: Q-035 (C-12, D-04, D-05).
- Tags: none.
- Depends on: none.
- Docs-first step: none (ADR-0081 aligns); named maximums documented in requirements.
- Acceptance: failing tests first (page size clamp, oversized body and field lengths rejected, `/ready` does not run a full `integrity_check` per unauthenticated probe); then `COUNT`/`SUM` repository functions for counts and balances (`web/routers/ledger.py:68,377-390`, `services/balance.py:77-82`), `page_size` clamp, field lengths in drafts, `/ready` uses a cheap check.
- Allowlist entries removed: none.
- Effort: M.
- Operator question blocking it: none.

### T-Q236 [P] HTMX error flashes swap; one event and toast contract
- Findings: Q-037 (E-01), Q-038 (A-18, E-02, E-07).
- Tags: none.
- Depends on: none.
- Docs-first step: ADR (next free number) or `docs/requirements.md` frontend note: `web/htmx.py` owns `Event` constants, `invalidate(response, *domains)` and `toast_payload(variant, message, undo=...)`; resolves OQ-27.
- Acceptance: failing tests first from `repro/E/htmx_matrix.py` / `htmx_matrix.out.md` (404/409/500 flash not swapped; four `*-stale` events with no listener); then one global `htmx:beforeSwap` handler in `app-init.js` and the contract module; the emitter/listener orphan guard per prevention.md §2 for `htmx-contract` is switched to strict. `frontend-visual-audit` on affected routes.
- Allowlist entries removed: per prevention.md §2 allowlist for `htmx-contract` (all entries).
- Effort: S-M.
- Operator question blocking it: OQ-27.

### T-Q237 [P] Budget numbers in templates come from `MonthSummary`
- Findings: Q-039 (E-05, A-15).
- Tags: none.
- Depends on: T-Q208.
- Docs-first step: none.
- Acceptance: failing test first: a rendered Today/Plan/Budget page shows the same left-per-day and percent-used as the service value (float template arithmetic removed); then add `left_per_day_minor`, `spent_pct`, `committed_pct`, `remaining_after` to `MonthSummary` (or a `BudgetView`) and delete the template `set` blocks (`today/index.html:28-36`, `plan/_budget_tab.html`, `_period_header.html`, `budget/index.html`). Visual audit.
- Allowlist entries removed: per prevention.md §2 allowlist for `template-logic`.
- Effort: M.
- Operator question blocking it: none.

### T-Q238 [P] Signed-image identity pinned to `main`; stricter skip classifier
- Findings: Q-040 (H1-02), Q-042 (H1-04, H1-05).
- Tags: none (`ci-trust-boundary`).
- Depends on: none (re-check at remediation: `terraform.yml`, `host_release.py`, `main.tf` changed after the audit SHA).
- Docs-first step: ADR amendment to ADR-0099/0100/0121: verified identity is `build.yml@refs/heads/main` or a release tag; the skip classifier allowlist is docs only.
- Acceptance: failing tests first from `repro/H1/gate_and_signing_probe.out` and `repro/H1/classifier_probe.out` (any-ref signature accepted; `.claude/` and `tests/` treated as inert); then `identity_regexp` pinned in `terraform/modules/compute/user_data.tf:118` (drill hosts via a variable), rollback ancestry check in `terraform/host/agent/bp_agent.py`, `scripts/ci/drill_gate_skip.py` shrunk and verdict bound to the head SHA; unit test greps `.github/` and `scripts/ci/` for paths under allowlisted dirs.
- Allowlist entries removed: per prevention.md §2 allowlist for `ci-trust-boundary`.
- Effort: S.
- Operator question blocking it: OQ-24 (rollback to `sha-*` tags).

### T-Q239 [P] Merge gate becomes tamper-resistant (operator GitHub settings)
- Findings: Q-041 (H1-03).
- Tags: none.
- Depends on: none (pairs with T-Q218).
- Docs-first step: ADR amendment (ADR-0099): required workflows from `main`, `integration_id` on required checks, CODEOWNERS over `.github/`, `scripts/ci/`, `terraform/`.
- Acceptance: **ruleset and branch-protection changes are made by the operator** (`workflows` rule, `integration_id` 15368 on each required context, required review for CODEOWNERS paths); `.github/CODEOWNERS` lands as code; evidence is the refreshed `repro/H1/gh_api/ruleset_protect_main.json`. Self-approved merge is accepted risk unless a second reviewer or bot is feasible (OQ-24).
- Allowlist entries removed: none.
- Effort: S.
- Operator question blocking it: OQ-24.

### T-Q240 [P] Dev-dependency provenance and CI/pre-commit parity
- Findings: Q-043 (G-07), Q-044 (G-05, G-06).
- Tags: none.
- Depends on: none.
- Docs-first step: ADR-0120 amendment: which checks run in PR CI versus pre-commit (OQ-22), tool versions come from `uv.lock`.
- Acceptance: first verify `httpx2` provenance (`git log -S httpx2`, PyPI page); if illegitimate this is an incident and goes to the operator; then remove `httpx2` and the plotly overrides (`pyproject.toml:44,136,172`) and re-lock; run hooks as `repo: local`, `language: system`, `entry: uv run <tool>`; CI runs ruff format, bandit, detect-secrets, tailwind-check or documents why not; pin `uv` in `ci.yml`.
- Allowlist entries removed: none.
- Effort: S.
- Operator question blocking it: OQ-19 (Sev), OQ-22.

### T-Q241 [S] CRUD service layer per entity
- Findings: Q-045 (B-04).
- Tags: `[pre-v4-P3-rec]`
- Depends on: T-Q210 (validation lives there), T-Q228.
- Docs-first step: ADR (next free number, extends ADR-0021): one CRUD service per entity (`transactions`, `planned`, `accounts`, `recurring_rules`, `budget_overrides`); resolves OQ-12 (before or after the Sourdough redesign, ADR-0107).
- Acceptance: failing architecture test first (routers do not import repositories; allowlist lists the current 13 routers and 6 writing routers); then one service per entity, routers call services only.
- Allowlist entries removed: per prevention.md §2 allowlist for `layer-leak` (router-to-repository imports).
- Effort: L.
- Operator question blocking it: OQ-12.

### T-Q242 [S] Split oversized modules
- Findings: Q-046 (B-09).
- Tags: none.
- Depends on: T-Q241, T-Q207.
- Docs-first step: none (follows the table 2.4 splits in `tracks/B-layering.md`).
- Acceptance: `web/routers/recurring.py` and `services/forecast.py` under 800 lines; no router function worse than complexity C once the E and D blocks are gone; xenon introduced at `--max-absolute C` in `just lint`.
- Allowlist entries removed: per prevention.md §2 allowlist for `oversized-module`.
- Effort: L.
- Operator question blocking it: none.

### T-Q243 [S] Break the recurring import cycle; keyword-only service signatures
- Findings: Q-047 (B-06, B-12, A-21), Q-048 (B-08).
- Tags: none.
- Depends on: T-Q211.
- Docs-first step: none (ADR-0021 covers); update the import-contract config.
- Acceptance: pure scheduling code (`generate_occurrences`, `advance_next_due`, `first_due_on_or_after`, `occurrence_in_month`, `_STEP_MONTHS`, `_build_lookup_stub`) moves to `domain/recurring_schedule.py`; nine `PLC0415` lazy imports and the `next_due` seeding copies removed; eight service signatures keep `conn, user_id` positional and the rest keyword-only (about 12 callers).
- Allowlist entries removed: per prevention.md §2 allowlist for `import-cycle` and `wide-signature`.
- Effort: M.
- Operator question blocking it: none.

### T-Q244 [P] Remove or re-wire routes without a caller
- Findings: Q-050 (G-13).
- Tags: none.
- Depends on: none.
- Docs-first step: decide per route (re-wire the ADR-0056 live preview in the entry form or the ADR-0107 redesign, or delete route, template and tests); update `docs/requirements.md` and ADR-0056 status accordingly.
- Acceptance: the four dead routes deleted with their tests; the formula preview either wired and covered by an e2e, or deleted; the htmx orphan guard stays green.
- Allowlist entries removed: per prevention.md §2 allowlist for `dead-code` and `htmx-contract` (affected entries).
- Effort: S (M for the re-wire).
- Operator question blocking it: none.

### T-Q245 [P] ADR status, bodies, and project-instruction drift
- Findings: Q-051 (G-02, G-03, G-04), Q-052 (G-16, G-15), Q-053 (G-08, G-09, D-13).
- Tags: none.
- Depends on: none.
- Docs-first step: this task is the docs change; CLAUDE.md and `.claude/skills/**` edits are reviewed by the operator before merge (implementation_plan §7.3).
- Acceptance: 13 implemented ADRs flipped to Accepted, ADR-0106/0107 to Accepted-with-implementation-pending (OQ-23), amendments reflected in the index, duplicate numbers 0105 and 0121 either renumbered or grandfathered with an architecture test of unique numbers; ADR-0002/0023/0026/0036/0052/0057 corrected with dated addenda; CLAUDE.md, the orchestrator skill and requirements §3 and §6.7 name real paths and the real stack.
- Allowlist entries removed: per prevention.md §2 allowlist for `doc-drift` (ADR-number collision entries).
- Effort: M.
- Operator question blocking it: OQ-23.

### T-Q246 [P] Reconcile task status with CHANGELOG and ADRs
- Findings: Q-054 (G-10).
- Tags: none.
- Depends on: T-Q245 (OQ-23 answer).
- Docs-first step: this is the docs change.
- Acceptance: listed rows in `docs/plans/v1/tasks.md`, `docs/plans/v3/tasks.md` reconciled; `docs/plans/v2/tasks.md` closed as superseded by ADR-0107 or its open rows triaged.
- Allowlist entries removed: none.
- Effort: M.
- Operator question blocking it: OQ-21.

### T-Q247 [P] Kill survivors in the non-priority modules
- Findings: Q-055 (F-11).
- Tags: none.
- Depends on: T-Q213 (analytics), T-Q221.
- Docs-first step: none.
- Acceptance: re-triage the sampled rows of `baseline/mutmut-real-gaps.md` (rows 310-516) first; then module by module (`analytics`, `today`, `users`, `planned`, `upcoming`, `export`, `replication_health`, `preferences`) using the suggested-killing-test column; record per-module score in `baseline/mutmut.txt` follow-up.
- Allowlist entries removed: none.
- Effort: L.
- Operator question blocking it: none.

### T-Q248 [P] Browser e2e drives real forms; ledger pagination race
- Findings: Q-056 (F-15), Q-057 (F-16).
- Tags: none.
- Depends on: none.
- Docs-first step: none.
- Acceptance: the four e2e tests (`test_add_transaction_flow`, `test_reconcile_flow`, `test_recurring_promote_flow`, `test_set_budget_flow`) drive the visible forms with role locators and keep `request.post` only for seeding; `hx-sync="#ledger-table:replace"` on the ledger form and button, and the pagination test awaits the response deterministically. Run `uv run pytest tests/e2e -q --no-cov` before the PR.
- Allowlist entries removed: none.
- Effort: M.
- Operator question blocking it: none.

### T-Q249 [P] Test transport matches production
- Findings: Q-058 (F-17).
- Tags: none.
- Depends on: T-Q212.
- Docs-first step: none.
- Acceptance: tests for CSRF run without the header auto-attached (an extra test class), the secure-cookie path is exercised, and FX tests inject a transport into the production client factory (`tests/unit/services/test_fx.py`, `test_forecast*`).
- Allowlist entries removed: none.
- Effort: M.
- Operator question blocking it: none.

### T-Q250 [P] Strengthen status-only HTTP tests and the vacuous rollback test
- Findings: Q-059 (F-18, F-19).
- Tags: none.
- Depends on: none.
- Docs-first step: none.
- Acceptance: each success-path test in `test_budget.py`, `test_recurring.py`, `test_categories.py`, `test_planned.py`, `test_accounts.py` reads back through the repository or rendered value; each rejection test asserts the row count is unchanged; the reconciliation rollback test fails a middle write, not the only write; weak-assert scan (`repro/F/weak_assert_scan.py`) count drops to zero for these files.
- Allowlist entries removed: none.
- Effort: M.
- Operator question blocking it: none.

### T-Q251 [P] Visual suite becomes a trustworthy check
- Findings: Q-061 (F-22).
- Tags: none.
- Depends on: none.
- Docs-first step: ADR-0027 amendment (scheduled visual workflow, perceptual threshold, missing baseline is a failure in CI).
- Acceptance: scheduled workflow on a pinned Playwright image, `max_diff_pixel_ratio`, a missing baseline fails in CI, baselines regenerated after the last template change, and a pre-commit check that baselines change when `templates/` change.
- Allowlist entries removed: none.
- Effort: M.
- Operator question blocking it: none.

### T-Q252 [P] Plan page and `monthly_projection` get tests; `format_money` zero
- Findings: Q-021 (F-13), Q-022 (F-01).
- Tags: none.
- Depends on: T-Q208 (so tests pin the fixed window).
- Docs-first step: none.
- Acceptance: new `tests/integration/web/test_plan.py` for `/plan?tab=forecast` (series length, first and last month label, one end balance), `/plan?month=` for a past and a future month (committed zero, period bar dates), the Year tab; `test_format_money_zero` parametrised over PLN and JPY (`0.00 PLN`, `0 JPY`) and `format_money(-1, "JPY")`; fix the `-0.00` rendering if the test shows it.
- Allowlist entries removed: none.
- Effort: M.
- Operator question blocking it: none.

---

### Band 7 — Low

### T-Q253 [P] Session and passkey hardening
- Findings: Q-062 (H3-02, H3-04, H3-06, H3-08).
- Tags: none.
- Depends on: T-Q203.
- Docs-first step: ADR amendment (ADR-0078/0079): single-use challenge nonce table, passkey revoke ends its sessions (OQ-26), CSRF token binding decision.
- Acceptance: failing tests first from `repro/H3/h3_passkey_ceremonies_output.txt` (P1, P2, P7), `h3_rotation_race_output.txt`, `h3_csrf_preauth_output.txt` (C1, C2); then fixes (`DELETE ... RETURNING` at finish, no re-set of the rotated token by an in-flight request, no revoke on `new == stored == 0`).
- Allowlist entries removed: none.
- Effort: M (S-M each; M for H3-02 and H3-08).
- Operator question blocking it: OQ-26 (Sev for H3-04).

### T-Q254 [P] 500 responses carry security headers; CSP from the app; unenforced surfaces
- Findings: Q-064 (D-03, D-09), Q-065 (D-08, E-11), Q-066 (D-07, D-12).
- Tags: none.
- Depends on: T-Q203 (proxy trust).
- Docs-first step: ADR amendment (ADR-0036/0072): CSP emitted by `SecurityHeadersMiddleware` with an app-generated nonce and Caddy as second layer; `BUDGET_TRUSTED_HOSTS` enforced; `/docs`, `/openapi.json`, `/dev/components` off in production (OQ-20).
- Acceptance: failing tests first (forced 500 asserts all headers and no-store; client-supplied nonce ignored; non-allowed Host rejected; `/docs` returns 404 in production); then an outermost pure-ASGI middleware, nonce generation, `TrustedHostMiddleware`, `docs_url=None`, conditional `dev_components`, and removal of the dead `csrf_token` and `csp_nonce` stubs; log redaction covers exception text.
- Allowlist entries removed: none.
- Effort: M.
- Operator question blocking it: OQ-20.

### T-Q255 [P] Infra pinning and release-workflow hardening
- Findings: Q-067 (D-11), Q-068 (D-10, H1-09, H1-10, H4-04), Q-069 (H1-07, H1-08), Q-078 (H4-02), Q-079 (H4-05), Q-080 (H4-06).
- Tags: none.
- Depends on: T-Q218 and T-Q239 (settings), H4 drill result for D-11 (done, see Q-067).
- Docs-first step: ADR-0101/0099 amendments (where the port control sits; pinning policy).
- Acceptance: Caddy/Litestream/base image by `@sha256:` digest, `uv`, tailscale and cloud-init versions pinned; Actions repo settings (`sha_pinning_required`, `allowed_actions: selected`) set by the operator; `permissions: contents: read` default on `ci.yml` and the release `ci` job, `.security-allowlist.yml` read from `origin/main` and passed via `env:` with a validated pattern; drill ports bound to the tailnet address or filtered in `DOCKER-USER`. Terraform changes go through the pipeline only; no prod apply from a laptop.
- Allowlist entries removed: per prevention.md §2 allowlist for `dependency` and `ci-trust-boundary`.
- Effort: S.
- Operator question blocking it: OQ-24 (Tailscale ACL parity), OQ-32.

### T-Q256 [P] Frontend duplication: card utilisation and passkey JS
- Findings: Q-070 (E-06, E-09), Q-071 (E-10).
- Tags: none.
- Depends on: none.
- Docs-first step: none.
- Acceptance: one `credit_utilisation(card)` in the accounts view model, templates fail under StrictUndefined instead of defaulting (`10`, `'PLN'`); `passkeys.js` extracts `runAssertion` and a shared `csrf.js`, logs `err.name` to `console.debug`. Visual audit on `/accounts` and the login flow.
- Allowlist entries removed: per prevention.md §2 allowlist for `template-logic`.
- Effort: S.
- Operator question blocking it: none.

### T-Q257 [P] Dead code and silent router import
- Findings: Q-072 (G-17, E-08, plus the E-track alias in findings.md Details), Q-073 (C-20, G-14).
- Tags: none.
- Depends on: T-Q244.
- Docs-first step: none (docs list of legacy redirects updated).
- Acceptance: legacy redirects, `routers/analytics.py`, `/afford` and `/budget-legacy` aliases, test-only symbols and `bulk-select.js` removed with `_ROUTER_NAMES`/`extra_paths` updated; `web/app.py:236-247` becomes explicit imports and `include_router` calls (a missing router now fails at startup, test asserts all routers are registered).
- Allowlist entries removed: per prevention.md §2 allowlist for `dead-code`.
- Effort: S.
- Operator question blocking it: none.

### T-Q258 [P] Small layering and functional-first deviations
- Findings: Q-074 (B-13, B-14, B-15, B-16).
- Tags: none.
- Depends on: T-Q241.
- Docs-first step: ADR-0021 sentence on framework classes and memo parameters.
- Acceptance: `ContextVar` for the transaction depth (`repositories/_shared.py:98`), `MappingProxyType` for `_EMPTY_TERM_INPUT`, the two SQL queries in `services/accounts.py` moved to repositories, the five `web -> db` import-contract breaks removed, and docstrings corrected to the soft-delete rule.
- Allowlist entries removed: per prevention.md §2 allowlist for `layer-leak` and `import-cycle` (contract entries).
- Effort: S.
- Operator question blocking it: none.

### T-Q259 [P] Test hygiene
- Findings: Q-077 (F-23, F-24, F-25, F-26).
- Tags: none.
- Depends on: T-Q231.
- Docs-first step: none.
- Acceptance: delete the e2e landmarks test and one of the duplicate promotion tests; the 15 permanently skipped pre-redesign tests deleted or restored; `conn` and an autouse fast-bcrypt fixture moved to `tests/conftest.py` with URLs through `sqlite_url`; investigate the `test_landmarks_present[/today]` flake (OQ-28).
- Allowlist entries removed: none.
- Effort: S.
- Operator question blocking it: OQ-28.
