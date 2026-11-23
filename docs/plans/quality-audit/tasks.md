# Post-v3 Code-Quality Audit — Tasks

> Flat index. The method for each task is in [implementation_plan.md](implementation_plan.md).
> Legend: `[P]` parallel-safe within its phase, `[S]` sequential, `→ T-Qxx` depends on upstream task.
> Acceptance = output file complete against its checklist + the guardrails in implementation_plan §11 respected + `✅` prefix added here.
> **Complete 2026-11-22 (T-Q232 closing gate).** Remaining debt: the 83 `template_logic.toml` entries, owned by the ui-redesign plan (ADR-0130 carve-out).

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

### ✅ T-Q15 [S] Apply controls → T-Q14
- Docs first: prevention ADR(s) (next free numbers; the mutation-testing ADR is **not** 0095), requirements §3.3 / §3 tooling, then CLAUDE.md, skills and briefs.
- Guards in allowlist mode with CI green. Mutmut setup committed (`pyproject`, `just mutate*`, `.gitignore`, fixture fixes). Nightly job decided.
- CLAUDE.md and skill edits reviewed by the operator.
- T-Q15c guidance drafted (CLAUDE.md, orchestrator-mode and frontend-visual-audit skills, active plan handoff templates; summary `docs/plans/quality-audit/T-Q15c-review.md`) — operator-approved and merged 2026-11-20.
- **T-Q15b tooling landed** (2026-11-20, ADR-0130/ADR-0131): mutmut + import-linter pinned, `[tool.mutmut]`, `[tool.importlinter]` (40 allowlisted imports), TID251 clock ban (per-file allowlist) and `PGH`, `clock.py` scaffold, `just mutate*`/`guards`/`lint-imports`, `scripts/mutate_report.py`, `scripts/check_github_settings.py`, CI runs `pre-commit run --all-files` (`SKIP=pytest-fast`), weekly `mutation.yml`. Timings: `baseline/precommit-timing.md`. Open: T-Q15a guards, T-Q15c CLAUDE.md/skills.
- Progress: **T-Q15a guards landed** (2026-11-20, ADR-0130): `tests/architecture/` exact-ratchet guards G1-support, G2, G4, G5, G6, G7 (invariants registry), G7b, G9, G10, G12, G14, G15, G16, G17-repo and G18 to G27 with `allowlists/*.toml`, `canonical_modules.toml` (S1), S3 isolation registry; `repro/allowlist_by_qid.py` lists entries per Q-id and epic. T-Q15b, T-Q15c and T-Q15d landed later the same day; T-Q15 is done.
- **T-Q15d fix-ups** (2026-11-20): G18 ignores dunder same-name rows (self-test; allowlist unchanged), `clock.py` row is `[[permanent]]` (ADR-0130 §4; burn-down entries 20 to 19), pre-commit `djlint-jinja` fixed to check `.html` templates (was a silent no-op), timings in `baseline/precommit-timing.md`.

### ✅ T-Q16 [S] Prevention dry run → T-Q15
- A fresh agent working on a synthetic duplication-prone task uses the canonical module, or the guard trips. Result recorded. `just ci` green. **Deliverable 2 done.**
- Done 2026-11-20 (P5 `just ci` pending CI): dry run V1-V4 and re-runs V1b/V2b recorded in `prevention.md` §7; controls: registry statuses with flip guard (copies listed), G30 private-import ratchet (8 entries), G31 frontend audit record, G27 non-money scope, `just guards` includes user-isolation, sharper messages, CLAUDE.md Interim rule.

## Phase 5 — Remediation backlog → T-Q12 (may overlap T-Q13…T-Q16)

### ✅ T-Q17 [S] Write the remediation backlog
- Done 2026-11-20: final backlog in the Remediation section below, 75 tasks (T-Q201 to T-Q275) in 8 bands plus an 18-wave orchestrator plan. Every Q-id (Q-001 to Q-080) and every epic (E01 to E16) is covered; every burn-down allowlist entry (613 entries, 1255 violations) and every `suppressions.toml` ceiling (87) is owned by exactly one task, with the per-guard reconciliation table in the section. Operator directive of 2026-11-20 applied: full compliance, all allowlists to zero.
- Accepted findings turned into `T-Q2xx` tasks in this file, ordered Critical → High → allowlist burn-down → Medium → Low. Each task lists its finding ids, ADRs, acceptance criteria and the allowlist entries it removes.
- Tasks that must be ✅ before v4 Phase 3 are tagged `[pre-v4-P3]`: Critical/High `duplicate-logic`, `repo-bypass` and `scoping-gap` (implementation_plan §9).

---

## Remediation (T-Q2xx)

Source: [findings.md](findings.md) (80 Q-ids, 0 Critical, 20 High, 41 Medium, 19 Low; accepted in full by the operator, T-Q12), [compliance-inventory.md](compliance-inventory.md) sections 15 and 16 (epics E01 to E16), [prevention.md](prevention.md), ADR-0130 (zero-violation policy) and ADR-0131. Method: [implementation_plan.md](implementation_plan.md) sections 5, 7.3, 8, 9. Execution follows the normal handoff checklist (CLAUDE.md), one task at a time or in orchestrator mode using the wave plan below.

**Final backlog (T-Q17 done 2026-11-20): 75 tasks, T-Q201 to T-Q275.** Band 0 (before a second user, and Highs that bite current PLN data): 12; Band 1 (before the first non-PLN account): 6; Band 2 (pre-v4-Phase-3 epics): 16; Band 3 (test-gap Highs and test infrastructure): 8; Band 4 (full-compliance burn-down): 11; Band 5 (Medium): 15; Band 6 (Low): 6; Band 7 (closing gate): 1. Sizes: S 21, M 40, L 14. T-Q201 to T-Q259 keep their draft ids; T-Q260 to T-Q275 are new (full-compliance epics and open items). Mechanical checks (all pass): every Q-id Q-001 to Q-080 appears in at least one task `Findings` line; every epic E01 to E16 has at least one task; every burn-down allowlist entry is owned by exactly one task and the per-guard sums equal the allowlist totals (tables below).

**Operator directive (2026-11-20), as implemented.** All 80 findings accepted; converge to full compliance with every principle, not only bug-causing violations: every guard allowlist reaches zero (ADR-0130 section 1). Prod facts that set the order: PLN-only today, single user with more users soon (scoping and abuse controls come before the second user), no non-PLN account yet (FX and currency fixes before the first one).

**Ordering rationale.** Band 0: everything that must precede a second user (T-Q201 to T-Q205, T-Q221) and the money-correctness Highs that are live on PLN data today (Q-002 hotfix T-Q206, Q-003 T-Q208, Q-010 sign part T-Q209, Q-004 T-Q210, Q-006 T-Q211), plus the operator-gated ungated-environments fix (T-Q218). Band 1: the FX and currency chain that must be done before the first non-PLN or zero-decimal account (T-Q212 to T-Q216) and the latent reconcile bug (T-Q217). Band 2: the epics inventory section 16 marks "before v4 Phase 3" in its sequencing order (E12, E10, E08, E09, E01, E11, E06, E07, with E03, E05, E14 in parallel). Band 3: the test-gap Highs that lock the fixes in. Band 4: the remaining full-compliance epics (E02, E13, E15, E16, E03 and E14 residue, E04). Band 5 and 6: Medium and Low findings with no allowlist entries. Band 7: the closing gate. Band order is priority; the wave plan is the execution order after dependencies and merge-conflict constraints.

**Allowlist convention (replaces the draft convention).** `tests/architecture/allowlists/*.toml` are exact ratchets: an entry's `count` must equal the live violation count, so a task that removes violations must delete or decrement the entries in the same commit. Each burn-down entry (`[[entry]]`, and each `[ceilings]` line in `suppressions.toml`) has exactly one **owning task**: the one named under "Removes allowlist entries" (guard: violations, with the entry count). The owner is responsible for bringing its slice to zero. Another task that deletes or rewrites the same code (for example a router split) decrements the entries it touches incidentally; the owner re-reads its slice with `uv run python docs/plans/quality-audit/repro/allowlist_by_qid.py --guard <guard>` at start and removes what remains. `[[permanent]]` and `[[framework]]` entries are not burn-down and have no owner (adding one needs an ADR-0130 amendment).

**Task fields.** Each task lists: Findings (Q-ids and inventory ids), Epic (compliance-inventory section 16), Band, Size (S under a day of agent work, M one to two, L larger and splittable), Tags, Depends on, Docs-first step, Acceptance, Removes allowlist entries, Done when. Titles carry `[S]` (sequential, one agent) or `[P]` (parallel-safe within its wave) as in the file legend; this is not the size.

**Acceptance convention (applies to every task).** Docs-first step done and committed first (CLAUDE.md change policy). A failing test that reproduces the finding is written first and committed or staged before the fix; where a `docs/plans/quality-audit/repro/` script exists, it is ported into `tests/` (integration or invariant test) and the original script stays as evidence. Pre-commit hooks green; frontend-touching tasks run `frontend-visual-audit` (desktop 1440, tablet 1024, mobile 375); `docs/CHANGELOG.md` line; no writes to `data/budget.sqlite`; scratch databases only. "Done when" adds the allowlist deletion and, where applicable, the invariant `xfail` flip.

**`[pre-v4-P3]` subset (implementation_plan section 9; must be ✅ before v4 Phase 3 starts, T-E00 gate):** T-Q201 (Q-001), T-Q206 and T-Q207 (Q-002), T-Q208 (Q-003), T-Q209 and T-Q215 (Q-010), T-Q212 (Q-007), T-Q213 (Q-008), T-Q214 (Q-009). Unchanged by this backlog. `[pre-v4-P3-rec]` marks work the inventory (section 16, "Before v4 Phase 3? yes") or the audit recommends before Phase 3 because it sits in the layers Phase 3 sweeps (repositories, aggregates, routers): T-Q219, T-Q227, T-Q228, T-Q229, T-Q233, T-Q236, T-Q237, T-Q241, T-Q243, T-Q245, T-Q258, T-Q260 (decision D2), T-Q263, T-Q264, T-Q265, T-Q266, T-Q268. Whether `[pre-v4-P3-rec]` becomes a gate is decision D1; the closing gate T-Q232 is not a v4 gate.

**`[before-2nd-user]`:** T-Q201 (Q-001), T-Q202 (Q-028), T-Q203 (Q-027), T-Q204 (Q-025, Q-063), T-Q205 (Q-034), T-Q221 (Q-015). An admin password reset equals account takeover until v4 envelope encryption (accepted v3 risk); OQ-2 (when the second user arrives) sets the urgency of Band 0.

**`[pre-first-non-PLN]`:** T-Q212, T-Q213, T-Q214, T-Q215, T-Q216 (Q-007 to Q-011, Q-029). Prod is PLN-only today (OQ-1 asks the operator to confirm with a read-only count on a copy); nothing in this set may be skipped before the first non-PLN, non-base or zero-decimal account exists.

**Decisions (operator, 2026-11-21).** D1 answered: default taken, only `[pre-v4-P3]` gates T-E00. D2 answered: default taken, T-Q260 stays after Phase 3 (Band 4); moot because all waves run before Phase 3. D3 answered: the redesign deletes the old templates, so remediation burns down `template_logic.toml` only for templates that survive the redesign; after the redesign the allowlist must be burned to zero (ADR-0130 amendment 2026-11-21; T-Q237 and T-Q273 re-scoped, the remainder transfers to `docs/plans/ui-redesign/`). D4 (open): E04 and the logging-in-services question (compliance-inventory section 17 questions 1 and 2) are settled in the ADRs of T-Q274 and T-Q264; defaults proposed there.

---

### Band 0 — Before a second user is onboarded, and Highs that bite current PLN data

### ✅ T-Q201 [S] Income-anchor endpoint uses the signed-in user
- Findings: Q-001 (D-01, H2-01).
- Epic: E09
- Band: 0 · Size: S · Tags: `[pre-v4-P3]` `[before-2nd-user]`
- Depends on: none
- Docs-first step: none (requirements 6.9 and ADR-0061/0025 already require per-user scoping); add one line to `docs/CHANGELOG.md`.
- Acceptance: failing two-user integration test first, ported from `repro/H2/h2_01_anchor_oracle.py` (user 2 writes own row, user 1's row untouched, user 2 gets no 200/422 oracle on user 1's category ids); then `Depends(current_user_id)` on `set_income_anchor` and pass it to both service calls (`web/routers/budget.py:375-399`). New architecture test under `tests/architecture/` fails on an integer literal passed as `user_id` anywhere under `web/` and `services/`.
- Operator question blocking it: none (OQ-2 only sets urgency).
- Final-backlog note: Also owns the single `literal_user_id` entry for `web/routers/budget.py` (2 violations).
- Removes allowlist entries: `literal_user_id`:2 (1 entry)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/literal_user_id.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q202 [S] Recurring-rule save path validates source categories and positive amounts
- Findings: Q-028 (H2-02).
- Epic: E08
- Band: 0 · Size: S · Tags: `[before-2nd-user]`
- Depends on: none
- Docs-first step: none.
- Acceptance: failing test first from `repro/H2/h2_03_formula_foreign_sources.py` extended to create and update (foreign or nonexistent category id and a zero-amount formula rule are rejected with 422 and nothing is persisted); then move `_invalid_source_ids` to a shared service function and call it from `_resolve_amount_inputs` (`web/routers/recurring.py:181-230`, used at create `:268` and update `:632`).
- Operator question blocking it: none.
- Final-backlog note: Epic E08: validation lives in the service, not the router.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q203 [S] Authentication abuse controls: trusted proxy identity, bounded audit text, per-IP lockout
- Findings: Q-027 (D-06, H3-01, H3-05, H3-07, H2-04, H4-01).
- Epic: none (security-control)
- Band: 0 · Size: M · Tags: `[before-2nd-user]`
- Depends on: none
- Docs-first step: ADR (next free number) or ADR-0072 amendment recording that the rate-limit identity is the proxy-set client address and that attacker text written to `audit_log` is truncated and escaped; requirements §6.7 line. OQ-25 is answered by H4: Caddy overwrites `X-Forwarded-For` and `X-CSP-Nonce`, so header rotation is not exploitable via Caddy; the remaining work is the real-IP chain (H4-01: host-networking or no-MASQUERADE for Caddy, Caddy `trusted_proxies`, `--forwarded-allow-ips` pinned to Caddy's address) plus the per-email cap and bounded audit text.
- Acceptance: failing tests first from `repro/H3/h3_rate_limit.py` (spoofed leftmost `X-Forwarded-For` does not change the bucket) and `repro/H2/h2_07_login_lockout_and_audit_tail.py` (one user cannot lock out another behind the same IP; the audit row length is bounded); then `--forwarded-allow-ips` pinned to the proxy address in the `Dockerfile` and compose template, proxy overwrites `X-Forwarded-For`/`X-Real-IP`, bucket keyed on (IP, username) with a global IP ceiling, truncation of persisted text (`web/routers/auth.py:85-203`).
- Operator question: OQ-25 answered by H4; OQ-30 (which MASQUERADE rule) shapes the fix.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q204 [S] One transaction for compound mutations, immediate write locks, admin edge cases
- Findings: Q-025 (C-09, B-07), Q-063 (H2-05).
- Epic: E10
- Band: 0 · Size: M · Tags: `[before-2nd-user]`
- Depends on: none
- Docs-first step: ADR (next free number) deciding `BEGIN IMMEDIATE` in `repositories/_shared.transaction` and that guard reads live inside the transaction; update ADR-0019 cross-reference.
- Acceptance: failing tests first from `repro/C/repro_concurrency.py` (double-submit promotes once, concurrent writers wait instead of 'database is locked') and `repro/H2/h2_04_admin_chain.py` (absent `is_admin` leaves the target unchanged; concurrent admin changes map to the 409 flow, not 500); then `BEGIN IMMEDIATE`, guard reads moved inside the transaction in `services/planned.py`, `services/recurring.py`, `services/reconciliation.py`, `services/users.py`, and `web/routers/settings_users.py` treating a missing `is_admin` as unchanged.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q205 [S] `user_id`-leading indexes and the per-request session write
- Findings: Q-034 (C-11).
- Epic: none (index/perf)
- Band: 0 · Size: S · Tags: `[before-2nd-user]`
- Depends on: none
- Docs-first step: none beyond a CHANGELOG line (migration only); note in `docs/requirements.md` data section if indexes are listed there.
- Acceptance: failing test first: `repro/C/explain_plans.py` ported to an integration test asserting `EXPLAIN QUERY PLAN` for the hot queries uses the new indexes (no full scan of `transactions`, `planned_transactions`, `audit_log`, `recurring_rules`); then the migration (`(user_id, operation_date) WHERE deleted_at IS NULL`, `(user_id, id)` on `audit_log`, `(user_id, active)` on `recurring_rules`) and, if cheap, throttle the session `last_seen` write. Migration runs on a scratch DB only; prod applies it through the normal release.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q206 [S] Hotfix: forecast overlay stops double-counting linked recurring occurrences
- Findings: Q-002 step 1 (A-04).
- Epic: E01
- Band: 0 · Size: S · Tags: `[pre-v4-P3]`
- Depends on: none
- Docs-first step: none (ADR-0087 amendment already states the rule); CHANGELOG line.
- Acceptance: failing test first ported from `repro/A/output/inv_03b*` and `repro/verify/V1/v_a04.py` (rule 1530 plus a linked planned row: budget committed 1530 and forecast overlay 1530, not 3060); then `_committed_future_for_category` (`services/forecast.py:345-390`) delegates to `budget._committed_by_category`, deleting the second implementation.
- Operator question blocking it: OQ-6 only affects overdue policy (T-Q227), not this fix.
- Final-backlog note: Flips INV-3b: remove the `Q-002` entry from `invariants.toml` in the same commit.
- Removes allowlist entries: `invariants`:1 (1 entry)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/invariants.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the strict `xfail` for INV-3b (Q-002) flips to a plain passing test and its `invariants.toml` entry is deleted; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q208 [S] Canonical budget period window (`domain/periods.py`)
- Findings: Q-003 (A-05, A-14, B-05).
- Epic: E01, E09
- Band: 0 · Size: M · Tags: `[pre-v4-P3]`
- Depends on: none
- Docs-first step: ADR (next free number, amends ADR-0041/0064/0085): half-open `[start, end)` fiscal window, no-anchor fallback is first-of-next-month; requirements note on the days-remaining divisor.
- Acceptance: failing tests first from `repro/A/output/inv_07*` (item on Nov 30: budget delta 0 vs `account_planned` 5000; divisor 11 vs 12) and `repro/B/b_router_logic.out` (plan router period differs for anchors on day 29-31); then `domain/periods.py` (`month_bounds`, `shift_month`, `fiscal_window`) used by `_resolve_anchor`, `account_planned.resolve_window`, analytics, forecast and `recurring_formula`; `web/routers/plan.py:68-251` logic moves to `services/budget.py:month_summary_for_picker`. The five month-bounds copies are deleted. Plan page covered by tests from T-Q252.
- Operator question blocking it: OQ-14 (payday divisor `max(..., 1)`, fiscal-month label) answers the edge-case behaviour.
- Final-backlog note: Also owns the `thin_router.toml` entry for `web/routers/plan.py` (2 violations) because the plan-router logic moves here.
- Removes allowlist entries: `banned_patterns`:4 (3 entries); `invariants`:2 (1 entry); `thin_router`:2 (1 entry)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/banned_patterns.toml`, `allowlists/invariants.toml`, `allowlists/thin_router.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the strict `xfail` for INV-7 (Q-003, 2 xfails) flips to a plain passing test and its `invariants.toml` entry is deleted; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q209 [S] Planned strip and formula-source sums are signed by direction
- Findings: Q-010 sign part (B-01, C-04, E-04).
- Epic: E09
- Band: 0 · Size: S · Tags: `[pre-v4-P3]`
- Depends on: none
- Docs-first step: none (ADR-0008 already defines direction-derived sign); CHANGELOG line.
- Acceptance: failing test first from `repro/B/b_router_logic.out` and `repro/E/fx_probe.out.json` (planned strip sums income and expense together today on PLN data); then move `_recurring_summary` and `planned_total_minor` (`web/routers/ledger.py:343-414`) into `services/ledger_totals.py` as `recurring_monthly_totals` / `planned_totals` using the direction sign helper; the template stops hard-coding `PLN` and `/ 100.0` (the currency-correct part lands in T-Q215/T-Q216).
- Operator question blocking it: OQ-8 (can formula inputs mix currencies) shapes T-Q215, not this task.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q210 [S] Transit shape is validated on every write path
- Findings: Q-004 (B-02).
- Epic: E08
- Band: 0 · Size: M · Tags: none
- Depends on: none
- Docs-first step: ADR-0008 amendment or short ADR (next free number): one `validate_transit_shape(direction, account, dest)` rule for create, update, planned and reconcile; resolves OQ-9 either way.
- Acceptance: failing tests first from `repro/B/b_transit_validation.out`, `repro/B/b_reconcile_transit.out` and `repro/verify/V1/v_b02.py` (POST persists, then /accounts, /today, /forecast return 500); then extract `validate_transit_shape` from `_promotion.validate_promotion` and apply it in create, update, planned and reconcile (`web/routers/transactions.py:263-430`, `planned.py`, `accounts.py`); optional one-off check that no existing prod row has a transit without a destination (read-only count on a copy, with explicit operator go).
- Operator question blocking it: OQ-9.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q211 [S] Recurring schedule anchor day and start-date boundary
- Findings: Q-006 (C-06, C-13).
- Epic: none (date-boundary)
- Band: 0 · Size: M · Tags: none
- Depends on: none
- Docs-first step: ADR amendment (recurrence anchor): `day_of_month` defaults to `start_date.day` at create, `advance_next_due` takes the rule and anchors on `rule.start_date`.
- Acceptance: failing tests first from `repro/C/repro_recurrence_boundaries.py` and `repro/verify/V1/v_c06_c13.py` (drift after a clamped month; occurrences before the start date); then the create-service default, `advance_next_due(rule, ...)` (`services/recurring.py:130,272-306`), and a one-off data-fix step only if OQ-5 shows affected prod rules (read-only check on a copy; prod write only on explicit in-session go).
- Operator question blocking it: OQ-5 (default taken 2026-11-21: no data-fix migration, pending operator data check).
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### 🟡 T-Q218 [S] Gate the CI environments that hold prod-grade secrets
- Findings: Q-012 (H1-01, H1-06, H4-03). Also drop `restore-source.env` and the prod age identity from explore drills (H4-03).
- Epic: none (ci-trust-boundary)
- Band: 0 · Size: M · Tags: none
- Depends on: none
- Docs-first step: ADR (next free number; amends ADR-0099/0100): split by data sensitivity (new `prod-restore-read` environment with required reviewers and `main`-only branch policy for `restore-drill` only; drill and teardown environments keep no prod-read material); update the runbook. Re-check against current `terraform.yml`/`drill.yml` first (audit branch absorbed T-D158 changes).
- Acceptance: **GitHub environment and branch-policy changes are made by the operator in repository settings** (agents have no admin credentials; this is a settings change, not code). Verification by evidence: `repro/H1/collect_gh_config.sh` re-run and the new `gh_api/environments.json` committed under the audit folder or the runbook showing required reviewers and `main`-only policies; workflow edits (environment names, `scripts/ci/tf_env.py`) land as normal code with a test that no workflow outside `main` can reference the gated environments; rotate the secrets listed in OQ-24 if they were real prod values.
- Operator question blocking it: OQ-24 (Sev).
- Status 2026-11-21: code half done (ADR-0132, workflows, `tf_env.py`, `main.tf`, guard, 9 allowlist entries deleted). Operator GitHub settings and rotation pending (ADR-0132 "Operator checklist").
- Removes allowlist entries: `workflow_trust`:23 (9 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/workflow_trust.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q277 [S] Per-drill age keypair in Terraform (ADR-0135)
- Findings: Q-012 (H4-03).
- Epic: none (ci-trust-boundary)
- Band: 0 · Size: S · Tags: none
- Depends on: T-Q218
- Operator decision 2026-11-21: generate the drill key pair with a third-party Terraform age provider so each pair is bound to one drill; drill GitHub environments hold no age key.
- Docs-first step: ADR-0135 (amends ADR-0132, ADR-0078).
- Acceptance: `age_secret_key.drill` (provider `koendelaat/age`, pinned `= 0.1.3`, lock hashes committed for linux_amd64 and darwin_arm64); `litestream_age_*` required only on prod; separate `restore_source_age_identity` delivered only with the restore helper; `tf_env.py`, `preflight.py` and `terraform test` updated; runbooks updated.
- Operator step after merge: delete `LITESTREAM_AGE_IDENTITY` and `LITESTREAM_AGE_RECIPIENT` from `drill`, `drill-plan`, `drill-teardown`.
- Done when: the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q221 [S] Two-user and tombstone fixtures for the money services
- Findings: Q-015 (F-09, F-10).
- Epic: none (test-gap)
- Band: 0 · Size: M · Tags: `[before-2nd-user]`
- Depends on: none
- Docs-first step: none.
- Acceptance: add a two-user fixture and `world_with_tombstones` (soft-deleted and inactive rows) to `tests/unit/services/conftest.py`; one parametrised test per money service function (balance, budget, forecast, analytics, recurring, planned, upcoming, today); re-run `just mutate` on the 40 listed mutants (`user_id`/`conn` as `None`, `include_deleted`, `active_only`) and record that they are killed (rows 5, 7, 22, 30, 43, 51, 60, 78, 101 of `baseline/mutmut-real-gaps.md`).
- Operator question blocking it: none (OQ-15 answered 2026-11-21, ADR-0136).
- Removes allowlist entries: `user_isolation`:54 (54 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/user_isolation.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

---

### Band 1 — Before the first non-PLN account (FX and currency)

### ✅ T-Q212 [S] Canonical FX converter (`FxConverter`), one missing-rate policy, working live fetch
- Findings: Q-007 (G-01, A-06, C-02, C-17, F-06): live fetch never succeeds (no `base_url`), four converter copies with five missing-rate policies, network I/O during page renders.
- Epic: E01, E06
- Band: 1 · Size: L · Tags: `[pre-v4-P3]` `[pre-first-non-PLN]`
- Depends on: none
- Docs-first step: ADR (next free number, amends ADR-0006): cache-only converter per request, explicit missing-rate policy (raise or flag, never rate 1/500), client factory with `base_url=settings.fx_api_url`, rate validation (`rate > 0`; OQ-17 decides a `CHECK`); `docs/requirements.md` FX section; resolves OQ-13 (`services/fx.convert` dead or reserved).
- Acceptance: failing tests first from `repro/A/output/inv_10*`, `repro/C/repro_fx_fallback.py`, `repro/G/fx_client_no_base_url.py` and `repro/verify/V2/g01_fx_relative_url.py` (UnsupportedProtocol, zero requests leave the client); then one `FxConverter` in `services/fx.py` built by `fx.converter_for(conn, settings, today)`, the four copies (`web/today_data.py:124`, `web/routers/forecast.py:49`, budget and analytics converters) deleted, page renders do no network I/O (refresh is a separate scheduled path), and a test injects an `httpx` transport into the same client factory as production (also closes the FX part of Q-058).
- Operator question blocking it: OQ-1 (Sev, confirms latency), OQ-13, OQ-17.
- Final-backlog note: Epic E06 lands here: after this task `forecast.py`, `fx.py`, `web/today_data.py` and the forecast, plan and today routers do no network I/O (the 11 `purity.toml` Q-007 entries), and the 11 `money_scope.toml` and 3 `banned_patterns.toml` FX-copy entries are deleted with the converter copies.
- Removes allowlist entries: `banned_patterns`:13 (3 entries); `invariants`:1 (1 entry); `money_scope`:18 (11 entries); `purity`:17 (11 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/banned_patterns.toml`, `allowlists/invariants.toml`, `allowlists/money_scope.toml`, `allowlists/purity.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the strict `xfail` for INV-10 (Q-007) flips to a plain passing test and its `invariants.toml` entry is deleted; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q213 [S] Analytics and forecast "spent" convert to base currency
- Findings: Q-008 (A-02, A-03).
- Epic: E01
- Band: 1 · Size: M · Tags: `[pre-v4-P3]` `[pre-first-non-PLN]`
- Depends on: T-Q212
- Docs-first step: none (ADR-0006 already says aggregates convert to base); refer to the T-Q212 ADR.
- Acceptance: failing tests first from `repro/A/output/inv_01*` (budget spent 85717 = ledger 85717, analytics 52717) and `inv_03a*` (budget spent 43000 vs forecast 10000); then inject the canonical converter into `services/analytics.py:123-243` (`_spend_by_category`, `_twelve_month_averages`, `_income_vs_expense_monthly`, `_largest_items`) and `forecast._spent_so_far`, ideally via the shared `aggregates.sum_by_category(txns, to_base)` (T-Q227).
- Operator question blocking it: none (OQ-15 for archived-category policy is in T-Q227).
- Removes allowlist entries: `banned_patterns`:3 (2 entries); `invariants`:2 (2 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/banned_patterns.toml`, `allowlists/invariants.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the strict `xfail` for INV-1 and INV-3a (Q-008) flips to a plain passing test and its `invariants.toml` entry is deleted; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q214 [S] One net-worth computation
- Findings: Q-009 (A-07).
- Epic: E01
- Band: 1 · Size: M · Tags: `[pre-v4-P3]` `[pre-first-non-PLN]`
- Depends on: T-Q212
- Docs-first step: requirements note on what "net worth, all accounts" means (converted total plus per-currency breakdown).
- Acceptance: failing test first from `repro/A/output/inv_02*` (+1000 EUR: `fortune.net_base` 3443969 vs `today_data.fortune_base` and forecast day 0 3873969); then `services/fortune.compute_fortune(..., converter)` returns per-currency and converted totals; `web/today_data.py:105-143` and forecast day 0 consume it; the unused `fortune_base` is removed.
- Operator question blocking it: none.
- Removes allowlist entries: `invariants`:1 (1 entry)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/invariants.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the strict `xfail` for INV-2 (Q-009) flips to a plain passing test and its `invariants.toml` entry is deleted; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q215 [S] Ledger strips and formula-source sums convert across currencies
- Findings: Q-010 currency part (B-01, C-04, E-04, A-16).
- Epic: E01, E09
- Band: 1 · Size: S · Tags: `[pre-v4-P3]` `[pre-first-non-PLN]`
- Depends on: T-Q209, T-Q212, T-Q216
- Docs-first step: none (follows the T-Q212 ADR).
- Acceptance: failing test first from `repro/E/fx_probe.out.json` (strip unchanged after flipping the main rule account to EUR); then `recurring_monthly_totals` and `planned_totals` convert via the canonical converter and render in the base currency through the currency renderer; `web/templates/ledger/index.html:93-114` has no literal `PLN`.
- Operator question blocking it: OQ-8.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q216 [S] One money renderer and a complete currency exponent table
- Findings: Q-011 (A-01, C-03, E-03), Q-029 (A-09, C-15).
- Epic: E11
- Band: 1 · Size: M · Tags: `[pre-first-non-PLN]`
- Depends on: none
- Docs-first step: ADR-0006 amendment: `domain/money.py:minor_to_major(amount, currency)` is the only conversion, rounding policy statement (shared with T-Q229), exponent table generated from ISO 4217 beside `ISO_4217_CURRENCIES`.
- Acceptance: failing tests first from `repro/A/output/inv_06*`, `repro/C/repro_jpy_display.py`, `repro/E/money_format_repro.py` (PLN equal, JPY 1,234.56 vs 123,456) and `repro/verify/V1/v_money.py`; then replace every hard-coded `/ 100.0` and two-decimal format in 40+ templates, charts and services (`today/index.html`, `_afford_preview.html`, `_upcoming.html`, `ledger/*`, `_MINOR_UNITS_PER_MAJOR`) with `money`/`money_num(currency)` or `minor_to_major`; unit test that every offered ISO code has an explicit exponent entry (ISK and the 20 other mis-scaled codes). Visual audit on all affected routes.
- Operator question blocking it: OQ-1.
- Final-backlog note: Also owns Q-029 and the INV-6 xfails; owns the `money_scope` slice for scale and format (Q-011).
- Removes allowlist entries: `banned_patterns`:1 (1 entry); `invariants`:3 (2 entries); `money_scope`:16 (10 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/banned_patterns.toml`, `allowlists/invariants.toml`, `allowlists/money_scope.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the strict `xfail` for INV-6 (Q-011, Q-029) flips to a plain passing test and its `invariants.toml` entry is deleted; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q217 [S] Reconcile with an income or expense category cannot misstate the balance
- Findings: Q-005 (C-01, F-07).
- Epic: none (money-arith, latent)
- Band: 1 · Size: S · Tags: none
- Depends on: none
- Docs-first step: requirements and ADR-0008 amendment: reconcile category must be ADJUSTMENT, INCOME with `delta > 0`, or EXPENSE with `delta < 0`; the docstring promise of coercion at `services/reconciliation.py:80-87` is removed.
- Acceptance: failing test first from `repro/C/repro_reconcile_and_parse.py` (B1, B2) and `repro/verify/V1/v_c01.py` (balance ends at 50000 for a typed target of 150000); then `CategoryDirectionMismatchError` in `reconcile` mapped to 422 in `web/routers/accounts.py:481-492`; the reconcile e2e/transport test asserts the resulting balance equals the typed figure.
- Operator question blocking it: OQ-9 (transit direction category), OQ-4 answered.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

---

### Band 2 — Pre-v4-Phase-3 epics (duplicate-logic residue, repository discipline, layering, purity, clock, parsers, HTMX contract)

### ✅ T-Q207 [S] One occurrence expander for all seven consumers
- Findings: Q-002 step 2 (A-04, A-17).
- Epic: E01
- Band: 2 · Size: L · Tags: `[pre-v4-P3]`
- Depends on: T-Q206, T-Q208, T-Q212
- Docs-first step: ADR (next free number, amends ADR-0087/0085): `pending_occurrences(conn, user_id, *, start, end, include_overdue, category_ids)` in `services/recurring.py` as the single "rules x overrides x linked-dedup x window" implementation.
- Acceptance: failing tests first: the invariant tests of T-Q220 for overlay-versus-budget parity stay red until each consumer is switched; then migrate `services/budget.py:296-310`, `forecast.py:262-283,373-381,737-770`, `account_planned.py:106-116`, `income.py:25-93`, `upcoming.py:74-174`, `recurring_formula.py:146-190` and delete the hand-rolled loops.
- Operator question blocking it: OQ-6 (overdue policy) for the `include_overdue` default.
- Final-backlog note: Band 2, not Band 0: the live PLN double count is closed by the T-Q206 hotfix; this is the structural fix. Also owns the `literal_user_id` entry for `services/recurring.py` (1 violation).
- Removes allowlist entries: `literal_user_id`:1 (1 entry)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/literal_user_id.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q227 [S] Residual `duplicate-logic`: categories policy, direction sign, balance rule, aggregates and tier
- Findings: Q-030 (A-11, A-12), Q-032 (C-14), Q-036 (A-10), Q-075 (A-20, A-22).
- Epic: E01
- Band: 2 · Size: M · Tags: `[pre-v4-P3-rec]`
- Depends on: T-Q207, T-Q212, T-Q213
- Docs-first step: ADR (next free number) fixing the policies once: archived categories and inactive rules (OQ-15), overdue items in the forecast (OQ-6), future-dated actuals in "current" balance (OQ-16), the single "monthly average" definition (OQ-7); requirements section update.
- Acceptance: failing tests first from `repro/A/output/inv_09*`, `inv_03c*`, `inv_04a*`; then `services/categories.py:expense_category_ids`, `balance.as_of_today`, one `domain` `signed_legs(direction, amount, account, dest)` with exhaustive `match` and `assert_never` (the six copies become one-line adapters), `services/aggregates.py` (`mean_minor`, `sum_by_category`) and one `pick_tier`.
- Operator question blocking it: OQ-6, OQ-7, OQ-15, OQ-16.
- Removes allowlist entries: `invariants`:2 (2 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/invariants.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the strict `xfail` for INV-3c and INV-9 (Q-030) flips to a plain passing test and its `invariants.toml` entry is deleted; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q228 [S] `repo-bypass`: undo endpoints and audit-free repository helpers
- Findings: Q-024 (B-03, B-11, C-16, H2-03), Q-049 (B-10).
- Epic: E10
- Band: 2 · Size: M · Tags: `[pre-v4-P3-rec]`
- Depends on: T-Q204
- Docs-first step: ADR (next free number, supersedes the relevant part of ADR-0019 text): undo is an audited action (OQ-11), undo targets the specific audit row, and `user_preferences` writes are audited or explicitly exempt (OQ-10 on NULL `ip`/`session_id`/`user_agent`).
- Acceptance: failing tests first from `repro/B/b_undo_replay.out` and `repro/H2/h2_02_undo_chain.py` (replays the latest audit row of any operation, restores partial state, writes no audit entry); then SQL deleted from `web/routers/planned.py:112-181` and `web/routers/recurring.py:470-545` in favour of repository/service functions; the three helpers move to `repositories/_unaudited.py`, imported only by `services/recurring.py` (architecture test beside `tests/architecture/test_user_id_filter.py`).
- Operator question blocking it: OQ-10, OQ-11.
- Removes allowlist entries: `sql_sites`:6 (4 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/sql_sites.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q229 [S] `clock` and rounding policy
- Findings: Q-031 (A-13, C-08, F-21), Q-076 (C-18, C-19).
- Epic: E07, E11
- Band: 2 · Size: L · Tags: `[pre-v4-P3-rec]`
- Depends on: T-Q212, T-Q216
- Partial: ledger tests fixed in T-Q-TB1 (planned seed date is now `date.today()`-relative).
- Docs-first step: ADR (next free number): `budget_planner/clock.py` with `utc_now()`, `today_local(settings)` and an injectable override; services never call `date.today()`; ADR-0006 amendment for the single rounding policy (`round_div` HALF_EVEN, `round_scaled`) and retention timestamp format (`utc_now_iso`). Resolves OQ-3 (zoneinfo in the image) and OQ-18 (only Europe/Warsaw).
- Acceptance: failing tests first from `repro/A/output/inv_08*` and `repro/C/repro_clock.py` (month-end and Warsaw midnight window); then replace the 16-18 `date.today()` sites (`baseline/clock-sites.txt`), add a `today` FastAPI dependency, route time-dependent tests and the visual suite through the override, unify the rounding helpers (`domain/money.py`, `services/recurring_formula.py`, `services/fx.py`, `services/today.py`, `web/routers/today.py`) and the retention comparison.
- Operator question blocking it: OQ-3, OQ-18.
- Defaults taken 2026-11-21, pending operator confirmation (ADR-0140): OQ-3 yes (the venv carries the PyPI `tzdata` wheel via `python-dateutil`/`pandas`, no Dockerfile change); OQ-18 Europe/Warsaw is the only supported display zone, the setting stays configurable. OQ-ROUND: single rounding mode? default kept per-site 2026-11-21 (HALF_EVEN averages and FX, HALF_UP `to_minor_units` and recurring formula; ADR-0006 amendment table), pending operator confirmation. The task text said HALF_EVEN everywhere, but the code and pinned tests (T-Q222, T-Q216) are HALF_UP at two sites; no user-visible amount changes.
- Final-backlog note: Also owns the `clock.py` `module-state` entry in `functional_first.toml`, the `DTZ011` ceiling (18 `noqa`) and the rounding and float slices of `banned_patterns` and `money_scope` (Q-022, Q-076).
- Removes allowlist entries: `banned_patterns`:29 (10 entries); `functional_first`:1 (1 entry); `invariants`:1 (1 entry); `money_scope`:27 (13 entries); `purity`:6 (6 entries); `suppressions` ceiling `DTZ011`:18
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/banned_patterns.toml`, `allowlists/functional_first.toml`, `allowlists/invariants.toml`, `allowlists/money_scope.toml`, `allowlists/purity.toml`, `allowlists/suppressions.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the strict `xfail` for INV-8 (Q-031) flips to a plain passing test and its `invariants.toml` entry is deleted; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q233 [P] One input parser and bounded parameters (no 500 on bad input)
- Findings: Q-023 (A-08, C-10, A-19, D-02, H3-03).
- Epic: E03, E11
- Band: 2 · Size: M · Tags: `[pre-v4-P3-rec]`
- Depends on: none
- Docs-first step: ADR (next free number) or requirements §6 note: `parse_amount_str` is the only amount parser (no exponents, `NaN`, non-ASCII digits, magnitude above `MAX_MINOR`), shared `web/params.py` for date/year/month/id parsing.
- Acceptance: failing tests first from `repro/A/output/inv_05*`, `repro/verify/V1/v_c10.py`, `repro/verify/V2/d02_overflow.py`, `repro/H3/h3_csrf_preauth_output.txt` (C4), `repro/C/repro_input_boundaries.py` (each input returns 422/400, never 500); then replace the seven parsers.
- Operator question blocking it: none.
- Final-backlog note: Also owns the `money-parse` entries of `money_scope.toml` and the `transactions.py` `banned-name` entry.
- Removes allowlist entries: `banned_patterns`:2 (1 entry); `invariants`:1 (1 entry); `money_scope`:17 (10 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/banned_patterns.toml`, `allowlists/invariants.toml`, `allowlists/money_scope.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the strict `xfail` for INV-5 (Q-023) flips to a plain passing test and its `invariants.toml` entry is deleted; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q236 [P] HTMX error flashes swap; one event and toast contract
- Findings: Q-037 (E-01), Q-038 (A-18, E-02, E-07).
- Epic: E03
- Band: 2 · Size: M · Tags: `[pre-v4-P3-rec]`
- Depends on: T-Q233
- Docs-first step: ADR (next free number) or `docs/requirements.md` frontend note: `web/htmx.py` owns `Event` constants, `invalidate(response, *domains)` and `toast_payload(variant, message, undo=...)`; resolves OQ-27.
- Acceptance: failing tests first from `repro/E/htmx_matrix.py` / `htmx_matrix.out.md` (404/409/500 flash not swapped; four `*-stale` events with no listener); then one global `htmx:beforeSwap` handler in `app-init.js` and the contract module; the emitter/listener orphan guard per prevention.md §2 for `htmx-contract` is switched to strict. `frontend-visual-audit` on affected routes.
- Operator question blocking it: OQ-27.
- Final-backlog note: Owns `htmx_events.toml` and the Q-038 `banned_patterns.toml` entries; T-Q261 follows for the string-literal registry.
- Removes allowlist entries: `banned_patterns`:6 (3 entries); `htmx_events`:35 (7 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/banned_patterns.toml`, `allowlists/htmx_events.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q237 [P] Budget numbers in templates come from `MonthSummary`
- Findings: Q-039 (E-05, A-15).
- Epic: E09, E16
- Band: 2 · Size: M · Tags: `[pre-v4-P3-rec]`
- Depends on: T-Q208
- Docs-first step: none.
- Acceptance: failing test first: a rendered Today/Plan/Budget page shows the same left-per-day and percent-used as the service value (float template arithmetic removed); then add `left_per_day_minor`, `spent_pct`, `committed_pct`, `remaining_after` to `MonthSummary` (or a `BudgetView`) and delete the template `set` blocks (`today/index.html:28-36`, `plan/_budget_tab.html`, `_period_header.html`, `budget/index.html`). Visual audit.
- Operator question blocking it: none.
- Final-backlog note: Scope for allowlist ownership: templates under `today`, `plan`, `budget`, `partials/budget`, `partials/forecast` (42 entries); T-Q273 owns the rest.
- **Re-scope (decision D3, operator 2026-11-21, ADR-0130 amendment):** burn down only entries for templates that survive the redesign; entries for templates the Sourdough redesign (ADR-0107) replaces are left in place and transfer to the redesign plan, where `template_logic.toml` must reach zero. The service-side work (`MonthSummary` fields, failing value test) still lands. Q-ids stay as above.
- Removes allowlist entries: `template_logic`:42 (42 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/template_logic.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q241 [S] CRUD service layer per entity
- Findings: Q-045 (B-04).
- Epic: E08
- Band: 2 · Size: L · Tags: `[pre-v4-P3-rec]`
- Depends on: T-Q202, T-Q210, T-Q228, T-Q243
- Docs-first step: ADR (next free number, extends ADR-0021): one CRUD service per entity (`transactions`, `planned`, `accounts`, `recurring_rules`, `budget_overrides`); resolves OQ-12 (before or after the Sourdough redesign, ADR-0107).
- Acceptance: failing architecture test first (routers do not import repositories; allowlist lists the current 13 routers and 6 writing routers); then one service per entity, routers call services only.
- Operator question blocking it: OQ-12.
- Final-backlog note: Owns the 13 `layering.toml` `routers-not-repositories` entries (36 violations); T-Q265 to T-Q267 own the router thinning that follows.
- Removes allowlist entries: `layering`:36 (13 entries)
- Outcome (2026-11-21): ADR-0142; entity services expose the router-facing CRUD (plain bindings over the repository helpers, new `services/budget_overrides.py`); all 12 routers stop importing `repositories`; `test_routers_no_repositories.py` (no allowlist); 13 `layering` entries and their `ignore_imports` deleted; `thin_router` logic-in-router counts lowered, helper-in-router raised by reclassification (ADR-0130 amendment).
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/layering.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q243 [S] Break the recurring import cycle; keyword-only service signatures
- Findings: Q-047 (B-06, B-12, A-21), Q-048 (B-08).
- Epic: E12, E13
- Band: 2 · Size: M · Tags: `[pre-v4-P3-rec]`
- Depends on: T-Q211
- Docs-first step: none (ADR-0021 covers); update the import-contract config.
- Acceptance: pure scheduling code (`generate_occurrences`, `advance_next_due`, `first_due_on_or_after`, `occurrence_in_month`, `_STEP_MONTHS`, `_build_lookup_stub`) moves to `domain/recurring_schedule.py`; nine `PLC0415` lazy imports and the `next_due` seeding copies removed; eight service signatures keep `conn, user_id` positional and the rest keyword-only (about 12 callers).
- Operator question blocking it: none.
- Final-backlog note: Also owns the `PLC0415` ceiling (37 lazy imports) and the 8 service-signature slice of the `PLR0917` ceiling in `suppressions.toml`.
- Removes allowlist entries: `layering`:4 (4 entries); `suppressions` ceiling `PLC0415`:37; `suppressions` ceiling `PLR0917`:8
- Outcome (2026-11-21): pure schedule in `domain/recurring_schedule.py` (`initial_next_due` replaces the repository stub copy); `apply_overrides` split into `services/recurring_overrides.py` so `recurring` and `recurring_formula` no longer import each other; all 37 `PLC0415` lazy imports in `src/` removed (ceiling key stays at 0, the guard needs the key); seven service signatures made keyword-only after `conn, user_id` (`expand_unpromoted`, `rt_expand`, `reconcile`, `forecast`, `forecast_monthly`, `_collect_budget_overlay`, `_resolve_period_start`), `PLR0917` ceiling 32 -> 25; `fx.convert` (no `user_id`, owned by T-Q212) left for its migration.
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/layering.toml`, `allowlists/suppressions.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q245 [P] ADR status, bodies, and project-instruction drift
- Findings: Q-051 (G-02, G-03, G-04), Q-052 (G-16, G-15), Q-053 (G-08, G-09, D-13).
- Epic: E14
- Band: 2 · Size: M · Tags: `[pre-v4-P3-rec]`
- Depends on: none
- Docs-first step: this task is the docs change; CLAUDE.md and `.claude/skills/**` edits are reviewed by the operator before merge (implementation_plan §7.3).
- Acceptance: 13 implemented ADRs flipped to Accepted, ADR-0106/0107 to Accepted-with-implementation-pending (OQ-23), amendments reflected in the index, duplicate numbers 0105 and 0121 either renumbered or grandfathered with an architecture test of unique numbers; ADR-0002/0023/0026/0036/0052/0057 corrected with dated addenda; CLAUDE.md, the orchestrator skill and requirements §3 and §6.7 name real paths and the real stack.
- Operator question blocking it: OQ-23.
- Final-backlog note: Owns `adr_index.toml` (1) and `guidance_paths.toml` (2 entries, 11 violations: `CLAUDE.md`, orchestrator skill).
- Removes allowlist entries: `adr_index`:1 (1 entry); `guidance_paths`:11 (2 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/adr_index.toml`, `allowlists/guidance_paths.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q258 [P] Small layering and functional-first deviations
- Findings: Q-074 (B-13, B-14, B-15, B-16).
- Epic: E05, E10, E12
- Band: 2 · Size: S · Tags: `[pre-v4-P3-rec]`
- Depends on: T-Q241, T-Q243
- Docs-first step: ADR-0021 sentence on framework classes and memo parameters.
- Acceptance: `ContextVar` for the transaction depth (`repositories/_shared.py:98`), `MappingProxyType` for `_EMPTY_TERM_INPUT`, the two SQL queries in `services/accounts.py` moved to repositories, the five `web -> db` import-contract breaks removed, and docstrings corrected to the soft-delete rule.
- Operator question blocking it: none.
- Final-backlog note: Owns the 5 `layering.toml` `web-not-db` entries and the 2 `sql_sites.toml` entries for `services/accounts.py`; epic E05 (ContextVar transaction depth) overlaps T-Q263 only on `repositories/_shared.py` (this task owns the `_TX_DEPTH` line).
- Removes allowlist entries: `layering`:5 (5 entries); `sql_sites`:4 (2 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/layering.toml`, `allowlists/sql_sites.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q263 [P] Immutable module constants, no hidden caches or globals
- Findings: Q-074 (B-13); epic E05.
- Epic: E05
- Band: 2 · Size: S · Tags: `[pre-v4-P3-rec]`
- Depends on: none
- Docs-first step: ADR-0021 sentence (framework classes and memo parameters) is T-Q258; this task needs none beyond a CHANGELOG line.
- Acceptance: Failing guard first: `functional_first.toml` entries with `epic = "E05"` (18 entries, 21 violations). Convert module `dict`/`list`/`set` constants to `MappingProxyType`, tuples or frozensets (`db/migrate.py`, `domain/money.py`, `repositories/_shared.py`, `services/audit.py`, `export.py`, `recurring.py`, `web/templating.py`, `web/today_data.py`, `web/routers/recurring.py`, middleware); replace the two `global` statements (`logging.py`, `web/app.py`) with an explicit state object; remove the `lru_cache` hidden caches by passing the object explicitly (`config.get_settings` caching moves with T-Q264); stop mutating `data` parameters in `logging.py` and `recurring_formula.py`.
- Operator question blocking it: none.
- Removes allowlist entries: `functional_first`:21 (18 entries) Done 2026-11-21: 16 of the 18 entries deleted; the two `config.py` entries (`hidden-cache`, `setattr-bypass`) stay with T-Q264 (settings caching and the frozen `ResolvedSettings`).
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/functional_first.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q264 [S] Pure services: settings as inputs, entropy and password ports, frozen resolved settings
- Findings: Q-074, B-13 (setattr bypass); epic E07; open item from T-Q15b (Settings derived values).
- Epic: E07
- Band: 2 · Size: M · Tags: `[pre-v4-P3-rec]`
- Depends on: T-Q212, T-Q229
- Docs-first step: ADR amendment (ADR-0021/ADR-0130, next free number): derived values move from `Settings._finalise` setattr into a frozen `ResolvedSettings` dataclass built from `Settings`; services receive the values they need as arguments; `TokenSource` port for the stdlib CSPRNG and `random` modules; decision recorded on logging inside services (compliance-inventory section 17 question 1: default is a single `get_logger` facade).
- Acceptance: Failing guard first: `purity.toml` Q-074 entries (12 entries, 14 violations: the hashing module, `auth.py`, `budget.py`, `users.py` and others) and `functional_first.toml` `config.py` `setattr-bypass` (2). Then `config.py` returns a frozen `ResolvedSettings`; `services/auth.py`, `services/budget.py` and friends take settings values as parameters; entropy and hashing go through ports so `domain/` and pure services stay import-clean. `get_settings()` is read only at the web edge (routers, `deps.py`, startup).
- Operator question blocking it: none.
- Removes allowlist entries: `functional_first`:2 (1 entry); `purity`:14 (12 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/functional_first.toml`, `allowlists/purity.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q265 [P] Thin routers, group 1: transactions, planned, ledger, today, forecast, health
- Findings: B-01, B-02 (inventory P5), Q-045 (routing half), Q-048 (route handlers with more than 5 positional parameters); epics E08, E09, E13.
- Epic: E08, E09, E13
- Band: 2 · Size: L · Tags: `[pre-v4-P3-rec]`
- Depends on: T-Q208, T-Q209, T-Q236, T-Q241
- Docs-first step: ADR-0021 amendment only if the view-model contract is not already in the T-Q241 ADR; CHANGELOG line.
- Acceptance: Failing guard first: `thin_router.toml` entries for these six router files (10 entries, 53 violations). Move arithmetic, aggregation, branching on direction/kind, helper functions and transaction control out of the route functions into services or view-model builders; each handler becomes parse, call, render. Route handlers with more than 5 positional parameters take a pydantic form model, which also retires 6 of the `PLR0917` noqa (ceiling slice owned here). `frontend-visual-audit` on every touched route at 1440, 1024, 375.
- Operator question blocking it: none.
- Removes allowlist entries: `thin_router`:53 (10 entries); `suppressions` ceiling `PLR0917`:6
- Outcome (2026-11-22): the six routers hold only parse, call, render. New `web/ledger_data.py` (filters, typed `TxnRow`, ledger context builders), `web/entry_forms.py` (transaction and planned form validation), `web/forecast_data.py`, `services/limit_preview.py` (credit-limit projection, isolation case added), `services/connections.ping`, `replication_health.check_status_file`, `rendering.render_context`; keyword-only handler parameters retire the 6 `PLR0917` noqa (ceiling 23 -> 17); 10 `thin_router` entries and the stale hygiene, size, clone and suppression entries of the moved code deleted (nothing added). `today.py` had no thin-router entry; its private import from `recurring` stays with T-Q266.
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/suppressions.toml`, `allowlists/thin_router.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q266 [P] Thin routers, group 2: recurring, budget, accounts, categories
- Findings: B-01, B-02 (inventory P5), Q-045 (routing half), Q-048 (route handlers with more than 5 positional parameters); epics E08, E09, E13.
- Epic: E08, E09, E13
- Band: 2 · Size: L · Tags: `[pre-v4-P3-rec]`
- Depends on: T-Q202, T-Q233, T-Q241
- Docs-first step: None beyond the T-Q241 ADR; CHANGELOG line.
- Acceptance: Failing guard first: `thin_router.toml` entries for `accounts.py`, `budget.py`, `categories.py`, `recurring.py` (8 entries, 56 violations). Same method as T-Q265; `recurring.py` (25 violations, 1115 lines) is last and is split by T-Q242 in the next wave. Pydantic form models retire 10 `PLR0917` noqa (ceiling slice owned here). Visual audit on affected routes.
- Operator question blocking it: none.
- Removes allowlist entries: `thin_router`:56 (8 entries); `suppressions` ceiling `PLR0917`:10
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/suppressions.toml`, `allowlists/thin_router.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q268 [S] Repository read filters and unaudited mutations classified or fixed
- Findings: B-14 (inventory P6: 22 read rows, 3 unaudited mutations); epic E10.
- Epic: E10
- Band: 2 · Size: M · Tags: `[pre-v4-P3-rec]`
- Depends on: T-Q228
- Docs-first step: ADR-0019 note (or the T-Q228 ADR): which repository functions are intentionally unfiltered (`include_deleted` named, secret-keyed lookups) versus defects.
- Acceptance: Failing guard first: `read_filters.toml` (11 entries, 23 violations: `_shared.py`, `audit.py`, `budgets.py`, `recurring.py`, `sessions.py`, `snapshots.py`, `users.py`, `webauthn.py`). Each row is fixed (add the predicate or the `user_id`), renamed to make the choice explicit (`include_deleted=True` parameter), or routed through `mutate`/`write_audit`; genuinely intentional rows become `permanent` entries with a reason only through an ADR-0130 amendment. Two-user and tombstone tests from T-Q221 cover each fixed function.
- Operator question blocking it: none.
- Removes allowlist entries: `read_filters`:23 (11 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/read_filters.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

---

### Band 3 — Test-gap Highs and test infrastructure

### ✅ T-Q219 [S] Coverage config stops excluding every line containing `...`
- Findings: Q-014 (F-12).
- Epic: E14
- Band: 3 · Size: M · Tags: `[pre-v4-P3-rec]`
- Depends on: none
- Docs-first step: none (tooling correction); CHANGELOG line. Note the coverage gate (90%) can move: record the new percentage in the changelog.
- Acceptance: failing check first: `repro/F/coverage_without_ellipsis_exclusion.txt` shows about 790 statements and 16 functions hidden; then change `pyproject.toml:194` to the anchored `"^\\s*\\.\\.\\.$"` (or delete it) and add tests for the 49 newly visible uncovered statements (triage OQ-28), keeping the gate at 90%.
- Operator question blocking it: OQ-28 (untriaged statements).
- Final-backlog note: Owns the single `coverage_config.toml` entry (`pyproject.toml` ellipsis exclusion).
- Removes allowlist entries: `coverage_config`:1 (1 entry)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/coverage_config.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q220 [S] Differential invariant tests (Track A): close-out of what T-Q15a landed
- Findings: Q-013 (F-14).
- Epic: none (test-gap)
- Band: 3 · Size: S · Tags: none
- Depends on: T-Q15a (landed)
- Docs-first step: none (tests only).
- Acceptance: Landed by T-Q15a (2026-11-20): `tests/integration/invariants/` has `test_inv_01` to `test_inv_10` (23 tests) with the multi-currency seed in `conftest.py` and the G7 registry guard; the open invariants are strict `xfail` entries listed in `allowlists/invariants.toml`. Remaining: confirm every one of the 16 differential invariants of Track A has a test (diff `repro/A/inv_*.py` against the test names), add any missing one, and document in `tests/integration/invariants/conftest.py` which fix task flips which `xfail`. This task owns no allowlist entry: each fix task deletes its own `invariants.toml` entry.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q222 [S] Kill the `recurring_formula` mutant cluster
- Findings: Q-016 (F-02).
- Epic: none (test-gap)
- Band: 3 · Size: M · Tags: none
- Depends on: T-Q221
- Docs-first step: none.
- Acceptance: tests from the real-gaps rows 234-304 in `tests/unit/services/test_recurring_formula.py`: HALF_UP tie cases, two-user same-name fixture, a category with two items and one inactive source rule; the 71 mutants drop to equivalents only (record the survivor count).
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q223 [S] Kill the `forecast` mutant cluster
- Findings: Q-017 (F-03).
- Epic: none (test-gap)
- Band: 3 · Size: L · Tags: none
- Depends on: T-Q207, T-Q221
- Docs-first step: none.
- Acceptance: tests in `tests/unit/services/test_forecast.py` for the horizon-end boundary (item on the last day and one day later), skipped-by-override item followed by a valid one, income/expense/transit legs on one day with the exact day balance, and the FX arguments; the 102 survivors drop to equivalents only.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q224 [S] Kill the `budget` mutant cluster
- Findings: Q-018 (F-04).
- Epic: none (test-gap)
- Band: 3 · Size: M · Tags: none
- Depends on: T-Q208, T-Q221
- Docs-first step: none.
- Acceptance: tests in `test_budget.py` and `test_budget_fx.py`: `_month_range` and fiscal start for the first of the month and the anchor day; committed item on the last day and the day after; empty and one-item `_mean_minor`; FX converter behaviour; the 53 survivors drop to equivalents only.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q225 [S] Kill the `recurring` mutant cluster; assert audit attribution
- Findings: Q-019 (F-05).
- Epic: none (test-gap)
- Band: 3 · Size: M · Tags: none
- Depends on: T-Q211, T-Q221
- Docs-first step: none.
- Acceptance: tests in `test_recurring.py` read the `audit_log` row after `promote_recurring` (user, entity, operation, prev/new JSON; helper `audit_rows` in `tests/integration/auth/conftest.py:41`), override ordering, boundary days; the 50 survivors drop to equivalents only.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q226 [S] Kill the `balance` mutant cluster; cover series and yearly grid
- Findings: Q-020 (F-08, F-27).
- Epic: none (test-gap)
- Band: 3 · Size: M · Tags: none
- Depends on: T-Q219, T-Q221
- Docs-first step: none.
- Acceptance: tests in `test_balance.py` for two accounts with one transaction each (balances and `AccountStats.account_id`/`base_balance`), include-deleted choice, `sparkline_points`, `balance_series`, and `budget.yearly_grid`; the 10 survivors drop to equivalents only.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q231 [S] Test-suite tripwire against touching the prod DB
- Findings: Q-060 (F-20).
- Epic: none (test-gap)
- Band: 3 · Size: S · Tags: none
- Depends on: none
- Docs-first step: none (testing hygiene; mention in CLAUDE.md "Databases" only if the operator approves the edit).
- Acceptance: failing meta-test first (a test that sets no DB URL must not resolve to `data/budget.sqlite`); then an autouse session fixture in `tests/conftest.py` pointing `BUDGET_DATABASE_URL` to a session temp path, unsetting `BUDGET_PLANNER_ADMIN_*`, and asserting the resolved path is not `data/budget.sqlite`.
- Operator question blocking it: OQ-29 (Sev, Medium to High).
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q278 [P] Migrate the SYNC-MAIN markup assertions to the UI harness
- Findings: harness debt from SYNC-MAIN (2026-11-22): 167 markup assertions in 25 remediation-side test files that `main` had converted to the UI map (ADR-0106 section 2).
- Epic: none (test infrastructure)
- Band: 3 · Size: L · Tags: none
- Depends on: SYNC-MAIN
- Docs-first step: ADR-0106 section 2 already forbids the pattern; this task only pays the allowlist down. No template hook without an entry in `docs/audits/2026-11-22-t-q278-ui-map.md`.
- Acceptance: every allowlisted test asserts behaviour through `tests/ui_map` locators (`_html`, Playwright `to_playwright`) or DB state (`db_probe`); exact values kept, no assertion weakened; `ALLOWLIST` in `tests/architecture/test_no_markup_assertions.py` is empty; any `data-testid` hook added is justified in the audit record.
- Operator question blocking it: none.
- Removes allowlist entries: `test_no_markup_assertions.ALLOWLIST` 167 -> 0
- Done when: the allowlist is empty; the guards stay green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

---

### Band 4 — Full-compliance burn-down (remaining epics)

### ✅ T-Q242 [S] Split oversized modules
- Findings: Q-046 (B-09).
- Epic: E13
- Band: 4 · Size: L · Tags: none
- Depends on: T-Q207, T-Q241, T-Q265, T-Q266
- Docs-first step: none (follows the table 2.4 splits in `tracks/B-layering.md`).
- Acceptance: `web/routers/recurring.py` and `services/forecast.py` under 800 lines; no router function worse than complexity C once the E and D blocks are gone; xenon introduced at `--max-absolute C` in `just lint`.
- Operator question blocking it: none.
- Final-backlog note: Allowlist ownership narrowed to `size_complexity.toml` entries for `services/forecast.py` and `web/routers/recurring.py` (6 entries); T-Q269 and T-Q270 own the rest of `size_complexity.toml`.
- Removes allowlist entries: `size_complexity`:18 (6 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/size_complexity.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q260 [S] Generic CRUD helpers in `repositories/_shared` (clone groups and same-name helpers)
- Findings: inventory P1 (compliance-inventory 2.2, 2.6; 9 clone groups, 36 repository functions, 7 pylint blocks); epic E02.
- Epic: E02
- Band: 4 · Size: L · Tags: `[pre-v4-P3-rec]` (decision D2)
- Depends on: T-Q268
- Docs-first step: ADR amendment (ADR-0021/ADR-0019, next free number if needed): one parametrised helper set (`find_by_id`, `find_by_name`, `list_all`, `update_patch`, `soft_delete`, `undelete`, `list_recently_deleted`, row hydration) in `repositories/_shared`; table-driven only, no ORM. Update requirements section 3 only if the repository conventions are listed.
- Acceptance: Failing guard first: `clones.toml` counts for `repositories/*` are the red/green signal. Replace the 18 allowlisted repository files one entity at a time (behaviour-preserving; the existing repository and integration tests are the safety net, plus a table-driven test per helper including soft-delete, user filter and audit). Mutation check with `just mutate` on `repositories/_shared.py` records the score. Large mechanical diff: land per entity, not in one commit.
- Why this slot: Inventory section 16 sequences E02 last (mechanical, conflict-prone). It is Band 4 and Wave 10 because it also shrinks the v4 Phase 3 repository sweep (decision D2: the operator may move it before Phase 3).
- Operator question blocking it: none.
- Removes allowlist entries: `clones`:75 (18 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/clones.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q261 [P] Literal registry: HTMX events, header names, currency codes, timezone, direction and cadence strings
- Findings: Q-038 (literal half; A-18, E-02), inventory P13 `domain-literal` / `repeated-literal` rows; epic E03.
- Epic: E03
- Band: 4 · Size: M · Tags: none
- Depends on: T-Q236, T-Q265, T-Q266, T-Q267
- Docs-first step: None beyond the T-Q236 contract ADR (the defining modules named in the G19 row of compliance-inventory section 15 are already decided by ADR-0130); one CHANGELOG line.
- Acceptance: Failing guard first: `literals.toml` (29 entries) is the signal. Replace string literals with the defining-module constants (`web/htmx.py`, `web/http_headers.py`, `config.py`, `domain/enums.py`) in `web/`, `services/`, `repositories/`, `db/`; repeated literals (message text, route names, cookie names) become module constants or a small `web/messages.py`. No behaviour change; run the full e2e subset that exercises HTMX swaps.
- Operator question blocking it: none.
- Removes allowlist entries: `literals`:124 (29 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/literals.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q262 [P] Clone ratchet: same-name helpers and clone groups in services and web
- Findings: inventory P1 (same-name rows and clone groups outside `repositories/`; compliance-inventory 2.2, 2.6, 2.7); epic E03.
- Epic: E03
- Band: 4 · Size: M · Tags: none
- Depends on: T-Q233, T-Q236, T-Q242, T-Q265, T-Q266, T-Q267
- Docs-first step: None (ADR-0130 already fixes the rule); CHANGELOG line.
- Acceptance: Failing guard first: `clones.toml` entries with `epic = "E03"` (15 entries). For each same-name private helper (`_wants_json`, `_safe_next`, `_hydrate_rows`, `_parse_*`, `_month_bounds` leftovers) keep one implementation in the canonical module and import it; delete the copies. Items already removed by T-Q233, T-Q236, T-Q242, T-Q265 to T-Q267 are re-read from `allowlist_by_qid.py` before starting.
- Outcome (2026-11-22): the 6 remaining E03 `clones.toml` entries deleted (the list is now empty). `wants_json` has one owner, `web/htmx.py` (both middleware copies and `auth_deps` use it; moved there to avoid an `auth_deps` -> `deps` -> middleware import cycle). The three `txn -> base` copies named `_base_of` are renamed or inlined onto `fx.txn_base_of`; `accounts.reconcile` `_reject` and `csrf._reject` renamed. The `today.py` private cross-router import was already gone (`web/recurring_forms.py`). `web/retention_task.run_once` vs `db/retention.run` (4 lines) left: a shared seam needs `services/connections` to import `config.Settings`, which G22 `eff-import` forbids, and the pair is not a clone-guard entry.
- Operator question blocking it: none.
- Removes allowlist entries: `clones`:24 (15 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/clones.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q267 [P] Thin routers, group 3: auth and settings routers
- Findings: B-01, B-02 (inventory P5), Q-045 (routing half), Q-048 (route handlers with more than 5 positional parameters); epics E08, E09, E13.
- Epic: E08, E09, E13
- Band: 4 · Size: L · Tags: none
- Depends on: T-Q241
- Docs-first step: None beyond the T-Q241 ADR; auth-flow changes keep ADR-0078/0079 behaviour; CHANGELOG line.
- Acceptance: Failing guard first: `thin_router.toml` entries for `auth.py`, `settings.py`, the password-settings router, `settings_security.py`, `settings_users.py` (7 entries, 43 violations; `auth.py` has 23 helpers in the router module, `settings_users.py` 11). Helpers move to `services/auth.py`, `services/users.py` or `web/auth_cookies.py`; form models retire 8 `PLR0917` noqa (ceiling slice owned here). Security-sensitive: run the auth integration and e2e suites, then `security-reviewer`.
- Operator question blocking it: none.
- Removes allowlist entries: `thin_router`:43 (7 entries); `suppressions` ceiling `PLR0917`:8
- Outcome (2026-11-22): the five routers hold route handlers only. Helpers and rate-limit dependencies moved to `web/auth_deps.py` (also `current_admin`), `web/auth_flow.py`, `web/security_context.py`, `web/users_admin.py` and the password-change response helpers; view models to `services/settings_drawer.py`, `services/security_settings.py`; `services/auth.py` gained `clean_passkey_label` and `is_session_handle`; `web/rendering.render_context` takes a ready context mapping. Keyword-only route params retire the 8 `PLR0917` noqa (ceiling 14 -> 6). The 6 `thin_router` entries (auth, settings x2, settings_password, settings_security, settings_users) plus the now-stale clones, hygiene, functional_first, literals, size_complexity, suppressions and private_imports entries for these routers deleted. No template change.
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/suppressions.toml`, `allowlists/thin_router.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q269 [S] Decompose oversized functions in services, repositories, db, logging and charts
- Findings: Q-046 (B-09 complexity and length rows outside the router modules); epic E13.
- Epic: E13
- Band: 4 · Size: L · Tags: none
- Depends on: T-Q207, T-Q242, T-Q243, T-Q262
- Docs-first step: None (follows the table 2.4 splits in `tracks/B-layering.md`); CHANGELOG line.
- Acceptance: Failing guard first: `size_complexity.toml` entries for `services/*`, `repositories/*`, `db/migrate.py`, `logging.py`, `web/charts.py`, `web/auth_cookies.py` (19 entries, 29 violations; `services/forecast.py` is owned by T-Q242). Split each function above 50 lines, complexity C or nesting above 4 into named steps; xenon at `--max-absolute C` is wired into `just lint` once both size owners are done.
- Operator question blocking it: none.
- Removes allowlist entries: `size_complexity`:29 (19 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/size_complexity.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q270 [S] Decompose oversized functions in web routers
- Findings: Q-046 (B-09 router rows); epic E13.
- Epic: E13
- Band: 4 · Size: L · Tags: none
- Depends on: T-Q242, T-Q262, T-Q265, T-Q266, T-Q267
- Docs-first step: None; CHANGELOG line.
- Acceptance: Failing guard first: `size_complexity.toml` entries under `web/routers/` except `recurring.py` (16 entries, 26 violations). Most disappear when T-Q265 to T-Q267 land; this task removes what remains (`plan()`, `budget.py`, `accounts.py`, `planned.py`, `transactions.py`, `settings.py`, `today.py`). Visual audit on affected routes.
- Outcome (2026-11-22): most entries had already gone with T-Q265 to T-Q267; the last 6 violations (accounts 1, planned 3, transactions 2) are fixed by `web/form_responses.py` and deleted. `recurring.py` stays with its owner (T-Q288). `xenon --max-absolute C src` is wired (pre-commit hook, `just lint`, CI through pre-commit; ADR-0130 amendment 2026-11-22) and the whole tree passes. No template touched, no visual audit needed.
- Operator question blocking it: none.
- Removes allowlist entries: `size_complexity`:26 (16 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/size_complexity.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q271 [S] Hygiene sweep: `Any` in signatures, asserts in `src`, broad and silent excepts, prints
- Findings: Q-073 (hygiene half; C-20), inventory P13 rows `any-annotation`, `assert-in-src`, `broad-except`, `silent-except`, `print-call` (compliance-inventory 14.2, 14.3); epic E15.
- Epic: E15
- Band: 4 · Size: L · Tags: none
- Depends on: T-Q260, T-Q265, T-Q266, T-Q267, T-Q268, T-Q269, T-Q270
- Docs-first step: ADR amendment (ADR-0130 section on hygiene) naming the typed error replacements for `assert`, the parse-sentinel convention for intentional swallow sites, and the logger used instead of `print` in `db/seed.py`.
- Acceptance: Failing guard first: `hygiene.toml` (61 entries, 145 violations: `any-annotation` 80, `assert-in-src` 32, `silent-except` 22, `broad-except` 9, `print-call` 2). Type `Any` away (typed form helpers, `TypedDict`, generics), replace each `assert` in `src` with a typed domain error, narrow each broad `except` and log or re-raise each swallowing one (13 are parse sentinels already folded by T-Q233), replace `print` with the logger.
- Operator question blocking it: none.
- Removes allowlist entries: `hygiene`:145 (61 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/hygiene.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q272 [S] Every inline suppression carries a reason or is deleted; per-code ceilings reach zero
- Findings: Q-048 (suppression half), inventory P11 (compliance-inventory section 12); epic E14.
- Epic: E14
- Band: 4 · Size: M · Tags: none
- Depends on: T-Q229, T-Q242, T-Q243, T-Q265, T-Q266, T-Q267, T-Q271
- Docs-first step: None beyond ADR-0130 section 6 (rule already decided); CHANGELOG line.
- Acceptance: Sweeper that runs last among source tasks. Failing guard first: `suppressions.toml` entries (31 entries, 94 violations: 82 `noqa`, 6 `pragma: no cover`, 5 `type: ignore`, 1 `fmt: skip`) and the remaining ceilings. Re-read the allowlist at start: most `PLC0415`, `PLR0917` and `DTZ011` suppressions are already gone with T-Q229, T-Q243, T-Q265 to T-Q267; give each survivor a same-line reason or fix the cause. Ruff `PGH` and `RUF100` stay on. After this task `[ceilings]` is empty.
- Operator question blocking it: none.
- Removes allowlist entries: `suppressions`:94 (31 entries)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/suppressions.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q273 [P] Template-logic burn-down outside the budget views, only for templates that survive the redesign
- Findings: Q-039 (rest of template-logic rows; E-05, A-15), Q-070 (card utilisation defaults), Q-011 (template math); epic E16.
- Epic: E16
- Band: 4 · Size: M · Tags: none
- Depends on: T-Q216, T-Q237
- Docs-first step: None beyond ADR-0130 (template guard) and ADR-0107; if the redesign surface task for a template ships first, its `removal.md` row flips to `deleted` and this task only verifies.
- Acceptance: Failing guard first: `template_logic.toml` entries outside `today`, `plan`, `budget`, `partials/budget` and `partials/forecast` (106 entries, 106 violations: `tpl-set`, `tpl-arith`, `tpl-format`, `tpl-scale`, `tpl-float`, `tpl-domain-if`, `tpl-currency-lit`). Move each computation into the view model or a filter/macro (`money`, `money_num`, `pct`), drop `set` blocks, replace literal currency codes with the row currency. If the old tree is scheduled for deletion by T-UR surface tasks, the order of the redesign decides which of the two paths removes each entry (decision D3). Visual audit on every touched route.
- **Re-scope (decision D3, operator 2026-11-21, ADR-0130 amendment):** the redesign deletes the old templates, so this task burns down only entries for templates that survive the redesign. The remainder transfers to `docs/plans/ui-redesign/tasks.md`, which must leave `template_logic.toml` empty; the count below is an upper bound and entries for redesign-replaced templates stay. Q-ids stay as above.
- Outcome (2026-11-22): verification only, no template edited. Every one of the 51 templates still holding a `template_logic.toml` entry (83 entries) is replaced or ported by a T-UR surface task or deleted by T-UR15 (shared components `_partials/components/*`, `_partials/*`, `partials/*`, `errors/*`, `accounts`, `ledger`, `recurring`, `settings/*`, `dev/components.html`); none survives ADR-0107, so by D3 all 83 entries stay and transfer to `docs/plans/ui-redesign/tasks.md` (surface mapping in its transfer note). No view-model or filter was added: burning replaced templates would be thrown away and would collide with the in-flight ledger FX template work (T-Q215). `frontend-visual-audit` not required (no template or CSS change).
- Operator question blocking it: none (D3 answered).
- Removes allowlist entries: `template_logic`:106 (106 entries, upper bound)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/template_logic.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q274 [S] ASGI middleware and framework-class decision (E04)
- Findings: B-13 (framework rows: 6 `BaseHTTPMiddleware` classes, `CacheControlMiddleware`, logging filter), compliance-inventory section 16 E04 and section 17 question 2; epic E04.
- Epic: E04
- Band: 4 · Size: S · Tags: none
- Depends on: T-Q254
- Docs-first step: ADR-0130 amendment (the only task whose output is a decision): accept Starlette `BaseHTTPMiddleware`, `APIRouter` singletons and the logging `Filter` as the `framework` allowlist category (proposal) or convert to pure ASGI. Either way `request.state` and `response.headers` mutation is funnelled through two helpers.
- Acceptance: Failing guard first: `functional_first.toml` `[[framework]]` entries (41 violations, not counted toward zero) keep a reason each, or the conversion removes them. Pure-ASGI conversion, if chosen, follows T-Q254 (which introduces the outermost ASGI middleware) so the pattern is established once.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

---

### Band 5 — Medium: correctness, security, CI, docs, tests

### ✅ T-Q230 [S] Account archive refuses or cascades when references exist
- Findings: Q-026 (C-05).
- Epic: none (scoping-gap)
- Band: 5 · Size: M · Tags: none
- Depends on: T-Q228
- Docs-first step: requirements and ADR-0019 note: an account with a non-zero balance or live rules/planned rows cannot be archived (409 with message), or they are deactivated in the same transaction.
- Acceptance: failing test first from `repro/C/repro_deleted_refs.py` and `repro/verify/V1/v_c05.py` (promotion posts to a deleted account); then `services/accounts.archive_account()` used by `web/routers/accounts.py:348-354`, and promotion refuses a deleted target.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q234 [P] Remove N+1 query storms on /accounts and /forecast
- Findings: Q-033 (C-07).
- Epic: none (perf)
- Band: 5 · Size: M · Tags: none
- Depends on: T-Q207
- Docs-first step: none (performance; add a query-count budget note to requirements §3.3 if the operator wants it).
- Acceptance: failing test first from `repro/C/query_counts.py` and `repro/verify/V1/v_c07.py` (about 2900 and 2800 statements per request) as an `assert_max_queries(route, n)` pytest helper; then `balance.balance_series` with one query and a running sum, and rules/overrides/planned rows/tiers loaded once and passed down.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q235 [P] Bound work per request
- Findings: Q-035 (C-12, D-04, D-05).
- Epic: none (security-control)
- Band: 5 · Size: M · Tags: none
- Depends on: none
- Docs-first step: none (ADR-0081 aligns); named maximums documented in requirements.
- Acceptance: failing tests first (page size clamp, oversized body and field lengths rejected, `/ready` does not run a full `integrity_check` per unauthenticated probe); then `COUNT`/`SUM` repository functions for counts and balances (`web/routers/ledger.py:68,377-390`, `services/balance.py:77-82`), `page_size` clamp, field lengths in drafts, `/ready` uses a cheap check.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q238 [P] Signed-image identity pinned to `main`; stricter skip classifier
- Findings: Q-040 (H1-02), Q-042 (H1-04, H1-05).
- Epic: none (ci-trust-boundary)
- Band: 5 · Size: S · Tags: none
- Depends on: none
- Docs-first step: ADR amendment to ADR-0099/0100/0121: verified identity is `build.yml@refs/heads/main` or a release tag; the skip classifier allowlist is docs only.
- Acceptance: failing tests first from `repro/H1/gate_and_signing_probe.out` and `repro/H1/classifier_probe.out` (any-ref signature accepted; `.claude/` and `tests/` treated as inert); then `identity_regexp` pinned in `terraform/modules/compute/user_data.tf:118` (drill hosts via a variable), rollback ancestry check in `terraform/host/agent/bp_agent.py`, `scripts/ci/drill_gate_skip.py` shrunk and verdict bound to the head SHA; unit test greps `.github/` and `scripts/ci/` for paths under allowlisted dirs.
- Operator question blocking it: OQ-24 (rollback to `sha-*` tags).
- Final-backlog note: Also owns the `workflow_trust.toml` entry for `cosign-identity-unpinned` (Q-040).
- Removes allowlist entries: `workflow_trust`:1 (1 entry)
- Done when: every entry listed under "Removes allowlist entries" is deleted from `allowlists/workflow_trust.toml` (delete, never lower; the guard ratchets both ways) and the guard is green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### 🟡 T-Q239 [P] Merge gate becomes tamper-resistant (operator GitHub settings)
- Findings: Q-041 (H1-03).
- Epic: none (ci-trust-boundary)
- Band: 5 · Size: S · Tags: none
- Depends on: none
- Docs-first step: ADR amendment (ADR-0099): required workflows from `main`, `integration_id` on required checks, CODEOWNERS over `.github/`, `scripts/ci/`, `terraform/`.
- Acceptance: **ruleset and branch-protection changes are made by the operator** (`workflows` rule, `integration_id` 15368 on each required context, required review for CODEOWNERS paths); `.github/CODEOWNERS` lands as code; evidence is the refreshed `repro/H1/gh_api/ruleset_protect_main.json`. Self-approved merge is accepted risk unless a second reviewer or bot is feasible (OQ-24).
- Operator question blocking it: OQ-24.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q240 [P] Dev-dependency provenance and CI/pre-commit parity
- Findings: Q-043 (G-07), Q-044 (G-05, G-06).
- Epic: none (dependency, config-drift)
- Band: 5 · Size: S · Tags: none
- Depends on: none
- Docs-first step: ADR-0120 amendment: which checks run in PR CI versus pre-commit (OQ-22), tool versions come from `uv.lock`.
- Acceptance: first verify `httpx2` provenance (`git log -S httpx2`, PyPI page); if illegitimate this is an incident and goes to the operator; then remove `httpx2` and the plotly overrides (`pyproject.toml:44,136,172`) and re-lock; run hooks as `repo: local`, `language: system`, `entry: uv run <tool>`; CI runs ruff format, bandit, detect-secrets, tailwind-check or documents why not; pin `uv` in `ci.yml`.
- Operator question blocking it: OQ-19 (Sev), OQ-22.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q244 [P] Remove or re-wire routes without a caller
- Findings: Q-050 (G-13).
- Epic: none (dead-code)
- Band: 5 · Size: S · Tags: none
- Depends on: none
- Docs-first step: decide per route (re-wire the ADR-0056 live preview in the entry form or the ADR-0107 redesign, or delete route, template and tests); update `docs/requirements.md` and ADR-0056 status accordingly.
- Acceptance: the four dead routes deleted with their tests; the formula preview either wired and covered by an e2e, or deleted; the htmx orphan guard stays green.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q246 [P] Reconcile task status with CHANGELOG and ADRs
- Findings: Q-054 (G-10).
- Epic: none (doc-drift)
- Band: 5 · Size: M · Tags: none
- Depends on: T-Q245
- Docs-first step: this is the docs change.
- Acceptance: listed rows in `docs/plans/v1/tasks.md`, `docs/plans/v3/tasks.md` reconciled; `docs/plans/v2/tasks.md` closed as superseded by ADR-0107 or its open rows triaged.
- Operator question blocking it: OQ-21 (default taken 2026-11-21, pending operator confirmation).
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q247 [P] Kill survivors in the non-priority modules
- Findings: Q-055 (F-11).
- Epic: none (test-gap)
- Band: 5 · Size: L · Tags: none
- Depends on: T-Q213, T-Q221
- Docs-first step: none.
- Acceptance: re-triage the sampled rows of `baseline/mutmut-real-gaps.md` (rows 310-516) first; then module by module (`analytics`, `today`, `users`, `planned`, `upcoming`, `export`, `replication_health`, `preferences`) using the suggested-killing-test column; record per-module score in `baseline/mutmut.txt` follow-up.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q248 [P] Browser e2e drives real forms; ledger pagination race
- Findings: Q-056 (F-15), Q-057 (F-16).
- Epic: none (test-gap)
- Band: 5 · Size: M · Tags: none
- Depends on: none
- Docs-first step: none.
- Acceptance: the four e2e tests (`test_add_transaction_flow`, `test_reconcile_flow`, `test_recurring_promote_flow`, `test_set_budget_flow`) drive the visible forms with role locators and keep `request.post` only for seeding; `hx-sync="#ledger-table:replace"` on the ledger form and button, and the pagination test awaits the response deterministically. Run `uv run pytest tests/e2e -q --no-cov` before the PR.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q249 [P] Test transport matches production
- Findings: Q-058 (F-17).
- Epic: none (test-gap)
- Band: 5 · Size: M · Tags: none
- Depends on: T-Q212
- Docs-first step: none.
- Acceptance: tests for CSRF run without the header auto-attached (an extra test class), the secure-cookie path is exercised, and FX tests inject a transport into the production client factory (`tests/unit/services/test_fx.py`, `test_forecast*`).
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q250 [P] Strengthen status-only HTTP tests and the vacuous rollback test
- Findings: Q-059 (F-18, F-19).
- Epic: none (test-gap)
- Band: 5 · Size: M · Tags: none
- Depends on: none
- Docs-first step: none.
- Acceptance: each success-path test in `test_budget.py`, `test_recurring.py`, `test_categories.py`, `test_planned.py`, `test_accounts.py` reads back through the repository or rendered value; each rejection test asserts the row count is unchanged; the reconciliation rollback test fails a middle write, not the only write; weak-assert scan (`repro/F/weak_assert_scan.py`) count drops to zero for these files.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q251 [P] Visual suite becomes a trustworthy check
- Findings: Q-061 (F-22).
- Epic: none (test-gap)
- Band: 5 · Size: M · Tags: none
- Depends on: none
- Docs-first step: ADR-0027 amendment 2026-11-22 (operator decision): the visual suite is a **required check on pull requests that change templates or CSS**, and also runs on a **weekly schedule** and `workflow_dispatch`; it runs in a **pinned Playwright container image**; baselines are regenerated inside that container (Linux), never on a laptop; perceptual threshold; a missing baseline is a failure in CI.
- Acceptance: the workflow triggers on `pull_request` with `paths` covering `src/budget_planner/web/templates/**` and `web/static/*.css` (and is a required status for those PRs), on a weekly `schedule` and on `workflow_dispatch`; the job image is pinned by digest and the same image generates baselines; `max_diff_pixel_ratio` is set; a missing baseline fails in CI; baselines are regenerated in the container after the last template change; a pre-commit check fails when `templates/` change without baseline changes.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.
- Outcome: baselines bootstrapped from the PR #43 CI artifact (run 45056330451), 8 routes x 375/1024/1440 = 24 PNGs in `tests/visual/__snapshots__/`, committed unmodified (T-Q251b).

### ✅ T-Q252 [P] Plan page and `monthly_projection` get tests; `format_money` zero
- Findings: Q-021 (F-13), Q-022 (F-01).
- Epic: none (test-gap)
- Band: 5 · Size: M · Tags: none
- Depends on: T-Q208
- Docs-first step: none.
- Acceptance: new `tests/integration/web/test_plan.py` for `/plan?tab=forecast` (series length, first and last month label, one end balance), `/plan?month=` for a past and a future month (committed zero, period bar dates), the Year tab; `test_format_money_zero` parametrised over PLN and JPY (`0.00 PLN`, `0 JPY`) and `format_money(-1, "JPY")`; fix the `-0.00` rendering if the test shows it.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q275 [P] Bandit bump to 1.9.4 and its three new findings
- Findings: tooling (T-Q15b left bandit pinned at 1.7.10); new findings B105 `repositories/users.py:250`, B704 `web/templating.py:124` and `:161`; epic E15.
- Epic: E15
- Band: 5 · Size: S · Tags: none
- Depends on: T-Q240
- Docs-first step: ADR-0130 tooling note (version bump, `# nosec` convention: reason on the same line); no new ADR otherwise.
- Acceptance: Bump the pin and `uv.lock`, run bandit. B105 (hardcoded password string) is fixed (rename or move the constant out of password-looking identifiers) or carries a reasoned `# nosec B105`; the two B704 (markup built from non-literal) are fixed with `markupsafe.escape` or carry a reasoned `# nosec B704`. Any `# nosec` added must satisfy the suppressions guard (reason on the line). Pre-commit and `just ci` use the same pin (T-Q240).
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

---

### Band 6 — Low

### ✅ T-Q253 [P] Session and passkey hardening
- Findings: Q-062 (H3-02, H3-04, H3-06, H3-08).
- Epic: none (security-control)
- Band: 6 · Size: M · Tags: none
- Depends on: T-Q203
- Docs-first step: ADR amendment (ADR-0078/0079): single-use challenge nonce table, passkey revoke ends its sessions (OQ-26), CSRF token binding decision.
- Acceptance: failing tests first from `repro/H3/h3_passkey_ceremonies_output.txt` (P1, P2, P7), `h3_rotation_race_output.txt`, `h3_csrf_preauth_output.txt` (C1, C2); then fixes (`DELETE ... RETURNING` at finish, no re-set of the rotated token by an in-flight request, no revoke on `new == stored == 0`).
- Operator question blocking it: OQ-26 (Sev for H3-04).
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q254 [P] 500 responses carry security headers; CSP from the app; unenforced surfaces
- Findings: Q-064 (D-03, D-09), Q-065 (D-08, E-11), Q-066 (D-07, D-12).
- Epic: none (security-control)
- Band: 6 · Size: M · Tags: none
- Depends on: T-Q203
- Docs-first step: ADR amendment (ADR-0036/0072): CSP emitted by `SecurityHeadersMiddleware` with an app-generated nonce and Caddy as second layer; `BUDGET_TRUSTED_HOSTS` enforced; `/docs`, `/openapi.json`, `/dev/components` off in production (OQ-20).
- Acceptance: failing tests first (forced 500 asserts all headers and no-store; client-supplied nonce ignored; non-allowed Host rejected; `/docs` returns 404 in production); then an outermost pure-ASGI middleware, nonce generation, `TrustedHostMiddleware`, `docs_url=None`, conditional `dev_components`, and removal of the dead `csrf_token` and `csp_nonce` stubs; log redaction covers exception text.
- Operator question blocking it: OQ-20.
- Outcome 2026-11-22: fixup T-Q254b: template comment tripped the terraform test; caught by drill gate because the terraform PR workflow sits in action_required.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### 🟡 T-Q255 [P] Infra pinning and release-workflow hardening
- Findings: Q-067 (D-11), Q-068 (D-10, H1-09, H1-10, H4-04), Q-069 (H1-07, H1-08), Q-078 (H4-02), Q-079 (H4-05), Q-080 (H4-06).
- Epic: none (dependency, ci-trust-boundary)
- Band: 6 · Size: M · Tags: none
- Depends on: T-Q218, T-Q239
- Docs-first step: ADR-0101/0099 amendments (where the port control sits; pinning policy).
- Acceptance: Caddy/Litestream/base image by `@sha256:` digest, `uv`, tailscale and cloud-init versions pinned; Actions repo settings (`sha_pinning_required`, `allowed_actions: selected`) set by the operator; `permissions: contents: read` default on `ci.yml` and the release `ci` job, `.security-allowlist.yml` read from `origin/main` and passed via `env:` with a validated pattern; drill ports bound to the tailnet address or filtered in `DOCKER-USER`. Terraform changes go through the pipeline only; no prod apply from a laptop.
- Operator question blocking it: OQ-24 (Tailscale ACL parity), OQ-32.
- Status 2026-11-22: repo side done. Digest-pinned Caddy, Litestream (compose + restore script) and both Dockerfile base stages; `uv==0.11.2`; tailscale pinned to `1.104.7` with `apt-mark hold`; `permissions: contents: read` on `ci.yml` and the release `ci` job; `security.yml` reads the allowlist from `origin/main`, validates ids, passes args via `env:`; drill port control documented (ADR-0101 amendment) and asserted in `render.tftest.hcl`; `scripts/check_github_settings.py` checks `allowed_actions: selected`.
- Operator steps left: (1) set Actions repo settings `sha_pinning_required: true` and `allowed_actions: selected`, then run `scripts/check_github_settings.py`; (2) OQ-32 (`tag:ci` ACL): pending operator, ACL source not in repo. Not done: pinning the runner's apt `cloud-init` package in `terraform.yml` (ubuntu-latest image owns the version; the rendered user-data is schema-checked, not installed); re-resolve digests on bump.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q256 [P] Frontend duplication: card utilisation and passkey JS
- Findings: Q-070 (E-06, E-09), Q-071 (E-10).
- Epic: E03, E16
- Band: 6 · Size: S · Tags: none
- Depends on: none
- Docs-first step: none.
- Acceptance: one `credit_utilisation(card)` in the accounts view model, templates fail under StrictUndefined instead of defaulting (`10`, `'PLN'`); `passkeys.js` extracts `runAssertion` and a shared `csrf.js`, logs `err.name` to `console.debug`. Visual audit on `/accounts` and the login flow.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q257 [P] Dead code and silent router import
- Findings: Q-072 (G-17, E-08, plus the E-track alias in findings.md Details), Q-073 (C-20, G-14).
- Epic: none (dead-code)
- Band: 6 · Size: S · Tags: none
- Depends on: T-Q244
- Docs-first step: none (docs list of legacy redirects updated).
- Acceptance: legacy redirects, `routers/analytics.py`, `/afford` and `/budget-legacy` aliases, test-only symbols and `bulk-select.js` removed with `_ROUTER_NAMES`/`extra_paths` updated; `web/app.py:236-247` becomes explicit imports and `include_router` calls (a missing router now fails at startup, test asserts all routers are registered).
- Operator question blocking it: none.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q259 [P] Test hygiene
- Findings: Q-077 (F-23, F-24, F-25, F-26).
- Epic: none (test-gap)
- Band: 6 · Size: S · Tags: none
- Depends on: T-Q231
- Docs-first step: none.
- Acceptance: delete the e2e landmarks test and one of the duplicate promotion tests; the 15 permanently skipped pre-redesign tests deleted or restored; `conn` and an autouse fast-bcrypt fixture moved to `tests/conftest.py` with URLs through `sqlite_url`; investigate the `test_landmarks_present[/today]` flake (OQ-28).
- Operator question blocking it: OQ-28.
- Removes allowlist entries: none
- Done when: no allowlist entry to delete; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

---

### Band 7 — Closing gate

### ✅ T-Q232 [S] Closing gate: every allowlist empty, every guard strict
- Findings: closes the loop for Q-001..Q-080 with a guard; zero-violation policy of ADR-0130 section 1.
- Epic: all (closing gate)
- Band: 7 · Size: S · Tags: none
- Depends on: T-Q201, T-Q206, T-Q207, T-Q208, T-Q212, T-Q213, T-Q214, T-Q216, T-Q218, T-Q219, T-Q221, T-Q227, T-Q228, T-Q229, T-Q233, T-Q236, T-Q237, T-Q238, T-Q241, T-Q242, T-Q243, T-Q245, T-Q258, T-Q260, T-Q261, T-Q262, T-Q263, T-Q264, T-Q265, T-Q266, T-Q267, T-Q268, T-Q269, T-Q270, T-Q271, T-Q272, T-Q273, T-Q274, T-Q275, T-Q279, T-Q280, T-Q281, T-Q282, T-Q283, T-Q284, T-Q285, T-Q286, T-Q287, T-Q288, T-Q289, T-Q290, T-Q291
- Docs-first step: update `prevention.md` status and the CLAUDE.md "Code conventions" pointer if wording changes (operator reviews CLAUDE.md edits); ADR-0130 status line.
- Acceptance: **Redesign carve-out (operator decision 2026-11-22, ADR-0130 amendment):** `template_logic.toml` keeps exactly the 83 D3 entries (T-Q273), each tagged with its T-UR owner task, and the redesign's last task burns them to zero; the gate fails if that file holds any entry without a T-UR owner tag or more than 83 entries. Every other file in `tests/architecture/allowlists/` has no `[[entry]]` and an empty `[ceilings]`; `[[permanent]]` and `[[framework]]` entries remain only with a reason recorded in an ADR-0130 amendment; guards run strict in `just ci` and pre-commit; `allowlist_by_qid.py` prints burn-down total 0; a deliberately introduced violation per guard class fails; the T-Q16 dry run is repeated and recorded. This is not a v4 gate: the v4 T-E00 gate is the `[pre-v4-P3]` tag only.
- Outcome (2026-11-22): new guard G32 `tests/architecture/test_closing_gate.py` (no `[[entry]]` or non-zero ceiling outside `template_logic.toml`; kept rows need a reason and a named path in ADR-0130; carve-out capped at 83 entries each with a valid `owner = "T-URnn"`, now tagged in the TOML; `_ratchet.Entry.owner` added). ADR-0130 closing amendment lists the inventory. Final inventory: functional_first 22 (2 permanent, 20 framework), sql_sites 8 permanent, prod_db_refs 6 permanent, read_filters 4 permanent, money_scope 3 permanent, template_logic 83 carve-out entries; all other allowlists empty, suppression ceilings 0, no strict-xfail invariants, no `exists-migrating` registry rows, all `pyproject.toml` per-file-ignores carry reasons. `allowlist_by_qid.py` does not exist in the tree, so the burn-down total is read by the gate itself.
- Operator question blocking it: none.
- Final-backlog note: Depends on every task that owns allowlist entries or a ceiling (list computed from `allowlist_by_qid.py` output) plus T-Q274 and T-Q275.
- Removes allowlist entries: none (tags the 83 `template_logic.toml` entries with their T-UR owner)
- Done when: no allowlist entry to delete other than the carve-out above; the guards stay green (counts decremented incidentally by this task are re-read from `allowlist_by_qid.py` at start); the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q276 [S] Soft-deleted accounts are excluded from balances, stats and converters
- Findings: Q-030, Q-015 (OQ-15, answered 2026-11-21).
- Epic: E01
- Band: 2 · Size: M · Tags: none
- Depends on: T-Q227, T-Q221, T-Q268
- Docs-first step: [ADR-0136](../../adr/0136-soft-deleted-accounts-excluded-from-balances-stats-converters.md) (written with T-Q-DECISIONS); update `docs/requirements.md` where account deletion is described.
- Acceptance: failing tests first, each asserting exact values: (1) a soft-deleted account's balance is absent from net worth and fortune (`compute_fortune`) and from the account balances list; (2) it is absent from stats and analytics totals; (3) it is absent from converter account lists; (4) an archived category's transactions are still counted in budget, stats and totals; (5) two-user isolation: a second user's deleted and live accounts neither leak into nor change the first user's figures. Undo of the account delete restores all figures. One predicate per read path in the canonical owner (no per-caller copies).
- Operator question blocking it: none (OQ-15 answered).
- Removes allowlist entries: none
- Wave: 11 (after T-Q227 in wave 8, T-Q234 in wave 9 and T-Q260 in wave 10, to avoid conflicts in `services/balance.py`, `services/aggregates.py` and account read helpers).


## Operator decisions 2026-11-22

The operator answered the deferred questions on 2026-11-22. Each decision below is a task recorded docs first (CLAUDE.md "Change policy"); the ADR amendments named here are written in the DECISIONS-1122 change, the code lands with the task. All run before T-Q232 (waves 14b to 14d below). None of these tasks adds an allowlist entry; T-Q283 records three permanent `money_scope` entries (its implementation task edits the TOML, the DECISIONS-1122 change edits no allowlist).

### ✅ T-Q279 [S] Archived categories reserve no budget; their actuals still count
- Findings: Q-030, Q-015 (OQ-15 refined 2026-11-22); reverses the T-Q227 reading of OQ-15.
- Epic: E01
- Band: 2 · Size: M · Tags: none
- Depends on: T-Q227, T-Q276
- Docs-first step: [ADR-0136](../../adr/0136-soft-deleted-accounts-excluded-from-balances-stats-converters.md) amendment 2026-11-22 (operator decision): archived categories reserve **no budget from the month they were archived onward** (past months keep it), anywhere (forecast planned-budget overlay, Budget page, yearly grid, monthly plan); transactions already booked in an archived category still count in spent, net worth, analytics and forecast actuals. `docs/requirements.md` F2.2b.
- Acceptance: failing tests first, exact values. **Archive is effective from the archive month (operator decision 2026-11-22):** a category archived in month M reserves no budget from M onward; months before M keep its budget (Budget page, yearly grid and plan for past months show it as before). Seed an expense category with a default budget of 30000 minor units and one posted expense of 4500 in it, archived in month M: (0) month M-1 still shows the 30000 budget and counts it in `budgeted_minor`; for month M and later: (1) the forecast overlay adds 0 for it, and the monthly-table `Planned budget` for that category is 0; (2) the Budget page and yearly grid list no budgeted row for it and `budgeted_minor` totals exclude its 30000; (3) `spent_minor`, analytics totals and the forecast actual events still include the 4500; (4) the INV-9 invariant test (T-Q227) is rewritten to this rule and passes; (5) two-user isolation: a second user's archived category changes nothing. `services/categories` keeps one owner: a `budgeted_expense_category_ids` (archived excluded) beside the actuals selector `expense_category_ids` (archived included), both registered in `canonical_modules.toml` if new.
- Operator question blocking it: none (answered 2026-11-22).
- Removes allowlist entries: none
- Wave: 14b.
- Done when: no allowlist entry to delete; guards stay green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q280 [S] Planned rows on soft-deleted accounts are hidden from planned totals
- Findings: Q-026, Q-030 (ADR-0136 decision 1).
- Epic: E01
- Band: 2 · Size: S · Tags: none
- Depends on: T-Q276, T-Q279
- Docs-first step: ADR-0136 amendment 2026-11-22 (operator decision): planned rows whose account is soft-deleted are hidden from planned totals and `planned_base_amounts`, the same as every other derived number. `docs/requirements.md` F2.2b.
- Acceptance: failing test first: a planned expense of 2500 on an account that is then soft-deleted is absent from the Accounts-tab planned net, the Today/Budget committed figure and `planned_base_amounts` (exact sums before and after); undo of the account delete restores the exact earlier sums; a second user's planned rows are unaffected.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Wave: 14b (same owner as T-Q279, merge after it).
- Done when: no allowlist entry to delete; guards stay green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q281 [M] One rounding mode: HALF_EVEN at every `round_div` call site
- Findings: Q-076 (OQ-ROUND answered 2026-11-22).
- Epic: E05
- Band: 3 · Size: M · Tags: none
- Depends on: T-Q229
- Docs-first step: [ADR-0006](../../adr/0006-multi-currency-model.md) amendment 2026-11-22 (operator decision): every rounding call site uses HALF_EVEN; the per-site mode table of the 2026-11-21 amendment is replaced; displayed amounts may shift by 0.01 (the money minimum unit). The `mode` argument of `round_div` / `round_scaled` is removed or fixed to HALF_EVEN (no HALF_UP constant). `docs/requirements.md` money rules.
- Acceptance: failing tests first with exact tie values per former HALF_UP site (`to_minor_units`, `percent_to_bps`, display rounding, `recurring_formula._apply_coefficient`): a value at an exact `.5` tie rounds to the even neighbour (e.g. 2.5 minor -> 2, 3.5 -> 4); the pinned T-Q222 tie tests are updated to the new expected values; no `HALF_UP` symbol remains under `src/`; a `banned_patterns` rule forbids `ROUND_HALF_UP` outside tests.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Wave: 14c.
- Done when: no allowlist entry to delete; guards stay green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q282 [M] Every bad query parameter is a 422, everywhere
- Findings: Q-023, Q-033.
- Epic: E03
- Band: 4 · Size: M · Tags: none
- Depends on: T-Q233, T-Q267
- Docs-first step: [ADR-0141](../../adr/0141-one-amount-parser-and-bounded-request-parameters.md) amendment 2026-11-22 (operator decision), replacing decision 3's "list filters degrade to no filter": a malformed `year`, `month`, date or integer query parameter returns 422 with a visible message on `/plan`, `/ledger`, `/forecast`, `/budget`, `/today` and every other route; there is no silent fallback to the current period. `docs/requirements.md` request-parameter note.
- Acceptance: failing tests first, one parametrised test per route in `app.routes` that takes a typed query parameter: `year=abc`, `month=13`, `date=2026-02-30`, `account_id=x` each return exactly 422 and the body or toast names the parameter; a valid or absent parameter still renders (default period); HTMX fragment routes return the error partial, not a page swap.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Wave: 14c.
- Done when: no allowlist entry to delete; guards stay green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q283 [S] Three permanent `money_scope` entries with written reasons
- Findings: Q-076 (G27).
- Epic: E05
- Band: 3 · Size: S · Tags: none
- Depends on: T-Q229
- Docs-first step: [ADR-0130](../../adr/0130-prevention-regime-and-full-architectural-compliance.md) amendment 2026-11-22 (operator decision): the three false positives of the money-scope scanner become `[[permanent]]` entries, the scanner is unchanged: `web/charts.py` (chart geometry, pixels not money), the rate-limit `Retry-After` seconds, and `services/balance.sparkline_points` scaling (plot coordinates, not amounts). Each entry carries its reason in the allowlist and in this amendment.
- Acceptance: failing test first (`test_money_scope.py`): the three paths are `[[permanent]]` with a non-empty `reason`, the scanner code and its fixtures are unchanged, and any other money-scope hit still fails. The `_ratchet.py` total does not rise: the entries replace the three burn-down entries and the burn-down total falls by three.
- Operator question blocking it: none.
- Removes allowlist entries: converts three `money_scope.toml` entries to `[[permanent]]` (this task's implementation edits the TOML).
- Wave: 14b (owns `money_scope.toml`).
- Done when: the three entries are permanent with reasons; guards stay green; the CLAUDE.md handoff checklist is complete.

### ✅ T-Q284 [M] User-scoping guard resolves `OwnedTable` specs
- Findings: Q-025 (ADR-0130 G7).
- Epic: E02
- Band: 3 · Size: M · Tags: none
- Depends on: T-Q260
- Docs-first step: ADR-0130 amendment 2026-11-22 (operator decision): `tests/architecture/_user_scoping.py` resolves each `repositories/_shared.OwnedTable` spec and checks every statement generated per table; dynamic-table SQL is no longer skipped.
- Acceptance: failing test first: a deliberately unscoped statement generated for one `OwnedTable` (fixture spec without `user_id = ?`) fails the guard naming the table; every real `OwnedTable` (accounts, categories, planned, transactions, recurring rules, budgets) passes; the number of skipped dynamic statements reported by the guard is 0.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Wave: 14b.
- Done when: no allowlist entry to delete; guards stay green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q285 [L] Real service functions own validation and the single `db_transaction`
- Findings: Q-045, Q-024 (G8).
- Epic: E02
- Band: 2 · Size: L · Tags: none
- Depends on: T-Q267, T-Q262
- Docs-first step: [ADR-0142](../../adr/0142-crud-service-entry-points-routers-never-import-repositories.md) amendment 2026-11-22 (operator decision): the pass-through service bindings of T-Q241 are replaced by real functions in `services/` that own input validation and the single `db_transaction` of a mutation (a service calling two or more mutators uses one transaction); routers keep one service call. Decide whether guard G8 (one transaction per multi-mutator service) becomes a real guard and record it in the same amendment and `prevention.md`.
- Acceptance: failing tests first: for each CRUD entity (accounts, categories, planned, transactions, recurring rules, budgets) a service-level test asserts the exact validation error for bad input and that a failure after the first mutator rolls back both mutators and both audit rows (value assertions); no module under `services/` re-exports a repository function as a binding (architecture test lists zero pass-throughs); routers call no repository (unchanged guard). If G8 is made a guard, a deliberately introduced two-transaction service fails it.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Wave: 14d.
- Done when: no allowlist entry to delete; guards stay green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q286 [M] Cross-currency formula amounts convert everywhere
- Findings: Q-010 (OQ-8 answered 2026-11-22), follow-up of T-Q215.
- Epic: E01
- Band: 2 · Size: M · Tags: none
- Depends on: T-Q215
- Docs-first step: `docs/requirements.md` formula/recurring lines and [ADR-0139](../../adr/0139-canonical-fx-converter-cache-only-one-missing-rate-policy.md) amendment 2026-11-22 (operator decision): a formula that mixes currencies converts each term through `FxConverter.to_base` on the recurring page, the formula preview, promotion and every recurring view, not only the ledger.
- Acceptance: failing tests first with a PLN rule referencing an EUR category at a cached rate of 4.30: the recurring page, preview and promoted transaction show the same exact base amount (e.g. EUR 100.00 term -> 43000 minor PLN); a missing rate raises `FxUnavailableError` (503) as for every other conversion; no view sums raw minor units across currencies.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Wave: 14b.
- Done when: no allowlist entry to delete; guards stay green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q287 [M] `include_deleted` defaults to False; writes against soft-deleted parents are refused
- Findings: Q-025 (T-Q268 follow-up).
- Epic: E02
- Band: 3 · Size: M · Tags: none
- Depends on: T-Q268, T-Q260
- Docs-first step: ADR-0022 amendment 2026-11-22 (operator decision), reversing the T-Q268 default for `_shared.require_owned`, `users.owns_accounts` and `webauthn._get_by_id`: the default is `include_deleted=False`; a write whose parent is soft-deleted is refused; history and audit reads pass `include_deleted=True` explicitly.
- Acceptance: failing tests first: creating a transaction, planned row or rule on a soft-deleted account or category is refused with the exact error; revoking an already revoked passkey still reports "already revoked" (explicit `include_deleted=True`); the history views still list tombstoned parents; second-user isolation holds.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Wave: 14c.
- Done when: no allowlist entry to delete; guards stay green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q288 [S] Recurring undo is scoped to its own batch and clears the override link
- Findings: Q-024.
- Epic: E02
- Band: 3 · Size: S · Tags: none
- Depends on: T-Q228
- Docs-first step: [ADR-0019](../../adr/0019-soft-delete-and-audit-log.md) and ADR-0022 amendment 2026-11-22 (operator decision): the recurring undo accepts only audit rows written by the batch being undone, and also clears an override's `promoted_to_txn_id` (compare-and-set, as the planned undo does).
- Acceptance: failing tests first: an undo request carrying an audit id from another batch (or another user) is refused and changes nothing; undoing a promotion that consumed an override leaves `promoted_to_txn_id` NULL and the rule and override exactly as before the promotion; a rule edited after the batch is skipped and reported (unchanged).
- Operator question blocking it: none.
- Removes allowlist entries: none
- Wave: 14c.
- Done when: no allowlist entry to delete; guards stay green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q289 [M] CSRF token bound to the session
- Findings: Q-066 (security hardening).
- Epic: E06
- Band: 3 · Size: M · Tags: none
- Depends on: T-Q274
- Docs-first step: amendment 2026-11-22 (operator decision) to [ADR-0065](../../adr/0065-csrf-dev-cookie-name-and-meta-token.md) (the CSRF ADR; `docs/requirements.md` "CSRF" line): the token is an HMAC of the session id (keyed by the cookie secret), rotated on login and logout; double-submit compares the header against the recomputed value.
- Acceptance: failing tests first: a valid token from session A is rejected (403) on session B; the token changes after login and after logout; a token without a session is rejected on state-changing routes; the dev cookie-name rule of ADR-0065 is unchanged; the E2E form flow still posts successfully.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Wave: 14d (after T-Q274 owns the ASGI middleware).
- Done when: no allowlist entry to delete; guards stay green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q290 [M] Scheduled daily FX refresh
- Findings: FX cache (ADR-0139 cache-only converter, `requirements.md` F7.4).
- Epic: E01
- Band: 3 · Size: M · Tags: ops
- Depends on: T-Q212
- Docs-first step: **ADR to write at implementation start, at the next free number** (0144 did not exist when this was recorded; T-Q274 may take 0144, so check `ls docs/adr` and take the next one; then update `docs/adr/README.md` and `docs/requirements.md` F7.4). Content (operator decision 2026-11-22): source is **NBP table A** (official PLN mid rates, no API key; replaces the ECB/frankfurter source of F7.4 and ADR-0139's refresh path, which the ADR supersedes or amends); outbound HTTPS from the host; it runs as an **in-app daily background task** (like the retention task), once a day **after 12:30 Europe/Warsaw** (NBP publishes around noon); no host timer, so no terraform change; failures are logged and the cache keeps the last rates (page renders stay cache-only, ADR-0139); rates must be `> 0`; agents never `terraform apply` prod (CLAUDE.md "Releases").
- Acceptance: failing tests first with an injected fake rate source and injected clock (no network in tests): the task does nothing before 12:30 Europe/Warsaw, runs once after it and not again the same day; one run inserts exactly the new `(date, from, to, rate)` rows and is idempotent on a second run; a source failure logs the error, leaves the cache unchanged and does not break page renders; a non-positive rate is rejected; the existing `cli.refresh_fx` and the job share one function.
- Operator question blocking it: none (decided 2026-11-22; scheduling mechanism chosen in the ADR).
- Removes allowlist entries: none
- Wave: 14b (new module and ops files; no allowlist TOML).
- Done when: ADR written and indexed; guards stay green; the Acceptance above holds; any terraform/host change is a PR for the operator's approved apply; the CLAUDE.md handoff checklist is complete.

### ✅ T-Q291 [M] `PasswordHasher` port with a bcrypt adapter
- Findings: Q-074.
- Epic: E04
- Band: 3 · Size: M · Tags: none
- Depends on: T-Q264
- Docs-first step: [ADR-0021](../../adr/0021-functional-style-no-oop.md) amendment 2026-11-22 (operator decision), reversing the T-Q264 note "bcrypt stays in `services/_passwords`": `domain/ports.PasswordHasher` (Protocol: `hash`, `verify`), bcrypt adapter in `adapters/`, injected from the web edge like `TokenSource`.
- Acceptance: failing tests first: services receive the hasher as an argument; a fake hasher makes `users.create_user`, login verification and password change run with no bcrypt import under `services/`; the bcrypt adapter keeps rounds and constant-time behaviour (hash round-trip and wrong-password test); `test_purity.py` needs no `_passwords` exception.
- Operator question blocking it: none.
- Removes allowlist entries: none (deletes any `_passwords` purity exception if one exists).
- Wave: 14b.
- Done when: no allowlist entry to delete; guards stay green; the Acceptance above holds and the CLAUDE.md handoff checklist is complete.

### ✅ T-Q295 [S] Pre-commit hook skips e2e; e2e runs once per wave, alone
- Findings: none (operator decision 2026-11-22 18:00 and 18:05).
- Epic: E04
- Band: 3 · Size: S · Tags: none
- Depends on: none
- Docs-first step: [ADR-0120](../../adr/0120-pre-commit-is-the-local-gate.md) amendment 2026-11-22 and a cross-reference in [ADR-0097](../../adr/0097-per-batch-ci-policy-and-fast-precommit-pytest.md): the hook scope excludes `tests/e2e`; e2e runs after each orchestrator wave and before every PR, by the orchestrator alone; an agent that genuinely needs it pushes its `wi/**` branch and reads the `e2e.yml` run.
- Acceptance: `just test-fast` and `just test-changed` pass `--ignore=tests/e2e` in testmon and full-suite modes; `just test`, `just ci` and `ci.yml` collect what they did before; `.github/workflows/e2e.yml` runs `tests/e2e` on `wi/**` pushes and `workflow_dispatch` in the pinned Playwright container; CLAUDE.md and the orchestrator skill state the cadence.
- Operator question blocking it: none.
- Removes allowlist entries: none.
- Wave: 14b.
- Done when: the Acceptance above holds and guards stay green.

### ✅ T-Q297 [S] e2e runs on every PR to main and is a required check
- Findings: none (operator decision 2026-11-22: "fold it into this PR, add it also to the main branch's policy").
- Epic: E04
- Band: 3 · Size: S · Tags: none
- Depends on: T-Q295
- Docs-first step: [ADR-0120](../../adr/0120-pre-commit-is-the-local-gate.md) and [ADR-0097](../../adr/0097-per-batch-ci-policy-and-fast-precommit-pytest.md) amendments 2026-11-22 (T-Q297): `e2e.yml` also runs on `pull_request` to `main` and its job `tests/e2e (Chromium, Playwright container)` joins the required checks of `protect-main`; the local pre-PR e2e run is no longer required (`just test-e2e` stays optional).
- Acceptance: `e2e.yml` triggers on `wi/**` push, `workflow_dispatch` and `pull_request` to `main`, job name unchanged; `scripts/check_github_settings.py` `REQUIRED_CHECKS` names the e2e job and a guard keeps it equal to the workflow's job name; `test_visual_image_pin.py` covers visual.yml, e2e.yml and the justfile (one digest-pinned image, tag equals the locked playwright version); CLAUDE.md handoff item 3 and orchestrator skill section 5 step 4 state the new cadence. The orchestrator applies the ruleset change through the API after the PR exists (not part of the code change).
- Operator question blocking it: none.
- Removes allowlist entries: none.
- Wave: 14f.
- Done when: the Acceptance above holds and guards stay green.

### Testing coverage review (2026-11-22)

- Findings: operator review of the test and gate stack (T-Q298, docs only). What exists today:
  - **Pre-commit hooks** (local gate, ADR-0120): ruff, mypy, import-linter, guards, and the affected tests through testmon. `tests/e2e` is excluded from the hook (ADR-0120 amendment 2026-11-22, T-Q295).
  - **PR CI** `ci.yml`: full suite with the 90% coverage gate on every PR to `main`; required check `just ci (Python 3.12, ubuntu-latest)`.
  - **`e2e.yml`**: `tests/e2e` in the pinned Playwright container (Chromium, 2 workers). Runs on push to `wi/**`, on `pull_request` to `main` (required check `tests/e2e (Chromium, Playwright container)`, T-Q297) and on `workflow_dispatch`.
  - **`visual.yml`**: visual regression in the same pinned container. Runs on PRs to `main` (the visual job only when templates, CSS or `tests/visual` change), Mondays 04:43 UTC and on dispatch. `visual-gate` is the always-run status check (ADR-0027 amendment, T-Q251); it is not yet a required check.
  - **Drill gate**: `drill.yml` in `mode=gate` posts `drill-gate` on the PR head SHA. Non-deploy PRs skip the real gate (ADR-0121).
  - **Weekly mutation**: `mutation.yml`, Mondays 03:17 UTC, advisory, over `domain` and `services` (ADR-0131). Never a merge gate.
  - **`tests/e2e/test_crawl.py`**: crawls the route inventory and asserts no 4xx/5xx, no console errors, no failed requests, no duplicate ids and no horizontal scroll at 375 and 1440.
  - **`tests/e2e/test_accessibility.py`**: a smoke test only. It asserts the skip link is the first focusable element and jumps to `#main`, Tab reaches every top-level nav link in document order, and each primary route has a single `<h1>` and a `<main id="main">`. No axe-core, no contrast check, no Lighthouse.
- Gaps (each has a follow-up below, none started): e2e runs on Chromium only (T-Q299); no axe-core sweep and no Lighthouse/CWV budgets in CI (T-Q300); the crawl covers 375 and 1440 but not 1024 (T-Q301); the drill DB is not seeded (T-Q302).

### ✅ T-Q298 [S] Testing coverage review recorded; follow-ups filed (docs only)
- Findings: operator agreed the follow-ups on 2026-11-22 (see "Testing coverage review (2026-11-22)" above).
- Epic: E04
- Band: 3 · Size: S · Tags: docs
- Depends on: T-Q297
- Docs-first step: this note and entries T-Q299 to T-Q302; [ADR-0099](../../adr/0099-release-and-environment-policy.md) amendment 2026-11-22 (current required status contexts).
- Acceptance: the review note and T-Q299 to T-Q302 are in this file, each follow-up marked not started; ADR-0099 lists the current required contexts, including the e2e check, with a dated amendment; `docs/CHANGELOG.md` has a line. No code or test change.
- Operator question blocking it: none.
- Removes allowlist entries: none.
- Wave: 14f (docs only).
- Done when: the Acceptance above holds.


### ✅ T-Q303 [S] Orchestrator ways of working from the remediation run (docs and skill only)
- Findings: 2026-11-22 remediation run lessons (heavy runs on the shared laptop, agents running 3-6 h, guard-gaming fixes, unhooked merges).
- Epic: E04
- Band: 3 · Size: S · Tags: docs, ops
- Depends on: T-Q298
- Docs-first step: [ADR-0066](../../adr/0066-orchestrator-mode-skill.md) amendment 2026-11-22.
- Goal: fold the lessons into `.claude/skills/orchestrator-mode/SKILL.md`, the shared `brief-common.md`, and CLAUDE.md.
- Acceptance: the skill covers hook-only testing in the brief, delegating heavy work to GitHub, per-plan heavy locks, the agent runtime budget, guard-gaming rejection, gated merges and prune extras, operator-step and question rules; `brief-common.md` exists; no code change.
- Operator question blocking it: none.
- Removes allowlist entries: none.

### ✅ T-Q304 [S] `just merge-item <ID> "<msg>"` recipe for the gated merge chain
- Findings: merges skip the hooks, so the orchestrator ran guards, lint-imports, ruff and mypy by hand (T-Q303).
- Epic: E04
- Band: 3 · Size: S · Tags: ops
- Depends on: T-Q303
- Docs-first step: ADR-0066 amendment 2026-11-22; skill section 5.
- Goal: `scripts/ci/merge_item.sh` and the `merge-item` recipe: refuse on `main`, a dirty tree or an unfinished merge; merge `wi/<work>/<ID>` with `--no-ff`; on conflict abort and exit non-zero; run the four checks; push; prune worktree, local and origin branch and empty `worktree-agent-*` branches, only after every step returned 0.
- Acceptance: a failed check leaves the merge commit in place, unpushed and unpruned. Not run against the real work branch in this task.
- Operator question blocking it: none.
- Removes allowlist entries: none.

### T-Q305 [M] Compose change must apply to an existing host; failure detail in the status file
- Findings: release v3.1.0 (2026-11-22, run 45066657240) failed at `compose` on the live host; the rollback to the v3.0.8 image failed the same way (a rollback keeps the new compose template); prod was down (502) until the v3.0.8 release was re-run. The drill gate passed because a drill is a fresh host.
- Cause (confirmed from the host journal, 20:39:06): ADR-0133 / T-Q203 added `ipam` (subnet `172.28.0.0/24`) to the existing `edge` network. Compose tried to recreate the network before it recreated the old bridged Caddy, which was still attached:
  ```
  bp-agent: compose: up: Container budget-planner-litestream-restore  Stopping
   Container budget-planner-litestream-restore  Stopped
   Network budget-planner_edge  Removed
  Error response from daemon: error while removing network: network budget-planner_edge has active endpoints (name:"budget-planner-caddy" id:"<id>")
  ```
  Every later attempt, including the v3.0.8 image rollback that kept the new template, failed with `Error response from daemon: container <id> is not connected to the network budget-planner_edge` (half-migrated: old Caddy `Up` with published 80/443 on `172.18.0.0/16`, app, litestream and probe `Exited`).
- Repair and state (operator): break-glass `docker compose down --remove-orphans` (no `-v`) plus a converge with main's template at 20:56 UTC (outage 20:39 to 20:56), then v3.1.0 released successfully at 21:05 UTC. Prod now has `budget-planner_edge` re-created on `172.28.0.0/24`. A rename reusing that subnet would fail with `Pool overlaps with other one on this address space`, so `edge_v2` uses `172.30.0.0/24` (gateway `172.30.0.1`) and the guard checks subnet overlap against the latest tag.
- Epic: E04
- Band: incident · Size: M · Tags: ops, deploy
- Depends on: T-Q203
- Docs-first step: ADR-0133, ADR-0111 and ADR-0099 amendments 2026-11-22; CHANGELOG.
- Goal: rename the network `edge` -> `edge_v2`; the agent removes a still-bridged Caddy before `up` (80/443 handover) and, if `up` fails, removes the project's containers once (`compose rm --force --stop`, never `-v`) and retries, so a half-migrated host converges; the agent removes the legacy `budget-planner_edge` after a successful `up` (best effort); `status.json` carries `error_detail` (scrubbed, one line, 200 chars, compose failures only); a unit guard fails when a network keeps its name but changes its definition against the latest `v*` tag.
- Acceptance: agent unit tests for the cleanup and the scrubbing (no `NAME=value` leaks, 200-char cap, non-compose codes empty); guard test green; `terraform fmt/validate/test` green. An existing v3.0.8 host converges and a rollback works (to be proven by the T-Q306 drill, not by this task).
- Operator question blocking it: none. Operator: read the host journal (`journalctl -u bp-agent`) of the failed run to confirm the cause.
- Removes allowlist entries: none.

### T-Q306 [L] The drill gate is an upgrade from the prod version (re-scoped 2026-11-23) → ADR-0149, ADR-0099, ADR-0127 §7, ADR-0132
- Findings: T-Q305; ADR-0099 amendment 2026-11-22; T-D127, T-D115, T-D158 (fresh-boot vs running-host bugs).
- Epic: E04
- Band: follow-up · Size: L · Tags: ci, deploy
- Depends on: T-Q305
- Docs-first step: ADR-0149, ADR-0099 amendment 2026-11-23, `docs/requirements.md` (drill gate), CHANGELOG (2026-11-23).
- Re-scoped 2026-11-23 (operator): no separate `mode=upgrade`. `mode=gate` itself becomes the upgrade drill for every PR the ADR-0121 skip does not cover. That answers the old operator question. The baseline is the version prod serves, not the latest tag.
- Work items:
  - (a) `scripts/ci/prod_baseline.py`: newest `prod` deployment whose latest status is `success` → tag; check the tag is an ancestor of `origin/main`; resolve `<tag>@sha256:<digest>` from GHCR; fail closed otherwise. Unit-tested with recorded API payloads (v3.1.1 tagged but not deployed → v3.1.2 / earlier).
  - (b) `terraform.yml`: optional input to apply `terraform/` from a given ref (the baseline tag) while the tooling stays at the workflow ref.
  - (c) Drill-only helper `seed-demo` (cloud-init `bin/`, rendered on `drill` only, like `restore-from-prod`): stop app + litestream, move the DB aside, install the demo DB copied from the runner, integrity check, chown 10001, start, wait `/ready`. The workflow copies `data/demo.sqlite` from the baseline tag, writes marker rows (`rehearsal_marker.sh`), waits for replication and records the generation.
  - (d) `drill.yml` gate jobs: baseline apply + smoke → seed → detection (`host_release.py replaced` on the PR plan) → writer + upgrade apply → verify (in place: `server_replaced=false`, converged on the PR ref, all committed rows, same generation, integrity; replacement: drain, `--require-restore`, seeded generation restored, 0 lost rows, integrity, tailnet cleanup + rename) → rollback apply (`rollback: true`, in place only) + smoke + integrity → teardown. Writer steps use `set +e` (T-D156 lesson).
  - (e) Gate verdict names the failing phase; TTL covers the longer run; `mode=explore` unchanged.
  - (f) Runbooks / workflow headers: `drill.yml` header, `deploy.md` (what the gate proves and what it does not: release bundles, host drift, no fresh boot of the PR head).
- Tests: `prod_baseline.py` unit tests; workflow-wiring tests (phase order, rollback only on the in-place path, `drill-gate` posted only from `gate-result`, no `prod-restore-read` or `restore_source` in `drill.yml`); render tftest (`seed-demo` only on `drill`); `seed-demo` script test like `test_litestream_restore_guard.py`.
- Acceptance: a throwaway branch that changes an existing compose network's definition under the same name (the v3.1.0 case; skip the T-Q305 unit guard on that branch only) fails the upgrade or rollback phase; a normal PR passes all three phases; a VM-replacing PR takes the replacement path and passes; record the run times of the first green gates in this entry.
- Operator question blocking it: none (answers 2026-11-23: in place + rollback, demo seed via the restore path, replacement branch included; release-bundle risk and host drift accepted; cost accepted).
- Removes allowlist entries: none.
### ✅ T-Q310 [S] Forecast batching test independent of the wall clock
- Findings: release CI 2026-11-23 (run 45140093769) failed `test_forecast_numbers_unchanged_by_batching`: every month off by 500 minor units; green in PR CI on 2026-11-22. Root cause: `recurring_repo.create_rule` derives `next_due` from `clock.today_local` (repository edge), and `seed_world` seeded rules with the real date while the test passed a fixed `TODAY`.
- Epic: E04
- Band: incident · Size: S · Tags: tests, clock
- Depends on: none
- Docs-first step: CHANGELOG (no ADR; ADR-0140 unchanged).
- Goal: `seed_world` pins the clock (`clock.frozen`) to its `today` while creating rules, so the stored `next_due` and the forecast do not depend on the wall date.
- Acceptance: the forecast test is parametrized over three wall dates (seeded under `clock.frozen`) and fails on the old fixture (2 of 3 dates), passes now.
- Removes allowlist entries: none.

### T-Q311 [M] Frozen test clock by default and a CI date matrix
- Findings: release CI 2026-11-23 (T-Q310): date-dependent tests pass on the authoring day and fail later.
- Epic: E04
- Band: incident follow-up · Size: M · Tags: tests, clock, ci
- Depends on: T-Q310
- Docs-first step: ADR-0140 amendment 2026-11-23; prevention.md G32.
- Goal: autouse `clock.frozen(BUDGET_TEST_NOW or 2026-11-21T12:00:00Z)` for every test (`real_clock` marker opts out); CI job `pytest (shifted clock)` over month end, leap day, year end and the Warsaw DST switch; guard G32 bans the SQLite clock in runtime SQL.
- Acceptance: suite green under the default and under all four matrix instants; a route run through `TestClient` sees the frozen date; G32 fails on a fixture `datetime('now')`.
- Removes allowlist entries: none (adds none).

### T-Q314 ✅ [S] Background-task crashes are visible
- Findings: Q46 follow-up (operator 2026-11-23): `retention_task.run_forever` / `fx_refresh_task.run_forever` catch only expected job errors; any other exception ends the task unobserved and the job silently never runs again.
- Epic: E04
- Band: follow-up · Size: S · Tags: reliability, observability
- Depends on: T-Q271
- Docs-first step: ADR-0130 amendment 2026-11-23 (T-Q314); requirements F7.4.
- Goal: done-callback logs `background_task_crashed` and flags the job; `/health/fx` 503 `refresh_crashed`; no restart, no broad except.
- Acceptance: tests for unexpected error, JOB_ERRORS unchanged, cancellation silent, health 503.
- Removes allowlist entries: none (adds none).

### ✅ T-Q312 [M] Harden CSRF against login CSRF (Origin check, token lifetime, browser binding)
- Findings: Q44 follow-up (operator decision 2026-11-23): pre-session tokens are universal and never expire; no Origin / Sec-Fetch-Site check, so login CSRF rests on cookie integrity alone.
- Epic: E04
- Band: security follow-up · Size: M · Tags: security, csrf, web
- Depends on: T-Q289
- Docs-first step: ADR-0065 amendment 2026-11-23; CHANGELOG.
- Goal: (1) unsafe methods require `Sec-Fetch-Site: same-origin`, else `Origin` equal to the configured public origin (`webauthn_origin`), else 403 `cross_origin`; (2) tokens carry a MAC-covered issued-at and pre-session tokens older than 2 h are refused, an expired login form POST re-renders the login page with a fresh token and a notice; (3) pre-session tokens are bound to a per-browser id cookie (`__Host-csrf-bid`, `csrf-bid` in dev).
- Acceptance: tests for cross-site Sec-Fetch-Site, mismatched Origin, both headers absent, same-origin accepted, expired pre-session token (frozen clock) re-renders the login page, a token minted for another browser id is refused, session flow unchanged, health exempt. e2e fixtures send Origin on API-client requests.
- Removes allowlist entries: none (adds none).

### ✅ T-Q313 [S] Rehash passwords on login when the bcrypt cost changed
- Findings: operator decision 2026-11-23 (Q43 follow-up): raising `BUDGET_BCRYPT_ROUNDS` leaves old-cost hashes, so unknown-user dummy verifies (T-Q291) and real users differ in timing until hashes are upgraded.
- Epic: E04
- Band: security follow-up · Size: S · Tags: auth, security
- Depends on: T-Q291, T-Q311
- Docs-first step: ADR-0074 amendment 2026-11-23; CHANGELOG.
- Goal: `PasswordHasher.needs_rehash`; after a successful password verify, a hash at another cost is replaced at the configured cost (`users.rehash_password`, audit action `password_rehash`); not a password change (no rotation flag, no session revocation); a failure is logged and the login continues.
- Acceptance: tests assert upgraded hash cost and verification, audit row, session issued, same-cost and wrong-password logins untouched, second user untouched, repository failure keeps login working.
- Removes allowlist entries: none (adds none).

### T-Q309 [S] Prod PR plan works without a Tailscale OAuth client
- Findings: PR #44 `terraform.yml` run 45072238526, `plan (prod)`: `TF_VAR_tailscale_oauth_client_id/secret is empty`. ADR-0132 checklist step 4 deleted `TS_OAUTH_*` from `prod-plan`; the input check and the provider were never adapted.
- Epic: E04
- Band: incident · Size: S · Tags: ci, deploy
- Depends on: T-Q218
- Docs-first step: ADR-0132 amendment 2026-11-22 (T-Q309); CHANGELOG.
- Goal: the prod PR plan gets placeholder Tailscale credentials (`tf_env.py --plan-only`, `terraform-env` input `plan-only`) and plans with `-refresh=false`; prod apply still requires the real credentials.
- Acceptance: `test_tf_env.py` covers plan-only (prod placeholder, drill unchanged, apply unchanged); `terraform test` plan-only run shows no destroy or replace of `tailscale_tailnet_key.vm`; workflow wiring test green.
- Operator question blocking it: none. Operator: none needed; optional read-scoped OAuth client if PR drift detection for prod is wanted.
- Removes allowlist entries: none.

### ✅ T-Q308 [S] merge-item skips worktree-agent branches still checked out
- Findings: the final prune loop in `scripts/ci/merge_item.sh` ran `git branch -D` on empty `worktree-agent-*` branches that a live worktree still had checked out; git refuses, `set -e` exits non-zero after a successful merge, push and prune.
- Epic: E04
- Band: 3 · Size: S · Tags: ops
- Depends on: T-Q304
- Docs-first step: none (bug fix within T-Q304 scope; no requirement or ADR change).
- Goal: skip any branch named in `git worktree list --porcelain` (`branch refs/heads/<name>`) in the stale-branch loop.
- Acceptance: the stale-branch loop never calls `git branch -D` on a checked-out branch; `bash -n` passes on the script.
- Operator question blocking it: none.
- Removes allowlist entries: none.

### T-Q299 [S] e2e on Firefox and WebKit in `e2e.yml` (follow-up, not blocking)
- Findings: testing coverage review (2026-11-22, T-Q298).
- Epic: E04
- Band: follow-up · Size: S · Tags: ci
- Depends on: T-Q297
- Docs-first step: [ADR-0120](../../adr/0120-pre-commit-is-the-local-gate.md) amendment naming the browser matrix, written at implementation start.
- Goal: run `tests/e2e` on Firefox and WebKit as well as Chromium. The pinned Playwright container already ships both, so the cost is runner minutes only.
- Acceptance: `e2e.yml` runs a browser matrix (chromium, firefox, webkit) in the same pinned image; the existing job name `tests/e2e (Chromium, Playwright container)` is unchanged; the new contexts are not added to `protect-main` until an operator decision records it.
- Operator question blocking it: should the Firefox and WebKit contexts become required checks, or stay advisory until they are green?
- Removes allowlist entries: none.
- Wave: follow-up, not blocking.
- Done when: the Acceptance above holds and the new jobs are green on a `wi/**` push.

### T-Q300 [M] axe-core sweep and Lighthouse/CWV budgets in CI (follow-up, not blocking)
- Findings: testing coverage review (2026-11-22, T-Q298).
- Epic: E04
- Band: follow-up · Size: M · Tags: ci, a11y, perf
- Depends on: T-Q297
- Docs-first step: ADR-0027 amendment (budget values and the accessibility gate) and ADR-0120 amendment for the CI job, written at implementation start.
- Goal: a full axe-core accessibility sweep over every route in the crawl inventory (colour contrast included), and Lighthouse budgets on the same inventory: LCP < 2.5 s, CLS < 0.1, TBT < 200 ms, plus a JS and CSS budget per page type (app page: JS < 300 kB gzipped, CSS < 50 kB, from the web performance rules). Both run in CI inside the Playwright container.
- Acceptance: the axe job fails on serious and critical violations and prints the route and rule for each; the Lighthouse job fails when a budget is exceeded; budgets live in one versioned config file; neither job is required until an operator decision records it.
- Operator question blocking it: none (the budget values are the web performance rules as written).
- Removes allowlist entries: none.
- Wave: follow-up, not blocking.
- Done when: the Acceptance above holds on a `wi/**` push.

### T-Q301 [S] Crawl diagnostics at 1024 (follow-up, not blocking)
- Findings: testing coverage review (2026-11-22, T-Q298).
- Epic: E04
- Band: follow-up · Size: S · Tags: e2e
- Depends on: T-Q297
- Docs-first step: none beyond this entry (the viewer set is frontend-visual-audit's: 1440, 1024, 375).
- Goal: `tests/e2e/test_crawl.py` also runs at 1024, so the crawl matches the frontend-visual-audit viewport set.
- Acceptance: the same diagnostics (no 4xx/5xx, console errors, failed requests, duplicate ids, horizontal scroll) are asserted at 1024. A new failure is fixed or triaged in its own task; the check is not loosened.
- Operator question blocking it: none.
- Removes allowlist entries: none.
- Wave: follow-up, not blocking.
- Done when: the Acceptance above holds in `e2e.yml`.

### T-Q302 [M] Drill DB seeded from an anonymized snapshot (follow-up, not blocking)
- Findings: testing coverage review (2026-11-22, T-Q298). The drill DB is not seeded today.
- Epic: E04
- Band: follow-up · Size: M · Tags: ops, ci
- Depends on: none
- Docs-first step: ADR-0099 / ADR-0101 amendment naming the seed source, written at implementation start.
- Goal: seed the drill from the anonymized prod-shaped `data/demo.sqlite` (built by `just demo-build`), or an equivalent anonymized snapshot, so migrations and smoke run against realistic data shapes.
- Acceptance: the drill seeds from the snapshot; smoke asserts the seeded tables are non-empty; CI never reads prod data and never touches `data/budget.sqlite`.
- Open questions (to answer before implementation):
  1. Where does the snapshot live? `data/demo.sqlite` is tracked in git today; an object-store copy is the alternative.
  2. How fresh is it? Rebuild cadence, or rebuild on demand only.
  3. It is never real prod data. The drill receives only the output of the anonymizer (`build_demo_db.py`), and its source-basename tripwire stays.
- Removes allowlist entries: none.
- Wave: follow-up, not blocking.
- Done when: the Acceptance above holds on a drill run.

### Third round (2026-11-22, answers to deferred Q39 to Q42)

Q40 (promotion into an archived category stays refused, T-Q287) and Q42 (recurring undo duplicate-live-transaction case left as is) need no task; one-line amendments in ADR-0136 and ADR-0019.

### ✅ T-Q292 [M] NBP refresh hardening and `/health/fx`
- Findings: Q39.
- Epic: E01
- Band: 3 · Size: M · Tags: ops
- Depends on: T-Q290
- Docs-first step: [ADR-0145](../../adr/0145-nbp-table-a-daily-fx-refresh-in-app-task.md) amendment 2026-11-22 and new [ADR-0146](../../adr/0146-fx-freshness-health-path.md) (modelled on ADR-0119).
- Acceptance: failing tests first with injected clock and fake source: (a) a failed run is retried the same day, hourly until 18:00 Europe/Warsaw, then not again; (b) a table whose effective date is older than N days (setting, default 7) is rejected and writes no row; (c) `GET /health/fx` returns 200 `ok` when the newest cached rate of each non-base currency in use is at most N business days old (setting), 200 `disabled` when refresh is off or no foreign currency is in use, 503 `stale` / `never` otherwise, fail closed, no DB writes, pure decision function in `services/`, exempt from auth like `/health/replication`; (d) operator step, not agent: UptimeRobot status-code monitor on `https://budget.rising-dough.eu/health/fx`, 5 min, same alert contact (ADR-0119 §6).
- Operator question blocking it: none.
- Removes allowlist entries: none
- Wave: 14e (before T-Q293).
- Done when: ADR indexed; guards green; the Acceptance holds; the CLAUDE.md handoff checklist is complete.

### T-Q307 [S] FX refresh on in prod; `/health/fx` 503 when disabled in prod
- Findings: Q39 (deferred question 45, resolved 2026-11-22: operator chose enable (b) and alert (c)).
- Epic: E01
- Band: 3 · Size: S · Tags: ops
- Depends on: T-Q292
- Docs-first step: [ADR-0146](../../adr/0146-fx-freshness-health-path.md) amendment 2026-11-22 (T-Q307); `docs/requirements.md` F7.4.
- Acceptance: tests first: production + refresh off is 503 `disabled`; non-production + off is 200 `disabled`; production + on + fresh is 200 `ok`; production + on + stale is 503 `stale`; on with no foreign account is 200 `ok`. The compose template sets `BUDGET_FX_REFRESH_ENABLED: "true"`; `terraform fmt/validate/test` pass.
- Operator step (after deploy, not the agent): add the UptimeRobot monitor on `https://budget.rising-dough.eu/health/fx`.
- Removes allowlist entries: none
- Done when: guards green; the Acceptance holds; the CLAUDE.md handoff checklist is complete.

### ✅ T-Q293 [M] `money_scope` `fx-def` check keys on behaviour
- Findings: Q39.
- Epic: E01
- Band: 4 · Size: M · Tags: none
- Depends on: T-Q292
- Docs-first step: [ADR-0130](../../adr/0130-prevention-regime-and-full-architectural-compliance.md) amendment 2026-11-22: the `fx-def` check flags rate arithmetic or conversion outside `services/fx.py` and `domain/fx.py`, not function names.
- Acceptance: failing guard tests first (a conversion under a neutral name is flagged; a non-FX function named like an FX one is not); revert the dodge-renames from T-Q286 (`formula_ctx*`) and T-Q290 (the two renamed fx functions) to honest names; no new allowlist entry.
- Operator question blocking it: none.
- Removes allowlist entries: `money_scope.toml` forecast `money-float` x1, recurring_formula `money-parse` x1, today `money-parse` x2
- Wave: 14e (after T-Q292).
- Done when: guards green; the Acceptance holds; the CLAUDE.md handoff checklist is complete.

### ✅ T-Q296 [S] Burn down the residual allowlist entries no task owns
- Findings: Q-046, B-13, Q-016 (residuals).
- Epic: E13
- Band: 4 · Size: S · Tags: none
- Depends on: T-Q270
- Docs-first step: [ADR-0130](../../adr/0130-prevention-regime-and-full-architectural-compliance.md) amendment 2026-11-22 (T-Q296).
- Acceptance: no behaviour change; `web/routers/recurring.py` leaves `size_complexity` (cc>=11 x3, func>50 x4) and its `assert-in-src` hygiene entry; `startup_migrate` imports a public `resolve_db_path`; `config.py` `hidden-cache` becomes a `[[permanent]]` row with a reason; no new allowlist entry or suppression.
- Operator question blocking it: none.
- Removes allowlist entries: `size_complexity` 2 rows (7), `private_imports` 1, `hygiene` 1 (3); `functional_first` 1 moved to permanent.
- Wave: before T-Q232.
- Done when: guards green; the Acceptance holds; the CLAUDE.md handoff checklist is complete.

### ✅ T-Q294 [S] Enum-like query parameters are a 422 on unknown values
- Findings: Q-023, Q-033 (extends T-Q282).
- Epic: E03
- Band: 4 · Size: S · Tags: none
- Depends on: T-Q282
- Docs-first step: [ADR-0141](../../adr/0141-one-amount-parser-and-bounded-request-parameters.md) amendment 2026-11-22.
- Acceptance: failing tests first in `tests/integration/web/test_bad_query_params.py`: `/plan?tab=`, `/ledger?view=`, `/today?window=`, analytics `period`, `/add?when=` and any other choice parameter return 422 on an unknown value, `errors.heading` "Check the form", the parameter name in `errors.main`; an HTMX request gets the error flash; missing or empty still defaults; valid values stay 200. One owner in `web/params.py`.
- Operator question blocking it: none.
- Removes allowlist entries: none
- Wave: 14e (parallel with T-Q292).
- Done when: guards green; the Acceptance holds; the CLAUDE.md handoff checklist is complete.

## Allowlist ownership and reconciliation

Source: `uv run python docs/plans/quality-audit/repro/allowlist_by_qid.py` at the T-Q17 commit (burn-down total 1255 violations in 613 entries; 35 permanent and 41 framework violations are not burn-down). Ceilings come from `[ceilings]` in `suppressions.toml` (87 suppressions) and are additional to the 1255.

Per guard: allowlist total versus the sum owned by tasks (entries / violations). All rows reconcile.

| Guard | Allowlist | Sum of tasks | Owning tasks (violations) |
|---|---|---|---|
| `adr_index` | 1 / 1 | 1 / 1 | T-Q245 1 |
| `banned_patterns` | 23 / 58 | 23 / 58 | T-Q208 4, T-Q212 13, T-Q213 3, T-Q216 1, T-Q229 29, T-Q233 2, T-Q236 6 |
| `clones` | 33 / 99 | 33 / 99 | T-Q260 75, T-Q262 24 |
| `coverage_config` | 1 / 1 | 1 / 1 | T-Q219 1 |
| `functional_first` | 20 / 24 | 20 / 24 | T-Q229 1, T-Q263 21, T-Q264 2 |
| `guidance_paths` | 2 / 11 | 2 / 11 | T-Q245 11 |
| `htmx_events` | 7 / 35 | 7 / 35 | T-Q236 35 |
| `hygiene` | 61 / 145 | 61 / 145 | T-Q271 145 |
| `invariants` | 12 / 14 | 12 / 14 | T-Q206 1, T-Q208 2, T-Q212 1, T-Q213 2, T-Q214 1, T-Q216 3, T-Q227 2, T-Q229 1, T-Q233 1 |
| `layering` | 22 / 45 | 22 / 45 | T-Q241 36, T-Q243 4, T-Q258 5 |
| `literal_user_id` | 2 / 3 | 2 / 3 | T-Q201 2, T-Q207 1 |
| `literals` | 29 / 124 | 29 / 124 | T-Q261 124 |
| `money_scope` | 44 / 78 | 44 / 78 | T-Q212 18, T-Q216 16, T-Q229 27, T-Q233 17 |
| `purity` | 29 / 37 | 29 / 37 | T-Q212 17, T-Q229 6, T-Q264 14 |
| `read_filters` | 11 / 23 | 11 / 23 | T-Q268 23 |
| `size_complexity` | 41 / 73 | 41 / 73 | T-Q242 18, T-Q269 29, T-Q270 26 |
| `sql_sites` | 6 / 10 | 6 / 10 | T-Q228 6, T-Q258 4 |
| `suppressions` | 31 / 94 | 31 / 94 | T-Q272 94 |
| `template_logic` | 148 / 148 | 148 / 148 | T-Q237 42, T-Q273 106 |
| `thin_router` | 26 / 154 | 26 / 154 | T-Q208 2, T-Q265 53, T-Q266 56, T-Q267 43 |
| `user_isolation` | 54 / 54 | 54 / 54 | T-Q221 54 |
| `workflow_trust` | 10 / 24 | 10 / 24 | T-Q218 23, T-Q238 1 |
| **total** | **613 / 1255** | **613 / 1255** | |

`suppressions.toml` ceilings (not in the table above):

| Ceiling | Total | Owners |
|---|---|---|
| `PLC0415` (function-level imports) | 37 | T-Q243 37 |
| `PLR0917` (positional parameters) | 32 | T-Q243 8 (services), T-Q265 6, T-Q266 10, T-Q267 8 (route handlers) |
| `DTZ011` (`date.today()`) | 18 | T-Q229 18 |

Per finding id (the `finding` field of each entry) to owning task:

| Finding id | Violations | Owning tasks |
|---|---|---|
| B-01 | 88 | T-Q208 2, T-Q265 41, T-Q266 41, T-Q267 4 |
| B-02 | 66 | T-Q265 12, T-Q266 15, T-Q267 39 |
| B-13 | 23 | T-Q263 21, T-Q264 2 |
| B-14 | 23 | T-Q268 23 |
| P1 | 99 | T-Q260 75, T-Q262 24 |
| Q-001 | 2 | T-Q201 2 |
| Q-002 | 2 | T-Q206 1, T-Q207 1 |
| Q-003 | 6 | T-Q208 6 |
| Q-007 | 49 | T-Q212 49 |
| Q-008 | 5 | T-Q213 5 |
| Q-009 | 1 | T-Q214 1 |
| Q-011 | 18 | T-Q216 18 |
| Q-012 | 23 | T-Q218 23 |
| Q-014 | 1 | T-Q219 1 |
| Q-015 | 54 | T-Q221 54 |
| Q-022 | 2 | T-Q229 2 |
| Q-023 | 20 | T-Q233 20 |
| Q-024 | 6 | T-Q228 6 |
| Q-029 | 2 | T-Q216 2 |
| Q-030 | 2 | T-Q227 2 |
| Q-031 | 10 | T-Q229 10 |
| Q-038 | 165 | T-Q236 41, T-Q261 124 |
| Q-039 | 148 | T-Q237 42, T-Q273 106 |
| Q-040 | 1 | T-Q238 1 |
| Q-045 | 36 | T-Q241 36 |
| Q-046 | 73 | T-Q242 18, T-Q269 29, T-Q270 26 |
| Q-047 | 4 | T-Q243 4 |
| Q-048 | 94 | T-Q272 94 |
| Q-051 | 1 | T-Q245 1 |
| Q-053 | 11 | T-Q245 11 |
| Q-073 | 145 | T-Q271 145 |
| Q-074 | 23 | T-Q258 9, T-Q264 14 |
| Q-076 | 52 | T-Q229 52 |

Per epic (the `epic` field), violations to owning tasks:

| Epic | Violations | Owning tasks |
|---|---|---|
| - | 92 | T-Q206 1, T-Q208 2, T-Q212 1, T-Q213 2, T-Q214 1, T-Q216 3, T-Q218 23, T-Q221 54, T-Q227 2, T-Q229 1, T-Q233 1, T-Q238 1 |
| E01 | 39 | T-Q207 1, T-Q208 4, T-Q212 31, T-Q213 3 |
| E02 | 75 | T-Q260 75 |
| E03 | 191 | T-Q233 2, T-Q236 41, T-Q261 124, T-Q262 24 |
| E05 | 21 | T-Q263 21 |
| E06 | 17 | T-Q212 17 |
| E07 | 25 | T-Q229 9, T-Q264 16 |
| E08 | 102 | T-Q241 36, T-Q265 12, T-Q266 15, T-Q267 39 |
| E09 | 90 | T-Q201 2, T-Q208 2, T-Q265 41, T-Q266 41, T-Q267 4 |
| E10 | 33 | T-Q228 6, T-Q258 4, T-Q268 23 |
| E11 | 88 | T-Q216 17, T-Q229 54, T-Q233 17 |
| E12 | 9 | T-Q243 4, T-Q258 5 |
| E13 | 73 | T-Q242 18, T-Q269 29, T-Q270 26 |
| E14 | 107 | T-Q219 1, T-Q245 12, T-Q272 94 |
| E15 | 145 | T-Q271 145 |
| E16 | 148 | T-Q237 42, T-Q273 106 |

## Coverage matrices

Epic to tasks (all of E01 to E16 covered; E16 has no remediation of the old tree except through T-Q237 and T-Q273 as long as the old templates exist, see decision D3).

| Epic | Scope (compliance-inventory section 16) | Tasks |
|---|---|---|
| E01 | DRY / services canonical modules | T-Q206, T-Q207, T-Q208, T-Q212, T-Q213, T-Q214, T-Q215, T-Q227 |
| E02 | DRY / repositories | T-Q260 |
| E03 | DRY / web (params, htmx, literals, clones) | T-Q233, T-Q236, T-Q256, T-Q261, T-Q262 |
| E04 | Functional / middleware and framework classes | T-Q274 |
| E05 | Functional / data constants and globals | T-Q258, T-Q263 |
| E06 | Purity / FX network I/O | T-Q212 |
| E07 | Purity / clock, entropy, settings | T-Q229, T-Q264 |
| E08 | Thin web / CRUD services | T-Q202, T-Q210, T-Q241, T-Q265, T-Q266, T-Q267 |
| E09 | Thin web / view models | T-Q201, T-Q208, T-Q209, T-Q215, T-Q237, T-Q265, T-Q266, T-Q267 |
| E10 | Repository discipline | T-Q204, T-Q228, T-Q258, T-Q268 |
| E11 | Money | T-Q216, T-Q229, T-Q233 |
| E12 | Layering and imports | T-Q243, T-Q258 |
| E13 | Size and signatures | T-Q242, T-Q243, T-Q265, T-Q266, T-Q267, T-Q269, T-Q270 |
| E14 | Suppressions and config drift | T-Q219, T-Q245, T-Q272 |
| E15 | Hygiene | T-Q271, T-Q275 |
| E16 | Templates | T-Q237, T-Q256, T-Q273 |

Q-id to tasks (all 80 covered).

| Q-id | Tasks | Q-id | Tasks | Q-id | Tasks | Q-id | Tasks |
|---|---|---|---|---|---|---|---|
| Q-001 | 201, 232 | Q-021 | 252 | Q-041 | 239 | Q-061 | 251 |
| Q-002 | 206, 207 | Q-022 | 252 | Q-042 | 238 | Q-062 | 253 |
| Q-003 | 208 | Q-023 | 233 | Q-043 | 240 | Q-063 | 204 |
| Q-004 | 210 | Q-024 | 228 | Q-044 | 240 | Q-064 | 254 |
| Q-005 | 217 | Q-025 | 204 | Q-045 | 241, 265, 266, 267 | Q-065 | 254 |
| Q-006 | 211 | Q-026 | 230 | Q-046 | 242, 269, 270 | Q-066 | 254 |
| Q-007 | 212 | Q-027 | 203 | Q-047 | 243 | Q-067 | 255 |
| Q-008 | 213 | Q-028 | 202 | Q-048 | 243, 265, 266, 267, 272 | Q-068 | 255 |
| Q-009 | 214 | Q-029 | 216 | Q-049 | 228 | Q-069 | 255 |
| Q-010 | 209, 215 | Q-030 | 227 | Q-050 | 244 | Q-070 | 256, 273 |
| Q-011 | 216, 273 | Q-031 | 229 | Q-051 | 245 | Q-071 | 256 |
| Q-012 | 218 | Q-032 | 227 | Q-052 | 245 | Q-072 | 257 |
| Q-013 | 220 | Q-033 | 234 | Q-053 | 245 | Q-073 | 257, 271 |
| Q-014 | 219 | Q-034 | 205 | Q-054 | 246 | Q-074 | 258, 263, 264 |
| Q-015 | 221 | Q-035 | 235 | Q-055 | 247 | Q-075 | 227 |
| Q-016 | 222 | Q-036 | 227 | Q-056 | 248 | Q-076 | 229 |
| Q-017 | 223 | Q-037 | 236 | Q-057 | 248 | Q-077 | 259 |
| Q-018 | 224 | Q-038 | 236, 261 | Q-058 | 249 | Q-078 | 255 |
| Q-019 | 225 | Q-039 | 237, 273 | Q-059 | 250 | Q-079 | 255 |
| Q-020 | 226 | Q-040 | 238 | Q-060 | 231 | Q-080 | 232, 255 |

(Task ids in the Q-id table omit the `T-Q` prefix.)

## Wave plan (orchestrator mode)

Use `orchestrator-mode` (ADR-0066): one worktree and branch per task, merge the main work branch into the item branch, never rebase. Constraints applied: (1) every task's dependencies are in an earlier wave; (2) **no two tasks in a wave own entries in the same allowlist TOML** (the hotspots), with two stated exceptions: `invariants.toml` (each task deletes only its own tiny block; adjacent-hunk conflicts are resolved by union and the guard re-run) and the path-disjoint groups of Wave 12 (`thin_router.toml` and the `PLR0917` ceiling, three router groups) and Wave 15 (`size_complexity.toml`, services/repositories versus routers); (3) disjoint primary source areas per wave; (4) at most about 4 heavy items at once (CPU budget, `PYTEST_WORKERS=2`); cheap tests-only, docs and ops items are fillers. Waves are sequential; items inside a wave are parallel. Merge order inside a wave: smallest first. Between waves the orchestrator runs the pre-commit gate on the merged branch and re-runs `allowlist_by_qid.py`.

| Wave | Tasks | Allowlist TOMLs (owner) | Primary source areas | Note |
|---|---|---|---|---|
| 1 | T-Q201, T-Q206, T-Q218, T-Q221 | `invariants` (206); `literal_user_id` (201); `user_isolation` (221); `workflow_trust` (218) | budget router; forecast overlay helper; GitHub/terraform ops; `tests/unit/services` fixtures | Operator-gated ops item (T-Q218) runs in parallel with code. |
| 2 | T-Q202, T-Q203, T-Q205, T-Q209, T-Q239 | none | recurring router + validator; auth router, Dockerfile, compose; migrations; ledger router/totals; CODEOWNERS | T-Q239 is operator-gated (GitHub settings). |
| 3 | T-Q204, T-Q208, T-Q219, T-Q220, T-Q238, T-Q245 | `adr_index` (245); `banned_patterns` (208); `coverage_config` (219); `guidance_paths` (245); `invariants` (208); `thin_router` (208); `workflow_trust` (238) | `repositories/_shared`, planned/recurring/reconciliation/users services; `domain/periods.py`, budget/forecast/analytics/plan; `pyproject`; `terraform/modules/compute`; docs/CLAUDE.md | T-Q219/T-Q220/T-Q238/T-Q245 are config, tests-only, terraform and docs; cheap. |
| 4 | T-Q210, T-Q211, T-Q216, T-Q231, T-Q240 | `banned_patterns` (216); `invariants` (216); `money_scope` (216) | transactions/planned/accounts routers; `services/recurring.py` schedule; `domain/money.py` + templates; `tests/conftest.py`; deps | T-Q216 is the large template sweep: no other item in the wave touches templates. |
| 5 | T-Q212, T-Q217, T-Q222, T-Q225, T-Q246, T-Q275 | `banned_patterns` (212); `invariants` (212); `money_scope` (212); `purity` (212) | `services/fx.py`, forecast, budget, analytics, `today_data`; reconciliation; mutant-kill tests; docs | T-Q212 is the FX hub: nothing else touches `services/fx.py`, `forecast.py` or `today_data.py` this wave. |
| 6 | T-Q213, T-Q214, T-Q215, T-Q243, T-Q226, T-Q248, T-Q249, T-Q252 | `banned_patterns` (213); `invariants` (213/214); `layering` (243); `suppressions` (243) | analytics/forecast spent; fortune; ledger templates; `services/recurring*` + router imports; tests | Tests-only items (T-Q226, T-Q248, T-Q249, T-Q252) are cheap fillers. |
| 7 | T-Q207, T-Q228, T-Q224, T-Q250, T-Q253, T-Q255 | `literal_user_id` (207); `sql_sites` (228) | occurrence expander across services; planned/recurring router SQL; session/passkey; CI settings | T-Q207 owns `services/recurring.py`, `forecast.py`, `budget.py`; T-Q228 owns the planned and recurring routers. |
| 8 | T-Q227, T-Q233, T-Q223, T-Q268, T-Q251, T-Q254, T-Q259 | `banned_patterns` (233); `invariants` (227/233); `money_scope` (233); `read_filters` (268) | categories/balance/aggregates; `web/params.py` + parsers; repository read filters; middleware; visual workflow | T-Q233 and T-Q254 both touch routers or middleware lightly; keep T-Q233 first in merge order. |
| 9 | T-Q229, T-Q237, T-Q234, T-Q230, T-Q247 | `banned_patterns` (229); `functional_first` (229); `invariants` (229); `money_scope` (229); `purity` (229); `suppressions` (229); `template_logic` (237) | clock, rounding, DTZ across services and routers; `MonthSummary` + budget templates; balance series | T-Q229 is the widest sweep (clock, rounding); T-Q237 stays in `templates/{today,plan,budget}`. |
| 10 | T-Q241, T-Q260, T-Q263 | `clones` (260); `functional_first` (263); `layering` (241) | CRUD services + router imports; `repositories/*` CRUD helpers; module constants | T-Q241 owns routers and new services; T-Q260 owns `repositories/`. |
| 11 | T-Q236, T-Q258, T-Q264, T-Q244, T-Q276 | `banned_patterns` (236); `functional_first` (264); `htmx_events` (236); `layering` (258); `purity` (264); `sql_sites` (258) | `web/htmx.py`, events; layering facade; `config.py`/entropy; dead routes; account soft-delete predicate in balance, aggregates and converters (T-Q276, no allowlist TOML) | T-Q236 owns `web/htmx.py`, `app-init.js` and event emitters; T-Q244 deletes dead routes first. |
| 12 | T-Q265, T-Q266, T-Q267 | `suppressions` (265/266/267); `thin_router` (265/266/267) | router groups: transactions/planned/ledger/today; accounts/budget/categories/recurring; auth/settings* | Three router groups with disjoint router files (thin_router.toml and the `PLR0917` ceiling are path-disjoint; resolve any adjacent-hunk conflict by union). |
| 13 | T-Q242, T-Q261, T-Q256, T-Q257, T-Q235 | `literals` (261); `size_complexity` (242) | recurring router and forecast split; literal registry; accounts template/passkeys.js; app.py router imports; bounds | T-Q242 owns `recurring.py` router and `forecast.py`; T-Q261 owns literal replacement elsewhere. |
| 14 | T-Q262, T-Q273, T-Q274 | `clones` (262); `template_logic` (273) | same-name helpers in services/web; remaining templates; ASGI middleware | After the router rewrites; T-Q262 owns remaining same-name helpers, T-Q273 templates, T-Q274 middleware. |
| 14b | T-Q279, T-Q280, T-Q283, T-Q284, T-Q286, T-Q290, T-Q291 | `money_scope` (283) | budget, forecast overlay, categories and planned totals (279, 280); `tests/architecture` guard (284); recurring formula views (286); new FX job module, cli, terraform (290); `domain/ports`, `adapters`, `services/_passwords`, users (291) | Operator decisions 2026-11-22. T-Q280 merges after T-Q279 (same files). Disjoint source areas, so all run in parallel (about 4 heavy at once; T-Q283 and T-Q284 are cheap fillers). Only T-Q283 owns an allowlist TOML. |
| 14c | T-Q281, T-Q282, T-Q287, T-Q288 | none | `domain/money.py` and rounding call sites across services (281); `web/params.py` and routers (282); `repositories/_shared`, `users.owns_accounts`, `webauthn` (287); recurring and planned undo in services (288) | After 14b. Parallel: disjoint areas. T-Q281 owns the one router rounding site (`web/routers/today.py`); T-Q282 merges after it. |
| 14d | T-Q285, T-Q289 | none | services CRUD entry points and routers (285, large; needs T-Q267 and T-Q262); ASGI CSRF middleware (289; needs T-Q274) | After 14c so T-Q285 builds on T-Q287 and T-Q288. Parallel: disjoint (services/routers versus middleware). All of 14b to 14d finish before Wave 15 (size decomposition) and T-Q232. |
| 14e | T-Q292, T-Q293, T-Q294 | none | NBP job, health router, settings (292); `tests/architecture` money_scope guard and renamed fx functions (293); `web/params.py` and routers (294) | Third round, 2026-11-22. T-Q292 then T-Q293 sequential; T-Q294 parallel. |
| 15 | T-Q269, T-Q270 | `size_complexity` (269/270) | service/repository/db decomposition; router/web decomposition | Path-disjoint size_complexity owners (services/repos/db vs routers/web). |
| 16 | T-Q271 | `hygiene` (271) | every `src/` module: `Any`, asserts, excepts, prints | Repo-wide sweep; nothing else runs. |
| 17 | T-Q272 | `suppressions` (272) | every `src/` suppression | Repo-wide sweep; nothing else runs. |
| 18 | T-Q232 | none | allowlists, guards, CI | Verification only; deletes `allowlists/*.toml` entry tables, flips guards strict. |

**Suggested first wave:** Wave 1 = T-Q201 (budget router, one-line fix, High now and Critical the day a second user exists), T-Q206 (forecast double-count hotfix, live on PLN data), T-Q218 (operator-gated: GitHub environments and branch policy; start the operator settings work immediately), T-Q221 (two-user and tombstone fixtures that every later task reuses). Wave 2 then covers the remaining before-second-user items (T-Q202, T-Q203, T-Q205) plus T-Q209 and T-Q239.

**Critical path.** T-Q216 and T-Q212 (FX hub, Wave 4 to 5) gate everything FX; T-Q243 then T-Q228 then T-Q241 (layering, repositories, services, Waves 6 to 10) gate the router thinning (Wave 12); the repo-wide sweeps T-Q271 and T-Q272 run last (Waves 16 and 17) because they touch every module; T-Q232 closes (Wave 18). Eighteen waves. Waves 1 to 9 deliver Bands 0, 1 and 3 and every `[pre-v4-P3]` task (the last of them, T-Q207, is in Wave 7); the rest of Band 2 (layering, thin routers, HTMX contract, purity) finishes in Waves 10 to 12.

**Hotspot rules for the orchestrator.** (a) The allowlist TOML owner table above is the contract; a task needing another wave's TOML waits. (b) `tests/architecture/allowlists/*.toml`, `pyproject.toml`, `uv.lock`, `docs/CHANGELOG.md` (append-only: resolve by keeping both lines), `docs/adr/README.md` (new ADR numbers: reserve numbers per wave before dispatch to avoid duplicates) are merged by the orchestrator, not by items, whenever a conflict appears. (c) CLAUDE.md and `.claude/**` edits (T-Q245) are operator-reviewed and merged alone. (d) Terraform and GitHub-settings tasks (T-Q218, T-Q238, T-Q239, T-Q255) never apply from a laptop; their code half lands through the PR pipeline, the settings half is the operator's.
