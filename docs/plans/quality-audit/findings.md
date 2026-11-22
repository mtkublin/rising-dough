# Code-Quality Audit — Findings Register

> Deliverable 1 (consolidated, T-Q11). **Frozen — operator review T-Q12 done 2026-11-20 (all accepted).**
> Schema, severity rubric and root-cause classes: [implementation_plan.md §4–§5](implementation_plan.md#4--finding-schema).
> All `path:line` references are valid at `AUDIT_SHA` (9fb18cb) only. `audit/quality` later absorbed main's T-D158 CI and Terraform changes, so findings in `.github/workflows/terraform.yml`, `scripts/ci/host_release.py`, `terraform/main.tf` (H1 and D findings) need a re-check at remediation time.

## Audit metadata

| Field | Value |
|---|---|
| `AUDIT_SHA` | `9fb18cbca26ef305855efc8fc106d896edc82631` (tip of `main` = tip of `audit/quality`) |
| Date | 2026-11-19 |
| Python / tool versions | Python 3.12.13; ruff 0.17.2; mypy 2.4.0; pytest 9.1.1; sqlfluff 4.4.0; djlint 1.47.0; bandit 1.9.4; detect-secrets 1.5.0 |
| LOC per package | Lines (files) under `src/budget_planner`: `domain` 1,283 (16); `services` 7,263 (32); `repositories` 3,563 (18); `web/routers` 6,114 (20); `web/templates` 6,022 (111); `web/static` 8,488 (44); `db` 752 (6); `adapters` 0 (3, empty); `cli` 155 (2). Package total (.py) 22,254 (120). `tests/` (.py) 39,158 (232). |
| `just ci` at SHA | Green: ruff, mypy (352 files) clean; 2637 passed, 17 skipped in 423.00s (pytest), 8:52.96 wall for the whole `just ci` (`PYTEST_WORKERS=2`); coverage 94.70% (gate 90%). Raw output: `baseline/ci.txt`, per-module table: `baseline/coverage.txt` |
| Scratch DB | `/tmp/audit.sqlite` (copied from `data/demo.sqlite`; migrations not needed) |
| Status | Frozen — operator review T-Q12 done 2026-11-20 (all accepted). Phase 3 complete. V1, V2, V3 verification and Track H4 (infra red team on drill 44609305750) folded in |

## Operator review (T-Q12)

Date: 2026-11-20. Status: **frozen**.

**Decision.** All findings are accepted as consolidated: 80 Q-ids (0 Critical, 20 High, 41 Medium, 19 Low), with the severities in this register. None adjusted, none dismissed beyond the one track finding already recorded as out of scope.

**Directive (full compliance).** The operator added: "the plan must also cover converging our architecture to FULL compliance with our assumed architectural principles (DRY, functional paradigm, no side effects etc.). We want no violations in our codebase — not only instances that caused bugs, all of them. Our development rules need to be tightened to prevent drifting in the future."

**Consequences.**
- The register lists the violations that caused or could cause defects. The directive widens the target to *every* violation of a stated principle. The complete inventory is `compliance-inventory.md` (same folder); it is the starting content of each guard's allowlist.
- Each guard's allowlist must reach zero. No new allowlist entries without an ADR amendment ([ADR-0130](../../adr/0130-prevention-regime-and-full-architectural-compliance.md)).
- Development rules are tightened by ADR-0130 (search-before-write, canonical-module reuse, handoff and merge-step checks).
- Other operator decisions of the day (CI runs pre-commit for parity, CI-side only with no local slowdown, mutation job, `clock.py`, settings check) are recorded in [prevention.md §5](prevention.md#5-operator-decisions-needed-before-or-during-t-q15) and ADR-0130/0131.

## Summary

**80 consolidated findings (Q-001 to Q-080) from 155 track findings** (154 merged into Q-ids, 1 dismissed as out of scope). Critical 0, High 20, Medium 41, Low 19. Verification: V1 (tracks A-C), V2 (D, E, G, H1, H3), V3 (F, H2) re-checked every Critical/High and at least 20 percent of Mediums; **0 findings rejected**, the 4 track-rated Criticals (A-01, B-01, C-01, G-01) were reclassified High because they are latent on current data. Track H4 (infrastructure, white-box red team on a live explore drill, Step 0 confirmed no prod data) added 6 findings: 3 merged into existing Q-ids (H4-01 into Q-027, H4-03 into Q-012, H4-04 into Q-068) and 3 new Low Q-ids (Q-078 to Q-080). It also resolved the open Caddy question (Caddy overwrites a forged `X-Forwarded-For`, so Q-027 keeps Medium for a different reason: the real client IP is lost for everyone) and verified D-11 (Q-067) and D-12 (Q-066).

**Nothing is Critical today.** Calibration used the operator facts of 2026-11-19: prod has only PLN accounts (no FX, no JPY/KRW/ISK), one active user (more soon), no reconciliation ever used an income/expense category, probably no recurring rule with a blank day-of-month starting after the 28th. Latent wrong-money is therefore High, and the two scoping defects (D-01/H2-01) are High but become Critical the day a second user exists. Items marked **Biting on current PLN data** are the ones that can produce a wrong number or a 500 today without any of those preconditions.

### Counts by severity and track (consolidated Q-ids by the track of their lead alias)

| Severity | A | B | C | D | E | F | G | H1 | H2 | H3 | H4 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Critical | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| High | 5 | 2 | 2 | 1 | 0 | 8 | 1 | 1 | 0 | 0 | 0 | 20 |
| Medium | 6 | 6 | 6 | 1 | 2 | 9 | 7 | 3 | 1 | 0 | 0 | 41 |
| Low | 1 | 1 | 2 | 5 | 2 | 1 | 1 | 1 | 1 | 1 | 3 | 19 |
| **Total** | 12 | 9 | 10 | 7 | 4 | 18 | 9 | 5 | 2 | 1 | 3 | 80 |

Original track counts before consolidation (track-assigned severity, `Critical (cond.)` counted as Critical):

| Severity | A | B | C | D | E | F | G | H1 | H2 | H3 | H4 | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Critical | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 4 |
| High | 7 | 2 | 6 | 1 | 3 | 13 | 0 | 2 | 1 | 0 | 0 | 35 |
| Medium | 9 | 7 | 10 | 2 | 3 | 10 | 10 | 4 | 2 | 1 | 2 | 60 |
| Low | 5 | 6 | 3 | 10 | 5 | 4 | 6 | 4 | 2 | 7 | 4 | 56 |
| **Total** | 22 | 16 | 20 | 13 | 11 | 27 | 17 | 10 | 5 | 8 | 6 | 155 |

Tracks A-G are the plan tracks (duplication, layering, correctness, security, frontend, tests, drift); H1 CI/supply chain, H2 isolation, H3 auth, H4 infrastructure exposure (live drill). In the first table H4 counts only the Q-ids whose lead alias is an H4 finding (Q-078 to Q-080); H4-01, H4-03 and H4-04 sit under D/H3, H1 and D respectively.

### Dedupe statistics

155 track findings: 154 mapped into 80 Q-ids (average 1.9 per Q-id), 1 dismissed. 42 Q-ids merge two or more track findings; the largest merges are Q-027 (6, now with H4-01), Q-007 (5), Q-023 (5), Q-010 (4); H4-03 grew Q-012 to 3 aliases and H4-04 grew Q-068 to 4. Merge rule: one Q-id per concept and root cause. Deliberate non-merges: the currency exponent is split into the renderer (Q-011, High) and the exponent table (Q-029, Medium) because the location, fix and severity differ; mixed-currency native sums are split into services (Q-008), the ledger strips (Q-010) and net worth (Q-009), which share one converter (Q-007) but not a location.

### Top 10 by risk

Ordered by: bites on current PLN data first, then scoping gaps that precede onboarding a second user, then the latent FX switch, then the ungated CI environments, then the missing safety net.

| # | ID | Severity | Why it is on the list |
|---|---|---|---|
| 1 | Q-001 | High | Cross-user write and oracle; must be fixed before a second user (Critical then). One-line fix. |
| 2 | Q-002 | High | Counts a re-dated recurring bill twice in forecast/overlay today on PLN data. |
| 3 | Q-003 | High | Left-per-day and committed window wrong when no income anchor exists (PLN data); Plan page untested. |
| 4 | Q-010 | High | Planned strip sums income and expense together today; recurring strip wrong with a 2nd currency. |
| 5 | Q-004 | High | One form submit makes /accounts, /today and /forecast return 500 until the row is deleted. |
| 6 | Q-006 | High | Recurring bills drift to the wrong day (blank day-of-month) or appear before their start date. |
| 7 | Q-005 | High | UI-reachable path that leaves the account twice the delta off; latent only because it was never used. |
| 8 | Q-007 | High | The one switch behind six latent findings: first non-PLN account turns rate-1/500 behaviour live; live fetch is broken. |
| 9 | Q-012 | High | A branch workflow (or an agent with push rights) can decrypt all user data without any approval. |
| 10 | Q-013 | High | No test guards any of the cross-implementation agreements; the duplicate-logic fixes can silently regress. |

### Root-cause histogram (primary class per Q-id)

| Class | Q-ids | Of which Critical/High | Secondary mentions |
|---|---|---|---|
| `duplicate-logic` | 12 | 6 | 0 |
| `weak-assertion` | 11 | 5 | 1 |
| `ci-trust-boundary` | 5 | 1 | 0 |
| `security-control` | 6 | 0 | 0 |
| `scoping-gap` | 4 | 1 | 0 |
| `layer-leak` | 4 | 1 | 0 |
| `money-arith` | 4 | 2 | 0 |
| `missing-invariant-test` | 4 | 2 | 0 |
| `config-drift` | 4 | 1 | 0 |
| `htmx-contract` | 4 | 0 | 0 |
| `doc-drift` | 4 | 0 | 0 |
| `repo-bypass` | 2 | 0 | 0 |
| `template-logic` | 2 | 0 | 0 |
| `dependency` | 2 | 0 | 0 |
| `dead-code` | 2 | 0 | 0 |
| `date-boundary` | 1 | 1 | 0 |
| `txn-boundary` | 1 | 0 | 0 |
| `clock` | 1 | 0 | 0 |
| `oversized-module` | 1 | 0 | 0 |
| `import-cycle` | 1 | 0 | 0 |
| `wide-signature` | 1 | 0 | 0 |
| `infra-exposure` | 3 | 0 | 0 |
| `silent-fallback` | 1 | 0 | 1 |

New classes introduced in Phase 3 (plan section 5.2 allows this): `txn-boundary` (compound mutation or its guard read outside one transaction, Q-025) and `date-boundary` (date and schedule arithmetic at month ends and rule starts, Q-006). Used with their section 5.2 meaning otherwise; `clock` has 1 Q-id but 27 call sites.

### Pre-v4-Phase-3 list (plan section 9)

v4 Phase 3 sweeps every repository for field encryption and ports aggregates to Python (ADR-0081). Critical/High remediation of `duplicate-logic`, `repo-bypass` and `scoping-gap` must be done first:

- Q-001 (High, `scoping-gap`): Income-anchor endpoint is hard-wired to user 1: any user can set or clear the owner's anchor and probe the owner's categories, and no other user can set their own
- Q-002 (High, `duplicate-logic`): Forecast budget-overlay helper counts a recurring occurrence twice when a linked planned row exists; occurrence expansion is hand-rolled in seven places
- Q-003 (High, `duplicate-logic`): Budget period window: the no-anchor fallback drops the last day and shortens the per-day divisor; month/period helpers are copied 4-6 times and the plan router re-implements the period for other months
- Q-007 (High, `duplicate-logic`): FX: live rate fetch can never succeed in production, four converter copies apply five different missing-rate policies, and page renders do network I/O
- Q-008 (High, `duplicate-logic`): Analytics and forecast 'spent' add native minor units across currencies against base-currency budgets
- Q-009 (High, `duplicate-logic`): Net worth is computed twice; the figure labelled 'all accounts' silently drops non-base accounts while forecast starts from the converted figure
- Q-010 (High, `duplicate-logic`): Recurring and Planned strips on the ledger sum raw amounts across currencies and, for planned, across income and expense, under a hard-coded 'PLN'

Not High by calibration but in the same classes and recommended before Phase 3 because they sit in the repository layer or touch the same aggregates: Q-024 (Batch undo endpoints bypass the repository layer, replay 'the latest a), Q-049 (Audit-free repository helpers are public API and `user_preferences` wr), Q-045 (No service layer for CRUD), Q-030 (Forecast and budget disagree on which categories and overdue items cou), Q-036 (Direction-to-sign logic exists in six hand-written copies (and default). Raw SQL in routers on `audit_log` and `planned_transactions` (Q-024) would be missed by a repository sweep.

### Before a second user is onboarded

- Q-001 (High): Income-anchor endpoint is hard-wired to user 1: any user can set or clear the owner's anchor and probe the owner's categories, and no other user can set their own
- Q-015 (High): Fixtures never contain a second user or a deleted/inactive row, so 40 money-path mutants (`user_id` or `conn` as `None`, `include_deleted`, `active_only`) survive
- Q-025 (Medium): Compound mutations and their guard reads are not inside one transaction: double-submit can promote twice, concurrent writers fail with 'database is locked'
- Q-027 (Medium): Authentication abuse controls: the real client IP is lost behind Docker NAT (every client is the gateway 172.18.0.1) so the per-IP login bucket is shared and `audit_log.ip` is useless, `--forwarded-allow-ips=*` trusts the header by name, throttled and failed logins write unbounded attacker text to the DB, and one user can lock out another
- Q-028 (Medium): The recurring-rule save path skips the source-category validation that preview performs: foreign or nonexistent category ids and zero-amount formula rules are persisted
- Q-034 (Medium): No `user_id`-leading indexes on the large multi-user tables; a session write on every request
- Q-063 (Low): Admin edge cases: an absent `is_admin` field demotes the target; concurrent admin changes surface 'database is locked' as 500
- Accepted v3 risk to keep in mind: an admin password reset equals account takeover until v4 envelope encryption (D section 6, ADR-0078 section 8, ADR-0079 A1).
- Open question: can the shared `fx_rates` cache be poisoned by one user's currency choice (H2 Q3)? See Open operator questions.

### Open operator questions

Deduplicated from the Questions sections of all tracks and verification files. **Sev** marks questions whose answer changes a severity.

| # | Question | Sev | Affects |
|---|---|---|---|
| OQ-1 | Does prod hold any non-PLN or non-base account, a JPY/KRW/ISK account, or fx_rates rows? (A Q-03, C Q-2, E Q1, G Q1). Needs a read-only count on a copy; I did not open prod. Operator facts say PLN only. | Answered by operator data profile 2026-11-19: PLN only (no non-PLN accounts, no fx rows); no data migration for T-Q216. T-Q212 default taken 2026-11-21, pending operator confirmation: prod PLN-only, no data migration. | Q-007, Q-008, Q-009, Q-010, Q-011, Q-029: High (latent) to Critical if yes |
| OQ-2 | Is more than one active user planned or present, and when? (D, H2 Q1) | Sev | Q-001 High to Critical on the second user |
| OQ-3 | Does the prod image contain `/usr/share/zoneinfo/Europe/Warsaw` (so `TZ` works)? (A Q-04, C Q-1) | Sev | Q-031 Medium to Low if yes; live if no |
| OQ-4 | Has any reconciliation used an income/expense category? (answered: no) |  | Q-005 stays High latent |
| OQ-5 | Is there a recurring rule with blank day-of-month and a start after the 28th, or with a day-of-month earlier than its start day? (C Q-2) | Sev | Q-006 (default taken 2026-11-21, pending operator data check; T-Q211 ships no data-fix migration) |
| OQ-6 | Is the forecast ignoring overdue items intentional (ADR-0105 covers only the budget)? (A Q-01) | **Default taken 2026-11-21, pending operator confirmation:** forecast counts overdue items, placed on `today + 1`; budget keeps ADR-0105 (ADR-0105 amendment 2026-11-21, T-Q207). | Q-030 policy |
| OQ-7 | Are the three 'monthly average' definitions intentional? (A Q-02) | **Default taken 2026-11-21, pending operator confirmation:** the three monthly-average definitions stay unchanged, each named and documented once in `services/aggregates.py` (T-Q227, no number changes). | Q-075 |
| OQ-8 | Can formula inputs mix currencies in practice? (A Q-05) |  | Q-010 |
| OQ-9 | Should a user-defined category with direction transit be allowed at all? (B Q2) | Default taken 2026-11-21, pending operator confirmation: allowed; every write path validates the transit shape (ADR-0008 amendment 2026-11-21, T-Q210) | Q-004, Q-005 scope |
| OQ-10 | Are NULL `ip`/`session_id`/`user_agent` on domain audit rows intended (ADR-0122 records only `user_id`)? (B Q3) |  | Q-049 (default taken 2026-11-21, pending operator confirmation: intended, ADR-0122 records `user_id` + actor only; no schema change; ADR-0019 amendment, T-Q228) |
| OQ-11 | Is undo an audited action or an erase of the trail? (B Q4) |  | Q-024 shape (default taken 2026-11-21, pending operator confirmation: undo is an audited action, never erases the trail; ADR-0019 amendment, T-Q228) |
| OQ-12 | Should the CRUD service extraction wait for the Sourdough redesign (ADR-0107) or go first? (B Q5) |  | Q-045 sequencing |
| OQ-13 | `services/fx.convert` has no production caller: dead code or reserved? (B Q6) | Default taken 2026-11-21, pending operator confirmation: dead code; `convert` replaced by `FxConverter` in `services/fx.py` (ADR-0139, T-Q212); dead copies deleted. | Q-007, Q-072 |
| OQ-14 | `days_until_next_income = max(..., 1)` on payday and 'average per active month' skipping empty months: intended? Is the fiscal-month label acceptable when a paycheck lands after month end? (C Q-3, Q-4) | Answered 2026-11-21 (ADR-0138): keep the floor of 1 as a guard but payday already opens the new period; label by the month holding most of the period's days (tie: later); average per active month keeps skipping empty months. | Q-003 |
| OQ-15 | Which policy for archived categories and inactive rules in each service (include or exclude)? (A, F Q-2). **Answered by the operator (2026-11-21): hide soft-deleted accounts from balances, stats and converters; archived categories still count.** [ADR-0136](../../adr/0136-soft-deleted-accounts-excluded-from-balances-stats-converters.md), task T-Q276. |  | Q-030, Q-015 |
| OQ-16 | Are future-dated actual transactions meant to be allowed? Is a one-day sparkline lag acceptable? (C Q-5, Q-8) | **Default taken 2026-11-21, pending operator confirmation:** future-dated actuals stay allowed and the one-day sparkline lag is accepted; `balance.as_of_today` is the date-bounded rule (T-Q227, no behaviour change). | Q-032 |
| OQ-17 | Should `fx_rates.rate` have a CHECK (> 0), and is the provider response validated enough that one user's currency cannot poison the shared cache? (C Q-6, H2 Q3) | Default taken 2026-11-21, pending operator confirmation: validate in code at the write and fetch boundary (`NewFxRate`, `parse_remote_rate`); no migration or DB CHECK in T-Q212 (ADR-0139). | Q-007 |
| OQ-18 | Is Europe/Warsaw the only supported display zone? (F Q-3) |  | Q-031 |
| OQ-19 | What is `httpx2` in the dev group and who added it? (G Q2) | Answered by T-Q240 (2026-11-21): legitimate, required by Starlette 1.9 `TestClient` (it imports `httpx2`); added in T-004 (8cf1a5c); kept. | Q-043 Medium to Low if legitimate, incident if not |
| OQ-20 | Are `/docs` and `/openapi.json` intended in prod? (G Q3) H4: unauthenticated requests redirect to login, so only authenticated exposure remains (OQ-34). | Default taken 2026-11-21, pending operator confirmation: `/docs` and `/openapi.json` disabled in production (404), enabled in dev (T-Q254, ADR-0036 addendum). | Q-066 |
| OQ-21 | Close `docs/plans/v2/tasks.md` (60 open rows) as superseded by ADR-0107? (G Q4) | Default taken 2026-11-21, pending operator confirmation: closed with a banner (T-Q246), rows kept. | Q-054 |
| OQ-22 | Should CI run `pre-commit run --all-files`, or are bandit and detect-secrets excluded from CI on purpose (ADR-0120)? (G Q5) | Answered (operator 2026-11-20): yes, CI runs `pre-commit run --all-files` with `SKIP=pytest-fast` plus the full suite; parity is CI-side only. Implemented by T-Q240 (ADR-0120 amendment 2026-11-21). | Q-044 |
| OQ-23 | Are ADR-0106 and ADR-0107 Accepted? Can the duplicate ADR numbers 0105 and 0121 stay grandfathered? (G Q6, Q7) |  | Q-051 |
| OQ-24 | H1: are the values in `prod-plan` real prod secrets or placeholders (rotate after remediation)? Do drill gates restore prod data or only `restore-drill`? Who can write the GHCR package, and has a rollback ever run to a `sha-*` tag? Is a second reviewer or bot feasible, or is the self-approved merge accepted risk? Is the live Tailscale ACL identical to the runbook? (H1 Q1-Q9) **Answered by the operator (2026-11-21): rotation accepted as risk (no evidence of exposure), no rotation; the migration runs as two operator scripts, drill age keys become per-drill (ADR-0132 amendment, T-Q277, ADR-0135).** **Sub-answers (operator, 2026-11-21):** rollback to a `sha-*` tag is allowed only if its signature identity is `build.yml` on `refs/heads/main` AND its commit is an ancestor of `main` (host-agent ancestry check; images signed from any other ref are rejected; ADR-0099 amendment, T-Q238); the live Tailscale ACL is checked for drift against the runbook copy by the operator-run `scripts/check_github_settings.py` (token from `TAILSCALE_API_TOKEN`; T-Q238). Other sub-questions unchanged. | Sev | Q-012, Q-040, Q-041 |
| OQ-25 | Does Caddy 2.8 overwrite a client-supplied `X-Forwarded-For` and strip `X-CSP-Nonce`? (H3 Q1, D, H2 Q2). **Answered by H4 (2026-11-19, live drill): yes.** Caddy 2.8.4 overwrote forged `X-Forwarded-For` and `X-Real-IP` (stored `audit_log.ip` and `auth_rate_limit.key` carry the Docker gateway `172.18.0.1`, not the forged addresses) and replaced a forged `X-CSP-Nonce` with its own. Header rotation is therefore not exploitable through Caddy, but H4-01 found the real client IP is lost for everyone, so Q-027 stays Medium (reason changed). | Sev | Q-027 stays Medium |
| OQ-26 | H3: do shipped pages send concurrent HTMX requests during re-auth (H3-04)? Is 300 s challenge replay acceptable? Should passkey removal end its sessions? Do the user's passkeys report counter 0? (H3 Q2-Q5) | Sev | Q-062 (H3-04 to Medium). Default taken 2026-11-21, pending operator confirmation: concurrent HTMX requests during re-auth assumed possible (handled), challenge single-use, passkey removal ends its sessions, counter 0 accepted and non-zero non-increasing rejected (T-Q253) |
| OQ-27 | E: after `budget-stale` does /budget show stale totals until reload? Does the undo reload fire on a failed undo? (E Q2, Q3) | default taken 2026-11-21, pending operator confirmation (ADR-0143): after a `*-stale` event the affected panel re-fetches (no stale totals until reload); the undo reload fires only on a successful undo. | Q-038, Q-037 |
| OQ-28 | F: root cause of the `test_landmarks_present[/today]` flake not found; the 49 newly visible uncovered statements after the coverage fix are untriaged. (F Q-1, Q-5) | investigated 2026-11-21 (T-Q259): flake not reproducible on the current tree. The facts it asserted are server-rendered static HTML, so DOM timing is excluded. Most likely cause (not provable without a trace): the old `live_server` readiness (15 s, 1 s per probe, no process check; fixed by T-Q248: 60 s, fail-fast) under load, or the `page` fixture teardown asserting on the `/today/afford` htmx request still in flight on `/today` (the only route with one). Test deleted (it duplicates `tests/integration/web/test_accessibility.py`), so nothing is left to flake. The 49 newly visible uncovered statements were triaged by T-Q219 in `baseline/coverage-ellipsis-triage.md` (38 remained on the newer tree: 25 tested, 2 dead for T-Q244, 11 owned by T-Q206 and T-Q209; by file: `web/routers/accounts.py` 315, 487-497; `budget.py` 256-267; `categories.py` 176-177; `planned.py` 240-249, 359; `recurring.py` 839-841; `transactions.py` 269-279, 389; `ledger.py` 229-232; `services/budget.py` 627-629; `services/forecast.py` 749-768; `services/analytics.py` 200). | Q-077, Q-014 |
| OQ-29 | Should the test-isolation tripwire (F-20) be treated as High? Consequence would be writes to the prod DB. | Sev | Q-060 Medium to High |
| OQ-30 | H4: which `MASQUERADE` rule rewrites the tailnet source to the bridge gateway `172.18.0.1` (the `ts-postrouting` mark masquerade versus the `LOCAL` hairpin rules on the `edge` bridge)? Needs `conntrack -E` or a capture on a throwaway drill. (H4 Q2) |  | Q-027 fix shape (host-network Caddy versus iptables change) |
| OQ-31 | H4: is the age identity on the explore drill really the prod identity (the install script header says it must be)? Compare the public recipient with the prod recipient in a context allowed to touch prod config. Is the prod replica read key on the drill valid against prod? (H4 Q4, not tested on purpose) | Sev | Q-012: confirms High; if both are synthetic, drops to Medium |
| OQ-32 | H4: what does tag:ci reach on the tailnet? The ACL source file is not in the repo; version and test it, including `tag:ci` to `tag:prod:22`. (H4 Q3, H1 Q9) | pending operator: ACL source not in repo (T-Q255) | Q-012, Q-067 |
| OQ-33 | H4: what does Caddy return when the app is down (502 page, headers, CSP)? Needs a controlled app stop on a throwaway drill. (H4 Q1) |  | Q-064 |
| OQ-34 | H4: are `/docs` and `/openapi.json` served to an authenticated session in production? Unauthenticated callers get a 302 to `/auth/login` (verified live); authenticated exposure needs a login on a drill. (H4 Q5; refines OQ-20) |  | Q-066 |

## Register

Sorted Critical, High, Medium, Low. Location(s) and Mitigation are abbreviated here; the full text is in Details. Final severity shown; the track severities and verifier changes are in each Details entry.

| ID | Severity | Confidence | Track / root cause | Title | Location(s) | Mitigation (best) |
|---|---|---|---|---|---|---|
| Q-001 | High | Confirmed | D/H2 / `scoping-gap` | Income-anchor endpoint is hard-wired to user 1: any user can set or clear the owner's anchor and probe the owner's categories, and no other user can set their own | `web/routers/budget.py:375-399` (literal `1` at lines 387 and 394); callee `services/preferences.py:44-58`; read side `services/budget.py:421` | Add `user_id: int = Depends(current_user_id)` to `set_income_anchor` and pass it to both service calls |
| Q-002 | High | Confirmed | A / `duplicate-logic` | Forecast budget-overlay helper counts a recurring occurrence twice when a linked planned row exists; occurrence expansion is hand-rolled in seven places | `services/forecast.py:345-390` (`_committed_future_for_category`, no `linked_occurrence_keys` filter); the seven loops: `services/budget.py:296-310`, ... | Step 1 (S): make `_committed_future_for_category` delegate to `budget._committed_by_category` (single copy with dedup and FX), deleting the second implementation |
| Q-003 | High | Confirmed | A/B / `duplicate-logic` | Budget period window: the no-anchor fallback drops the last day and shortens the per-day divisor; month/period helpers are copied 4-6 times and the plan router re-implements the period for other months | `services/budget.py:364-385` (`_resolve_anchor`), `:546,551,566` (`end_of_month`, `days_until_next_income`, exclusive `end`), `:388-436`, ... | New `domain/periods.py`: `month_bounds`, `shift_month`, `fiscal_window(anchor_date, today) -> [start, end)` half-open |
| Q-004 | High | Confirmed | B / `layer-leak` | Transit transactions without a destination account can be persisted through create, update, planned and reconcile; every later balance computation raises and /accounts, /today and /forecast return 500 | `web/routers/transactions.py:263-283` (create validates a destination only `if dest_account_id and ...`), `:358-430` (update: no category or destination check), ... | New `services/transactions.py` with `create_checked` / `update_checked` calling one `validate_transit_shape(direction, account, dest)` extracted from `_promotion.validate_promotion`; use it from the transactions, ... |
| Q-005 | High | Confirmed | C/F / `money-arith` | Reconcile with a chosen income or expense category stores an adjustment of the wrong sign; the balance ends 2x\|delta\| away from the figure the user typed | `services/reconciliation.py:99-112` (`stored_amount = abs(delta)`, docstring `:80-87` promises coercion); entry `web/routers/accounts.py:481-492`, ... | In `services/reconciliation.reconcile` raise `CategoryDirectionMismatchError` (422 in the route) unless the category is ADJUSTMENT, or INCOME with `delta > 0`, or EXPENSE with `delta < 0`, ... |
| Q-006 | High | Confirmed | C / `date-boundary` | Recurring schedule anchor: with a blank day-of-month `next_due` drifts permanently after a clamped month, and occurrences can be generated before the rule's start date | `services/recurring.py:272-306` (`advance_next_due` stub with `start_date = from_date`; `anchor_day = rule.day_of_month or start.day` at `:130`), ... | Persist the anchor: default `day_of_month = start_date.day` in the create service (plus a one-off data fix in the remediation task) and make `advance_next_due` take the rule (anchored on `rule.start_date`), not a `from_date` stub |
| Q-007 | High | Confirmed | A/C/F/G / `duplicate-logic` | FX: live rate fetch can never succeed in production, four converter copies apply five different missing-rate policies, and page renders do network I/O | `config.py:70` (`fx_api_url` never read); `services/fx.py:55,96-164`; clients without `base_url` at `web/today_data.py:124`, `web/routers/forecast.py:49`, ... | One `FxConverter` in `services/fx.py`, built per request by `fx.converter_for(conn, settings, today)`: cache-only (`convert_cached`), client factory `httpx.Client(base_url=settings.fx_api_url, ... |
| Q-008 | High | Confirmed | A / `duplicate-logic` | Analytics and forecast 'spent' add native minor units across currencies against base-currency budgets | `services/analytics.py:123-125,166-168,197-205,236-243` (`_spend_by_category`, `_twelve_month_averages`, `_income_vs_expense_monthly`, `_largest_items`), ... | Inject `budget.base_txn_converter` (built from the Q-007 converter) into the four analytics functions and `_spent_so_far`, or better call one shared `aggregates.sum_by_category(txns, to_base)` (see Q-075), ... |
| Q-009 | High | Confirmed | A / `duplicate-logic` | Net worth is computed twice; the figure labelled 'all accounts' silently drops non-base accounts while forecast starts from the converted figure | `services/fortune.py:30-51` (base-currency accounts only), `web/today_data.py:105-143` (`collect_account_rows` converts; `fortune_base` unused by any template), ... | `services/fortune.compute_fortune(..., converter)` returns per-currency and converted totals using the Q-007 converter; render the converted net worth, ... |
| Q-010 | High | Confirmed | A/B/C/E / `duplicate-logic` | Recurring and Planned strips on the ledger sum raw amounts across currencies and, for planned, across income and expense, under a hard-coded 'PLN' | `web/routers/ledger.py:343-376` (`_recurring_summary`), `:409-414` (`planned_total_minor`); `web/templates/ledger/index.html:93-114` (literal `PLN`, `/ 100.0`), ... | Move both strips (and the formula-source sums) into `services/ledger_totals.py:recurring_monthly_totals` / `planned_totals` using the Q-007 converter, signed by direction (`domain` sign helper, Q-036), ... |
| Q-011 | High | Confirmed | A/C/E / `money-arith` | Money rendered with hard-coded `/ 100.0` and two decimals in 40+ templates, charts and services: zero-decimal currencies show 100x off | `web/templates/today/index.html:32,42,52-55,89-93,100`, `today/_afford_preview.html:3,5`, `today/_upcoming.html:43`, `ledger/_table.html:69`, `ledger/index.html:98-114`, ... | Route every amount through `money` / `money_num(currency)` (templates) and one `domain/money.py:minor_to_major(amount, currency)` (charts, services); replace `_MINOR_UNITS_PER_MAJOR`, ... |
| Q-012 | High | Confirmed | H1/H4 / `ci-trust-boundary` | Ungated, all-branch GitHub environments hold prod-grade secrets (prod age identity, prod replica read key, prod app key, Tailscale OAuth) and can mint a tailnet identity that reaches prod sshd | `.github/workflows/terraform.yml:41-56,204-215`, `drill.yml:60-107,207-218`, `restore-drill.yml`, `replace-rehearsal.yml`, `scripts/ci/tf_env.py:60-79`, ... | Split by data sensitivity: new `prod-restore-read` environment (prod restore-reader key plus prod age identity only) with required reviewers and `main`-only branch policy, used only by `restore-drill`, ... |
| Q-013 | High | Confirmed | F / `missing-invariant-test` | None of Track A's 16 differential invariants exists as a test; 8 of the 10 failing ones will regress or stay open unguarded | `tests/integration/invariants/` (absent); seed in `repro/A/harness.py`; table in `tracks/F-tests.md` section for F-14 | Add `tests/integration/invariants/` with one file per Track A script, reusing the multi-currency seed from `repro/A/harness.py` as a conftest fixture (PLN + EUR + JPY, one cached rate, one archived category, ... |
| Q-014 | High | Confirmed | F / `config-drift` | The coverage config excludes every line containing `...`, silently removing about 790 statements and 16 whole functions from the report | `pyproject.toml:194` (`"\\.\\.\\."` in `[tool.coverage.report] exclude_lines`); affected e.g. `services/balance.py:42`, `services/budget.py:603` (`yearly_grid`), ... | Delete the line or replace it with the anchored `"^\\s*\\.\\.\\.$"` in `pyproject.toml` `exclude_lines`; add tests for the 49 newly missed statements (listed in the repro file). |
| Q-015 | High | Confirmed | F / `missing-invariant-test` | Fixtures never contain a second user or a deleted/inactive row, so 40 money-path mutants (`user_id` or `conn` as `None`, `include_deleted`, `active_only`) survive | `services/forecast.py:277`, `services/budget.py:308,451,501,548`, `services/recurring.py:496`, `services/balance.py:102,133` (rows 5, 7, 22, 30, 43, 51, 60, 78, 101, ... | Add a two-user fixture and a `world_with_tombstones` fixture to `tests/unit/services/conftest.py`; one parametrised test per money service function (balance, budget, forecast, analytics, recurring, planned, upcoming, ... |
| Q-016 | High | Confirmed | F / `weak-assertion` | `recurring_formula` (71 surviving mutants): rounding mode, source-rule lookup and validation unasserted | `services/recurring_formula.py` (rows 234-304 of `baseline/mutmut-real-gaps.md`; `_apply_coefficient` at `:135` `ROUND_HALF_UP` replaced by `None` survives, ... | In `tests/unit/services/test_recurring_formula.py`: HALF_UP tie cases (12.5 percent of 100 minor, odd amounts), a two-user same-name fixture, a category with two items and one inactive source rule, ... |
| Q-017 | High | Confirmed | F / `weak-assertion` | `forecast` (102 surviving mutants): the largest survivor cluster; horizon boundaries, skipped items and FX arguments unasserted | `services/forecast.py` rows 64-165 of the real-gaps list (`_committed_future_for_category` 16, `forecast_monthly` 13, `_planned_budget_per_month` 12, `forecast` 11, ... | In `tests/unit/services/test_forecast.py`: horizon-end-day case (item on the last day and one day later), skipped-by-override item followed by a valid one, income/expense/transit legs on one day with the exact day balance, ... |
| Q-018 | High | Confirmed | F / `weak-assertion` | `budget` (53 surviving mutants): fiscal-month anchoring, committed window, mean and FX converters unasserted | `services/budget.py` rows 11-63 (`month_summary` 20, `_committed_by_category` 8 incl. `end + 1 day` and `rule_start > inclusive_end`, `_resolve_period_start`, ... | In `tests/unit/services/test_budget.py` / `test_budget_fx.py`: `_month_range` and fiscal start for the first of the month and the anchor day; committed item on the last day and the day after; empty and one-item `_mean_minor`, ... |
| Q-019 | High | Confirmed | F / `weak-assertion` | `recurring` (50 surviving mutants): `promote_recurring` audit attribution, override ordering, boundary days | `services/recurring.py` rows 184-233 (`promote_recurring` 10 incl. `user_id=None` in `write_audit` at `:488-496`, `generate_occurrences` boundary values at `:124,134`, ... | In `tests/unit/services/test_recurring.py`: read the `audit_log` row after `promote_recurring` (helper `audit_rows` exists in `tests/integration/auth/conftest.py:41`) and assert user, entity, operation, prev/new JSON, ... |
| Q-020 | High | Confirmed | F / `weak-assertion` | `balance` (10 surviving mutants) and the untested `sparkline_points` / `balance_series` / `yearly_grid`: include-deleted choice, account filter and series are unasserted | `services/balance.py:69,81,98,102,129,133,147,156,158` and `:166-217` (`sparkline_points`, `balance_series`); `services/budget.py:603` (`yearly_grid`, ... | In `tests/unit/services/test_balance.py`: two accounts, one transaction each (balances and `AccountStats.account_id`/`base_balance`), ... |
| Q-021 | Medium | Confirmed | F / `missing-invariant-test` | The Plan page (non-current months, Year tab, Forecast tab) and `forecast.monthly_projection` are executed by no coverage-measured test | `web/routers/plan.py:87-94,126-133,145-171,180-193,195-222`; `services/forecast.py:932-975` (`monthly_projection`); `tests/integration/web/test_forecast.py:92`, ... | New `tests/integration/web/test_plan.py`: GET `/plan?tab=forecast` on a seeded world (series length, first/last month label, one end balance), `/plan?month=...` for a past and a future month (committed zero, period bar dates), ... |
| Q-022 | Medium | Confirmed | F / `weak-assertion` | `format_money` renders zero as `-0.00 PLN` without any test failing (and the zero/negative sign decision is unasserted) | `domain/money.py:246-252` (mutant `value <= 0`); `tests/unit/domain/test_money.py` has no zero case | Add `test_format_money_zero` parametrised over PLN and JPY (`"0.00 PLN"`, `"0 JPY"`) and `format_money(-1, "JPY")`. |
| Q-023 | Medium | Confirmed | A/C/D/H3 / `duplicate-logic` | Unvalidated input reaches the 500 handler: seven divergent amount parsers, unguarded year/month/id parameters, oversized magnitudes and pre-auth parser failures | `domain/money.py:198-231` (canonical `parse_amount_str`, used only by `web/routers/transactions.py:139,228`; accepts `1e3`, `1e30`, `_`, non-ASCII digits, ... | Make `domain/money.py:parse_amount_str` the only parser (reject exponents, `NaN`/`Infinity`, non-ASCII digits, magnitude above a named `MAX_MINOR`, catch `InvalidOperation`); new `web/params.py` with shared `parse_date`, ... |
| Q-024 | Medium | Confirmed | B/C/H2 / `repo-bypass` | Batch undo endpoints bypass the repository layer, replay 'the latest audit row' of any operation, do not restore all state and write no audit entry | `web/routers/planned.py:112-181` (raw SELECT at `140`, raw UPDATE at `155`), `web/routers/recurring.py:470-545` (raw SELECT at `501`, ... | Delete the SQL from both routers |
| Q-025 | Medium | Probable | B/C / `txn-boundary` | Compound mutations and their guard reads are not inside one transaction: double-submit can promote twice, concurrent writers fail with 'database is locked' | `repositories/_shared.py:113-143` (deferred `BEGIN`); `services/planned.py:149-193,221-224`; `services/recurring.py:356-500`; `services/reconciliation.py:62-120`, ... | `BEGIN IMMEDIATE` in `repositories/_shared.transaction` (waits on `busy_timeout`); move the guard reads inside, ... |
| Q-026 | Medium | Confirmed | C / `scoping-gap` | Soft-deleting an account drops its balance from fortune and leaves live recurring rules and planned rows pointing at it (promotion still posts to it) | `web/routers/accounts.py:348-354`; `repositories/accounts.py:138-155`; `repositories/_shared.py:199-200`; `services/_promotion.py:41-60`, ... | New `services/accounts.archive_account()` that refuses (typed error, 409 with a message) when the balance is not zero or live rules/planned rows reference it, or deactivates them in the same transaction, ... |
| Q-027 | Medium | Confirmed | D/H2/H3/H4 / `security-control` | Authentication abuse controls: the real client IP is lost behind Docker NAT (every client is the gateway 172.18.0.1) so the per-IP login bucket is shared and `audit_log.ip` is useless, `--forwarded-allow-ips=*` trusts the header by name, throttled and failed logins write unbounded attacker text to the DB, and one user can lock out another | `Dockerfile:104-108` (`--proxy-headers --forwarded-allow-ips=*`); `web/routers/auth.py:85-143,146-203` (`_client_ip`, `login_rate_limit`, `reauth_rate_limit`), ... | Stop trusting the header by name: `--forwarded-allow-ips` set to the proxy's fixed address, proxy overwrites `X-Forwarded-For` and `X-Real-IP`, ... |
| Q-028 | Medium | Confirmed | H2 / `missing-invariant-test` | The recurring-rule save path skips the source-category validation that preview performs: foreign or nonexistent category ids and zero-amount formula rules are persisted | `web/routers/recurring.py:181-230` (`_resolve_amount_inputs`, used by create `:268` and update `:632`), ... | Move `_invalid_source_ids` to a shared service function and call it (with the positive-amount rule) in `_resolve_amount_inputs`; extend the two-user formula test to the create/update paths. |
| Q-029 | Medium | Confirmed | A/C / `money-arith` | Currency exponent table lists only JPY/KRW (and a few others): 21 accepted ISO codes are mis-scaled, including ISK which is FX-reachable | `domain/money.py:14-23` (`_CURRENCY_DECIMALS`), `:26-195` (accepted list, `currency_decimals`); `services/accounts.py:197-200` (accepts any 3-letter code) | Generate the exponent table from ISO 4217 (all codes) next to `ISO_4217_CURRENCIES`; unit test in `tests/unit/domain/test_money.py` that every offered code has an explicit entry, ... |
| Q-030 | Medium | Confirmed | A / `duplicate-logic` | Forecast and budget disagree on which categories and overdue items count: archived categories reserve budget in the daily overlay, overdue planned items are dropped from the forecast stream | `services/forecast.py:581,447` (`directions_by_cat` built `include_deleted=True`), `:686`, `:254,262-283` (`event_start = today + 1`), ... | Decide the policy once (operator, OQ-6/OQ-18), then `services/categories.py:expense_category_ids(conn, user, *, ... |
| Q-031 | Medium | Probable | A/C/F / `clock` | Two notions of 'today': display-timezone date (8-9 sites) vs host-clock `date.today()` (16-18 sites); time-dependent tests can fail at month end or in the Warsaw midnight window | tz-aware: `web/routers/today.py:48,109,160`, `plan.py:76,272`, `budget.py:126,156,183`; host clock: `db/migrate.py:155`, `repositories/recurring.py:227`, ... | New `budget_planner/clock.py`: `utc_now()`, `today_local(settings)` and an injectable override (`ContextVar`) used by tests and the visual suite; a `today` FastAPI dependency for routers; services never call `date.today()`, ... |
| Q-032 | Medium | Probable | C / `duplicate-logic` | 'Current' balance includes future-dated transactions while forecast day 0 and the sparkline do not | `services/balance.py:87-107` (`as_of_date=None` counts all), `:210-217`; `web/today_data.py:116`, ... | Decide the rule once (ADR amendment, operator OQ-16): `balance.as_of_today(conn, user, account, today)` used by every consumer; if future-dated actuals are allowed they stay out of 'current'. |
| Q-033 | Medium | Confirmed | C / `layer-leak` | N+1 query storms on /accounts and /forecast (about 2900 and 2800 statements per request on the demo DB) | `services/balance.py:191-217` (90 `derive_balance` calls per account, 3 queries each), `:87-107`; `web/routers/accounts.py:68-70`, ... | `balance.balance_series`: one transactions query then a running sum; in forecast/today/budget load rules, overrides, planned rows and budget tiers once into dicts and pass them down; add a pytest `assert_max_queries(route, ... |
| Q-034 | Medium | Confirmed | C / `scoping-gap` | No `user_id`-leading indexes on the large multi-user tables; a session write on every request | `migrations/0012_multi_user.sql:212-219,274-275,338`; `repositories/retention.py:26,37`; `repositories/sessions.py:248` | New migration: `(user_id, operation_date) WHERE deleted_at IS NULL` on `transactions` and `planned_transactions`, `(user_id, id)` on `audit_log`, `(user_id, active)` on `recurring_rules`, ... |
| Q-035 | Medium | Confirmed | C/D / `security-control` | Unbounded work per request: all-row loads for counts and balances, unbounded page size and body size, full `PRAGMA integrity_check` on every unauthenticated `/ready` probe | `web/routers/ledger.py:68,377-390` (`len(list_filtered(... limit=None))`, `page_size` unbounded), `domain/transactions.py:91`, `services/balance.py:77-82`, ... | `SELECT COUNT(*)` / `SUM` repository functions for counts, balances and aggregates (also ADR-0081); clamp `page_size` to a named maximum in `parse_filters`; field lengths in service drafts (name 120, description 500), ... |
| Q-036 | Medium | Confirmed | A / `duplicate-logic` | Direction-to-sign logic exists in six hand-written copies (and default branches that would swallow a new direction) | `services/balance.py:42`, `services/ledger_totals.py:22`, `services/forecast.py:128,751,770`, `services/account_planned.py:74`, ... | One `domain` function `signed_legs(direction, amount, account, dest)` returning legs with an exhaustive `match` and `assert_never`; the others become one-line adapters; adjustment policy stays an explicit parameter. |
| Q-037 | Medium | Confirmed | E / `htmx-contract` | HTMX 404/409/500 responses carry an out-of-band flash that htmx never swaps; failed saves and expired CSRF tokens are silent | `web/errors.py:55-77,91,107,129`; `static/js/app-init.js:4-10` (only 422/429 forced to swap); `static/js/users-admin.js:73-82`; `templates/base.html:6-7`, ... | One global `htmx:beforeSwap` handler in `app-init.js` replacing the 422/429 block: for any 4xx/5xx with `hx-swap-oob` set `shouldSwap = true; isError = false`, ... |
| Q-038 | Medium | Confirmed | A/E / `htmx-contract` | HTMX event contract is half dead: four `*-stale` events (27 emit sites, 45 string literals) have no listener, toast payload uses `kind` and `variant` inconsistently | emit sites `routers/{categories,recurring,accounts,transactions,budget,planned}.py` (e.g. `transactions.py:313,432,443,457`, `budget.py:262-427`, `planned.py:91,162`, ... | `web/htmx.py`: `Event` constants and `invalidate(response, *domains)` mapping domain to events once, `toast_payload(variant, message, undo=...)` for all emitters, ... |
| Q-039 | Medium | Probable | A/E / `template-logic` | 'Left per day' and percent-used are re-derived in templates in float, ignoring the service value; per-day divisors and zero guards differ per page | `web/templates/today/index.html:28-36`, `plan/_budget_tab.html:2-12,56-59`, `_partials/components/_period_header.html:4-8`, `budget/index.html:102-108`, ... | Add `left_per_day_minor`, `spent_pct`, `committed_pct`, `remaining_after` to `MonthSummary` (or a `BudgetView` in `web/`), render only those, delete the `set` blocks; decide the afford clamp once |
| Q-040 | Medium | Probable | H1 / `ci-trust-boundary` | Prod accepts an image signed by `build.yml` from any ref; any branch can push and sign `sha-*` images, and rollback resolves mutable tags without an ancestry check | `terraform/modules/compute/user_data.tf:118` (`identity_regexp` ends at `build.yml@`), `terraform/host/agent/bp_agent.py:410-411`, ... | Pin the verified identity: `identity_regexp = ...build\.yml@refs/(heads/main\|tags/v[0-9]+\.[0-9]+\.[0-9]+)$` (drill hosts keep a looser pattern via a variable), ... |
| Q-041 | Medium | Confirmed | H1 / `ci-trust-boundary` | The merge gate is self-attested: required checks come from PR-editable workflows, are not bound to an app, and need no review | ruleset `protect-main` (`repro/H1/gh_api/ruleset_protect_main.json`: six required contexts without `integration_id`, zero required approvals, no code-owner review, ... | Ruleset `workflows` rule (workflows referenced from `main`) for `ci`, `security`, `lock-check`; `integration_id` 15368 on every required context; `.github/CODEOWNERS` over `.github/`, `scripts/ci/`, `terraform/`, ... |
| Q-042 | Medium | Confirmed | H1 / `ci-trust-boundary` | The `drill-gate-skip` classifier treats paths as inert that deploy, CI and agent tooling consume, and its verdict and status target come from different moments (TOCTOU) | `scripts/ci/drill_gate_skip.py:16-37` (`SAFE_DIRS`: docs, `.claude`, tests, top-level `*.md`), ... | Shrink the allowlist to what nothing executes: `docs/**` except `restore-log.md`, top-level `*.md` except `CLAUDE.md`; drop `.claude/` and `tests/`; unit test greps `.github/` and `scripts/ci/` for paths under allowlisted dirs |
| Q-043 | Medium | Probable | G / `dependency` | Unused dev dependency `httpx2` of unverified provenance is locked and installed by `uv sync` on every developer machine and CI run | `pyproject.toml:44` (`httpx2>=0.1`), `uv.lock:739-746` (2.16.0); no import in `src/`, `tests/`, `scripts/`; leftovers `pyproject.toml:136,172` (plotly overrides) | Check provenance first (PyPI project page, who added it in `git log -S httpx2`); then remove `httpx2` and the plotly entries and re-lock |
| Q-044 | Medium | Confirmed | G / `config-drift` | `just ci` and PR CI omit checks that pre-commit enforces (ruff format, bandit, detect-secrets, tailwind-check) and tool versions drift between pre-commit pins, `uv.lock` and CI | `justfile:92-98,116`; `.pre-commit-config.yaml:26,33-58,70,76-83,125-131`; `.github/workflows/ci.yml:26,42,51,68` (re-check: `audit/quality` absorbed T-D158 CI changes) | Run the hooks as `repo: local`, `language: system`, `entry: uv run <tool>` so every linter uses the lock (as `pytest-fast` already does), drop hook-side `rev` pins, pin `uv` in `ci.yml`, ... |
| Q-045 | Medium | Confirmed | B / `layer-leak` | No service layer for CRUD: 13 routers import repositories and 6 write through them | writes from routers: `categories.py:109,192,211`, `accounts.py:225,325,354,377,497`, `transactions.py:295,416,441,453`, `planned.py:269,385,413,427`, ... | One CRUD service per entity (`services/transactions.py`, `planned.py`, `accounts.py`, `recurring_rules.py`, `budget_overrides.py`; `categories.py` exists) that validates and calls repositories, ... |
| Q-046 | Medium | Confirmed | B / `oversized-module` | Two files over 800 lines and 16 router functions of complexity C or worse | `web/routers/recurring.py` (1115 lines, MI B 17.61, 17 suppressions, 109 `Any`), `services/forecast.py` (978), `web/routers/plan.py:68` (E 31), ... | Do the splits of table 2.4 after Q-045 (routers shrink as services appear); introduce xenon at `--max-absolute C` in `just lint` only after the E and D blocks are gone. |
| Q-047 | Medium | Confirmed | A/B / `import-cycle` | Import cycle `repositories.recurring <-> services.recurring <-> services.recurring_formula` forces nine `PLC0415` lazy imports; 28 unnecessary function-level imports; `next_due` seeding copied in three places | `repositories/recurring.py:31,128,227`, `services/recurring.py:309,384,408,515,603,635-638`, `services/recurring_formula.py:166,167,213,336,392`, ... | Extract the pure scheduling code (`generate_occurrences`, `advance_next_due`, `first_due_on_or_after`, `occurrence_in_month`, `_STEP_MONTHS`, `_build_lookup_stub`) into `domain/recurring_schedule.py`, ... |
| Q-048 | Medium | Confirmed | B / `wide-signature` | Eight service signatures have adjacent same-typed positional parameters; the rule is noise on 24 route handlers | `services/reconciliation.py:62`, `services/budget.py:408`, `services/forecast.py:433,530,778`, `services/recurring.py:641`, `services/recurring_formula.py:322`, ... | Keep `conn, user_id` positional and make everything after them keyword-only (`*`) in the eight service functions (about 12 callers), ... |
| Q-049 | Medium | Confirmed | B / `repo-bypass` | Audit-free repository helpers are public API and `user_preferences` writes are unaudited | `repositories/recurring.py:269` (`set_next_due`), `:294` (`set_inactive`), `:406` (`mark_override_promoted`), `repositories/preferences.py:43,59` | Move the three helpers to `repositories/_unaudited.py` and add an architecture test (beside `tests/architecture/test_user_id_filter.py`) that fails when anything other than `services/recurring.py` imports it, ... |
| Q-050 | Medium | Confirmed | G / `dead-code` | Routes with no caller; the ADR-0056 live formula preview is unreachable from the UI | `web/routers/recurring.py:546` (formula preview), `:424` (batch promote-due), `web/routers/accounts.py:133`, `budget.py:347`, `plan.py:254`, ... | Decide per route: re-wire the preview in the entry form (or in the ADR-0107 redesign) or delete route, template and tests; delete the other four. |
| Q-051 | Medium | Confirmed | G / `doc-drift` | ADR status and index hygiene: 15 ADRs say Proposed but are live, amendments live only in the README index, duplicate numbers and broken links | `docs/adr/` 0032, 0033, 0034, 0035, 0037, 0050, 0051, 0054, 0056, 0061, 0078, 0106, 0107, 0118, 0127 (status line 3); status lines of 0002, 0011, 0012, 0015, 0017, 0018, ... | One docs-first PR: flip the 13 implemented ADRs to Accepted, 0106/0107 to 'Accepted, implementation pending' (operator OQ-24), ... |
| Q-052 | Medium | Confirmed | G / `doc-drift` | ADR bodies and comments contradicted by code (ADR-0002, 0023, 0026, 0036, 0052, 0057; stale ADR-0005 and 'Phase 7' comments) | ADR-0002 lines 15-16, ADR-0023 section 1, ADR-0026/0028 (`fab_target_for`), ADR-0036 lines 68, 108-109 vs `terraform/cloud-init/compose/docker-compose.yml.tpl:122`, ... | Edit each status line to the true state (partly superseded by N); ADR-0036 gets a dated addendum (stock `caddy:2.8`, app-side rate limiting per ADR-0072); ADR-0057 either gets validation or the text is corrected, ... |
| Q-053 | Medium | Confirmed | D/G / `doc-drift` | CLAUDE.md, the orchestrator skill and `requirements.md` section 3 and 6.7 contradict the code (paths that do not exist, Plotly/CDN stack, FAB and shortcuts, fail2ban and CSP claims) | `CLAUDE.md` (change policy item 1, handoff checklist, Stack line); `.claude/skills/orchestrator-mode/SKILL.md:62-63`, ... | Docs-first edits (CLAUDE.md order): CLAUDE.md and the skill name `docs/plans/<plan>/{tasks,implementation_plan}.md` and the real stack and commands, ... |
| Q-054 | Medium | Confirmed | G / `doc-drift` | Task status in `tasks.md` disagrees with CHANGELOG and ADRs | `docs/plans/v1/tasks.md:515,519,670`; `docs/plans/v3/tasks.md:920,952`; `docs/plans/v2/tasks.md` (60 rows open, e.g. T-R71 to T-R73), ... | Reconcile the listed rows once (operator decides whether the v2 plan is closed as superseded by ADR-0107, OQ-22), ... |
| Q-055 | Medium | Probable | F / `weak-assertion` | Non-priority modules: 213 surviving mutants rule-defaulted (analytics, users, planned, upcoming, today, export, replication_health, preferences) | `baseline/mutmut-real-gaps.md` rows 310-516 (`analytics` 322-358, `users` 488-516, `planned` 403-429, `upcoming` 471-487, `replication_health` 440-454, ... | Fix after the priority-module findings, module by module with the 'suggested killing test' column, starting with `analytics` (after Q-008) and `today`; re-triage the sampled rows first. |
| Q-056 | Medium | Confirmed | F / `weak-assertion` | Four of the five 'critical flow' e2e tests are API tests run in a browser; no test submits the add, reconcile, promote or budget forms through the UI | `tests/e2e/test_add_transaction_flow.py:19-68`, `test_reconcile_flow.py:19-65`, `test_recurring_promote_flow.py:26-100`, `test_set_budget_flow.py:19-62`, ... | Rewrite the four tests to drive the visible forms (`get_by_role(...).click()/fill`) for one happy path each; keep `request.post` only for seeding. |
| Q-057 | Medium | Probable | F / `htmx-contract` | `test_pagination_keeps_filters` races two in-flight HTMX responses; the product has no `hx-sync` | test `tests/e2e/test_ledger_filters.py:73-81,109-114`; product `templates/ledger/index.html:25-29`, `templates/ledger/_table.html:386-389` | Product: `hx-sync="#ledger-table:replace"` on the form and the button |
| Q-058 | Medium | Confirmed | F / `weak-assertion` | The web test client hides transport-level bugs: CSRF header attached to every request, https forced, FX client built with a `base_url` production never sets | `tests/integration/web/conftest.py:45-70` (`_CSRFAwareTestClient`), `tests/e2e/conftest.py:217`, `tests/unit/services/test_fx.py:20-24`, `test_forecast*` | FX: one client factory in `services/fx.py` (Q-007) with tests injecting a transport into the same factory, ... |
| Q-059 | Medium | Confirmed | F / `weak-assertion` | 141 HTTP tests assert only the status code and the reconciliation 'rollback' test is vacuous (it fails the only write) | `tests/integration/web/test_recurring.py` (24), `test_budget.py` (17, e.g. `:83-85,103-105`), `test_categories.py` (14), `test_planned.py` (11), `test_accounts.py` (11), ... | Add a read-back assertion through the repository (or the rendered value) to each success-path test and a row-count-unchanged assertion to each rejection test, starting with `test_budget.py`, `test_recurring.py`, ... |
| Q-060 | Medium | Probable | F / `scoping-gap` | Prod-DB isolation in tests depends on `BUDGET_ENV=test` being set by default and on convention; there is no tripwire | `tests/conftest.py:19` (`os.environ.setdefault("BUDGET_ENV", "test")`), `config.py:20-21,45` (relative default `sqlite:///data/budget.sqlite`), ... | Autouse session fixture in `tests/conftest.py` that sets `BUDGET_DATABASE_URL` to a session temp path and unsets `BUDGET_PLANNER_ADMIN_*`, ... |
| Q-061 | Medium | Confirmed | F / `config-drift` | The visual suite is opt-in, byte-exact, silently creates missing baselines, and its baselines predate the last template change | `justfile:78-84`, `pyproject.toml:159-160`, `.github/workflows/*.yml` (no visual job), `tests/visual/test_snapshots.py:105-109,116` | Scheduled/nightly workflow on a pinned Playwright image, perceptual threshold (`max_diff_pixel_ratio`), a missing baseline is a failure in CI, and a pre-commit check that baselines change when `templates/` change |
| Q-062 | Low | Confirmed | H3 / `security-control` | Session and passkey hardening (defence in depth): challenges not single-use, in-flight request re-sets the rotated token, passkey revoke keeps its sessions, CSRF token unbound | `web/auth_cookies.py:150-205`, `web/routers/auth.py:392-425,583-592`, `services/auth.py:383-392,411-413,455-465`, `services/reauth.py:135-169`, ... | (H3-02) single-use challenge nonce table (`DELETE ... RETURNING` at finish) and do not revoke on a regression with `new == stored == 0` |
| Q-063 | Low | Confirmed | H2 / `htmx-contract` | Admin edge cases: an absent `is_admin` field demotes the target; concurrent admin changes surface 'database is locked' as 500 | `web/routers/settings_users.py:77-78,228-264`; `services/users.py:385-392`; `repositories/_shared.py:113-143` | Treat a missing `is_admin` as unchanged (or require an explicit hidden 0); `BEGIN IMMEDIATE` for admin mutations and map `OperationalError` to the 409 flow. |
| Q-064 | Low | Confirmed | D / `security-control` | 500 responses skip the security-header and no-store middleware; exception text bypasses log redaction | `web/errors.py:117-125,155-156`; `web/app.py:187-199`; `logging.py:25-55,77-90` | One pure-ASGI middleware registered outermost for the baseline headers and no-store, plus a test that forces a 500 and asserts all headers, ... |
| Q-065 | Low | Confirmed | D/E / `security-control` | CSP exists only at the proxy; the app trusts a client-supplied nonce and carries dead nonce and `csrf_token` stubs | `web/middleware/security_headers.py:41-78`; `terraform/cloud-init/compose/Caddyfile.tpl:49-54`; `deploy/Caddyfile:5-8`; `web/rendering.py:39,59`, `web/errors.py`, ... | Emit the CSP from `SecurityHeadersMiddleware` (app-generated nonce, inbound header ignored, Caddy stays a second layer) with a test; remove the `csrf_token` stub and the unused `csp_nonce` context key, ... |
| Q-066 | Low | Confirmed | D/H4 / `config-drift` | Declared-but-unenforced and exposed surfaces: `BUDGET_TRUSTED_HOSTS` never enforced; `/docs`, `/openapi.json` and `/dev/components` live in production | `config.py:54-57,169-176`; `terraform/cloud-init/compose/docker-compose.yml.tpl:23`; `web/app.py:168,187-199`; `web/routers/dev_components.py:17-27` | Register Starlette `TrustedHostMiddleware(allowed_hosts=settings.trusted_hosts)` when non-empty; register `dev_components` only when `settings.env != "production"` and build the app with `docs_url=None, ... |
| Q-067 | Low | Confirmed | D/H4 / `infra-exposure` | Docker-published ports bypass ufw; the tailnet-only drill relies on the cloud security group alone | `terraform/cloud-init/compose/docker-compose.yml.tpl:125-130`; `terraform/cloud-init/bootstrap.yaml.tpl:125-135,238` (re-check at remediation) | Bind the Caddy ports to the tailnet address for the drill (Terraform variable) or filter in the `DOCKER-USER` chain beside the metadata guard; update ADR-0101 to say where the control sits. |
| Q-068 | Low | Confirmed | D/H1/H4 / `dependency` | Pinning gaps: mutable Caddy/Litestream/base-image tags, floating `uv`/tailscale/cloud-init versions, Actions repo settings weaker than the runbook | `terraform/cloud-init/compose/docker-compose.yml.tpl:4,60,77,102,122`; `Dockerfile:9,24,43`; `.github/workflows/ci.yml:25`, `security.yml:50,111,126`, ... | Pin `caddy`, `litestream` by `@sha256:` digest (the host agent can verify), the base image digest and `uv`; pin tailscale and `cloud-init` versions; set `sha_pinning_required: true`, `allowed_actions: selected`, ... |
| Q-069 | Low | Confirmed | H1 / `ci-trust-boundary` | Release `ci` job runs third-party installers with write-capable tokens; `.security-allowlist.yml` is read from the PR checkout and reaches a `run:` line unescaped | `.github/workflows/release.yml:27-31,76-79`, `ci.yml:16-86`, `security.yml:62-75`, `.security-allowlist.yml` | `permissions: contents: read` on `ci.yml` and the `ci` job of `release.yml`, grant the rest per job; pass the allowlist through `env:` and a validated array (`^[A-Za-z0-9-]+$`) and read it from `origin/main`. |
| Q-070 | Low | Probable | E / `template-logic` | Credit-card utilisation computed in three templates plus the router; hard-coded `10` default month and `'PLN'` fallbacks in templates | `partials/accounts/_card.html:3-7`, `_row.html:17-19`, `accounts/index.html:77-79`, `routers/accounts.py` (`_uses_available`); `partials/budget/_override_form.html:8`, ... | One `credit_utilisation(card)` returning `used_minor, available_minor, used_pct` in the accounts view model; the view model supplies `currency` and month and templates fail (StrictUndefined) instead of defaulting. |
| Q-071 | Low | Probable | E / `duplicate-logic` | `passkeys.js` duplicates the login and re-auth flows and swallows every error | `static/js/passkeys.js:21-24,65-72,111-192,240-244`; `static/htmx-csrf.js:26-30` | Extract `runAssertion(beginUrl, finishUrl, status, errorMsg)`, share `csrfToken()` via a tiny `csrf.js`, log `err.name` to `console.debug`, rename `resp403` to `isReauthRequired`. |
| Q-072 | Low | Confirmed | E/G / `dead-code` | Dead code kept alive: legacy redirects and aliases past expiry, symbols used only by tests, `bulk-select.js` (no markup, would omit the CSRF header if revived) | `web/routers/analytics.py`, `routers/budget.py:306`, `categories.py:22`, `planned.py:55`, `recurring.py:58`, `transactions.py:113`, `plan.py:284`, `today.py:175`, ... | One cleanup task: remove the redirects, `routers/analytics.py`, the `/afford` and `/budget-legacy` aliases, update `_ROUTER_NAMES` and `extra_paths`; delete the listed symbols and their tests, ... |
| Q-073 | Low | Confirmed | C/G / `silent-fallback` | Router registration swallows `ImportError`: a router that fails to import is silently skipped | `web/app.py:236-247` (`except ImportError: continue  # pragma: no cover`) | Replace the loop by explicit imports and `include_router` calls (no `importlib`, no `try`). |
| Q-074 | Low | Confirmed | B / `layer-leak` | Small layering and functional-first deviations: module-level mutable state, two SQL queries in a service, `web -> db` contract broken by five modules, docstrings contradicting soft-delete | `repositories/_shared.py:98` (`_TX_DEPTH` keyed by `id(conn)`), `services/recurring_formula.py:240`, `web/routers/recurring.py:78`; `services/accounts.py:35-53,63-80`, ... | `ContextVar` for transaction depth; `MappingProxyType` for `_EMPTY_TERM_INPUT`; ADR-0021 sentence on framework classes and memo parameters, ... |
| Q-075 | Low | Probable | A / `duplicate-logic` | Tier resolution has two implementations and the receiving screens use three different 'monthly average' definitions | `services/budget.py:183,603,515-523`, `web/routers/budget.py:99,206`, `services/analytics.py:152`, `_mean_minor` in `budget.py:240` and `analytics.py:138` | New `services/aggregates.py` (`mean_minor`, `sum_by_category(txns, to_base)`) and one pure `pick_tier(one_off, recurring, default)`; document one average definition after the operator decides. |
| Q-076 | Low | Confirmed | C / `money-arith` | No single rounding policy (HALF_UP, HALF_EVEN, float `round()`, floor division) and retention window compares mismatched timestamp formats | `domain/money.py:198-207`, `services/recurring_formula.py:68,135`, `services/fx.py:142,164`, `services/today.py:50`, `web/routers/today.py:141`, ... | `domain/money.py` exports `round_div` (HALF_EVEN) and `round_scaled`; document the policy in ADR-0006; compare with `strftime('%Y-%m-%dT%H:%M:%fZ','now',?)` and one precision (`utc_now_iso`). |
| Q-077 | Low | Confirmed | F / `weak-assertion` | Test hygiene: duplicated tests and fixtures, 15 permanently skipped pre-redesign tests, tests with no meaningful assertion | `tests/e2e/test_accessibility.py:24-31`; `conn` fixture in `tests/integration/conftest.py:54`, `tests/unit/services/conftest.py:17`, ... | Delete the e2e landmarks test and one of the duplicate promotion tests; move `conn` and an autouse fast-bcrypt fixture to `tests/conftest.py` and route URLs through `sqlite_url` (also helps Q-060), ... |
| Q-078 | Low | Confirmed | H4 / `infra-exposure` | Unauthenticated status endpoints disclose the exact running image ref and digest, deploy generation, restore result and replica generation | Caddy `handle /.well-known/bp-deploy-status.json` (file server on `/srv/bp-status`), `/health`, `/health/replication` | Trim the status JSON to `state`, `generation` and a short ref, or require a deploy-token header at Caddy for that path; or accept (tailnet only) and record it in ADR-0111. |
| Q-079 | Low | Confirmed | H4 / `security-control` | Hardening is app-only: Caddy and the three Litestream containers run as root with a writable rootfs and no dropped capabilities, and the flat `edge` network lets them reach the app | rendered `docker-compose.yml` (`terraform/cloud-init/compose/docker-compose.yml.tpl`), `daemon.json` (`icc:false` covers only the default bridge) | Add `read_only`, `cap_drop: [ALL]` and `user:` where the images allow; put the Litestream services on a network separate from the app. |
| Q-080 | Low | Confirmed | H4 / `infra-exposure` | The initial admin password and the cookie secret stay in the app container environment for its lifetime and are readable via `docker inspect` by any `docker` group member | the initial-admin-password and cookie-signing variables in the rendered compose and `bp-config`; Terraform state | Seed the admin through a one-shot container or file that is removed, or drop the variable from the rendered compose after first login (host-agent generation bump). |

## Details

### Q-001 — Income-anchor endpoint is hard-wired to user 1: any user can set or clear the owner's anchor and probe the owner's categories, and no other user can set their own
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** D/H2 / `scoping-gap`
- **Track aliases and calibration:** D-01 High; H2-01 High
- **Calibration note:** D-01 and H2-01 both High. Both tracks say Critical if more than one active user: operator fact is one active user today, so High, but this MUST be fixed before a second user is onboarded.
- **Priority flag:** **Fix before a second user is onboarded**
- **Location(s):** `web/routers/budget.py:375-399` (literal `1` at lines 387 and 394); callee `services/preferences.py:44-58`; read side `services/budget.py:421`
- **Description:** The handler has no `current_user_id` dependency and passes the constant `1` to `set_income_anchor_category_id`. Any signed-in user can clear or overwrite user 1's anchor (which drives user 1's fiscal-month window), learn the existence and direction of user 1's categories from the 200/422 answers, and cannot set an anchor of their own (422 for their own income category). Violates ADR-0061 section 5.
- **Evidence:** `tracks/D-security.md` D-01; `tracks/H2-isolation.md` H2-01; `repro/H2/h2_01_anchor_oracle.py` + `h2_01_anchor_oracle_output.txt` (user 1's row changed 5 to 23, then deleted by user 3).
- **Impact:** Cross-user write plus a small cross-user read oracle; the Settings anchor control is dead for every non-first user. Harmless today (one active user); live the day a second user is onboarded.
- **Mitigation:** Add `user_id: int = Depends(current_user_id)` to `set_income_anchor` and pass it to both service calls. Add a two-user integration test (user 2 writes own row, user 1 untouched, user 2 cannot probe user 1's ids) and an architecture test under `tests/architecture/` that fails on an integer literal passed as `user_id` anywhere under `web/` and `services/`.
- **Effort:** S
- **Related:** ADR-0061, ADR-0025, requirements 6.9; Q-015 (two-user fixtures); Q-028 (formula save validation)
- **Verification:** D-01: V2 Confirmed (High). H2-01: V3 Confirmed (High; Critical once a second active user exists). One fix for both.

### Q-002 — Forecast budget-overlay helper counts a recurring occurrence twice when a linked planned row exists; occurrence expansion is hand-rolled in seven places
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** A / `duplicate-logic`
- **Track aliases and calibration:** A-04 High; A-17 Medium
- **Priority flag:** **Biting on current PLN data**
- **Location(s):** `services/forecast.py:345-390` (`_committed_future_for_category`, no `linked_occurrence_keys` filter); the seven loops: `services/budget.py:296-310`, `forecast.py:262-283,373-381,737-770`, `account_planned.py:106-116`, `income.py:25-93`, `upcoming.py:74-174`, `recurring_formula.py:146-190`
- **Description:** ADR-0087 (amendment): a linked, unpromoted planned row stands for its occurrence and consumers must skip the virtual one. Budget, forecast events, flow sums and `account_planned` do; the overlay helper forgot. Root cause: seven independent "rules x overrides x dedup x window" implementations.
- **Evidence:** `tracks/A-duplication.md` A-04, A-17; `repro/A/output/inv_03b*` (rule 1530 + linked planned row: budget committed 1530, forecast 3060); V1 repro `repro/verify/V1/v_a04.py` (`out_a04.txt`).
- **Impact:** Monthly `planned_budget` and the daily overlay `unaccounted` are understated by the duplicated bill for every re-dated recurring occurrence. Needs no FX: bites on PLN-only data whenever a re-dated occurrence exists.
- **Mitigation:** Step 1 (S): make `_committed_future_for_category` delegate to `budget._committed_by_category` (single copy with dedup and FX), deleting the second implementation. Step 2 (L): one `pending_occurrences(conn, user_id, *, start, end, include_overdue, category_ids)` in `services/recurring.py` (overrides, `linked_occurrence_keys` dedup, half-open window) used by all seven consumers; add the invariant test from Q-013 (budget committed == forecast committed).
- **Effort:** S then L
- **Related:** ADR-0087, ADR-0085, ADR-0105; Q-030 (overdue/archived policy), Q-013, Q-017 (forecast tests)
- **Verification:** V1: A-04 Confirmed (repro v_a04), High. A-17 structure only (not sampled).

### Q-003 — Budget period window: the no-anchor fallback drops the last day and shortens the per-day divisor; month/period helpers are copied 4-6 times and the plan router re-implements the period for other months
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** A/B / `duplicate-logic`
- **Track aliases and calibration:** A-05 High; A-14 Medium; B-05 Medium
- **Calibration note:** Bites on PLN data only when no income anchor is configured (or in the fallback month); operator to confirm the prod anchor state.
- **Priority flag:** **Biting on current PLN data**
- **Location(s):** `services/budget.py:364-385` (`_resolve_anchor`), `:546,551,566` (`end_of_month`, `days_until_next_income`, exclusive `end`), `:388-436`; `services/account_planned.py:66` (`+ 1 day`); month bounds `budget.py:203`, `analytics.py:84`, `forecast.py:317`, `recurring_formula.py:123`; month shift `budget.py:176`, `forecast.py:621`, `web/routers/plan.py:96`; `web/routers/plan.py:68-251` (`plan()`, CC E 31, 184 lines; `:115-178` fiscal override and total rebuild; anchor day capped at 28)
- **Description:** With an income anchor the 'next income date' is exclusive; the fallback reuses the variable with the inclusive last day of the month, so a committed item on the last day is dropped and days remaining is one too few (about 9 percent inflated left-per-day on Nov 19). `account_planned` adds the missing day, budget does not. The same window logic exists in 4-6 copies and the plan router rewrites service results for non-current months (anchor day capped at 28, committed zeroed, unguarded `replace(year=...)`).
- **Evidence:** `tracks/A-duplication.md` A-05, A-14; `tracks/B-layering.md` B-05; `repro/A/output/inv_07*` (item on Nov 30: budget delta 0, account_planned 5000; divisor 11 vs 12); `repro/B/b_router_logic.out`.
- **Impact:** Today hero 'left per day' and Budget totals wrong for users with no income anchor (also in a month where the anchor lookup misses). Plan month picker shows different period bounds than Today/Budget for anchors on day 29-31.
- **Mitigation:** New `domain/periods.py`: `month_bounds`, `shift_month`, `fiscal_window(anchor_date, today) -> [start, end)` half-open. `_resolve_anchor` fallback returns first-of-next-month; `account_planned.resolve_window` and `budget` use the same helper (delete the five month-bounds copies). Move `plan.py:111-178` into `services/budget.py:month_summary_for_picker(conn, user_id, year, month, today)` returning the final dataclass; split `plan()` per tab; use the shared `parse_year_month` (Q-023).
- **Effort:** M
- **Related:** ADR-0041, ADR-0064, ADR-0085; Q-031 (clock), Q-023, Q-039; operator Q on payday divisor (OQ-14)
- **Verification:** V1: A-05 Confirmed (code), High, 'fallback path only'. A-14 code-confirmed. B-05 not sampled.

### Q-004 — Transit transactions without a destination account can be persisted through create, update, planned and reconcile; every later balance computation raises and /accounts, /today and /forecast return 500
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** B / `layer-leak`
- **Track aliases and calibration:** B-02 High
- **Calibration note:** Bites if the user hits the form path; no evidence either way for prod. Stays High (not Critical): self-inflicted and recoverable.
- **Priority flag:** **Biting on current PLN data**
- **Location(s):** `web/routers/transactions.py:263-283` (create validates a destination only `if dest_account_id and ...`), `:358-430` (update: no category or destination check); `web/routers/accounts.py:489-495` with `services/reconciliation.py:62-120`; `web/routers/planned.py:220-300`; compare `services/_promotion.py:41-60` (the only service-level guard); `services/balance.py` (false comment 'schema CHECK blocks it')
- **Description:** The transit shape rule (destination required, distinct account, same currency) exists in `_promotion.validate_promotion` and a router copy in `recurring.py`; plain create/update/reconcile never call it and neither the repository nor the schema enforces it (only `account_id <> dest_account_id` is checked).
- **Evidence:** `tracks/B-layering.md` B-02; `repro/B/b_transit_validation.out`, `b_reconcile_transit.out`; V1 repro `repro/verify/V1/v_b02.py` (POST returns 200, persists, then /accounts, /today, /forecast all 500).
- **Impact:** One accidental submit (or re-categorising an expense as transit) takes down every page that derives that account's balance; recoverable only by deleting the row.
- **Mitigation:** New `services/transactions.py` with `create_checked` / `update_checked` calling one `validate_transit_shape(direction, account, dest)` extracted from `_promotion.validate_promotion`; use it from the transactions, planned and recurring routers and from `reconciliation.reconcile` (reject transit categories there). Last line of defence: `transactions_repo.create/update` raise on transit without `dest_account_id`.
- **Effort:** M
- **Related:** ADR-0008, ADR-0011; Q-045 (service layer); operator Q: allow user-defined transit categories? (OQ-9)
- **Verification:** V1: Confirmed (repro v_b02), High.

### Q-005 — Reconcile with a chosen income or expense category stores an adjustment of the wrong sign; the balance ends 2x|delta| away from the figure the user typed
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** C/F / `money-arith` (also `weak-assertion`)
- **Track aliases and calibration:** C-01 Critical -> High (verifier); F-07 High
- **Calibration note:** C-01 orig Critical: downgraded because no reconciliation ever used an income/expense category (operator).
- **Priority flag:** Latent (prod data does not trigger it today)
- **Location(s):** `services/reconciliation.py:99-112` (`stored_amount = abs(delta)`, docstring `:80-87` promises coercion); entry `web/routers/accounts.py:481-492`; options `web/templates/partials/accounts/_reconcile_modal.html:104-109`; missing test `services/reconciliation.py:100-103` (the four uncovered lines)
- **Description:** `reconcile()` stores `abs(delta)` and the sign then comes from the category direction. If the chosen category's direction does not match the sign of `delta`, the transaction moves the balance away from the typed figure. The modal lists every non-system category so it is UI-reachable. No test exercises the caller-supplied `category_id` path (mutants survive, F-07).
- **Evidence:** `tracks/C-correctness.md` C-01; `tracks/F-tests.md` F-07; `repro/C/repro_reconcile_and_parse.py` (B1, B2); V1 repro `v_c01` (balance ends at 50000 for target 150000).
- **Impact:** A 'reconciled' account differs from reality by 2x|delta|, persisted in the ledger and fed into fortune, forecast and budget spent. Latent: operator reports no reconciliation ever used an income/expense category.
- **Mitigation:** In `services/reconciliation.reconcile` raise `CategoryDirectionMismatchError` (422 in the route) unless the category is ADJUSTMENT, or INCOME with `delta > 0`, or EXPENSE with `delta < 0`; expose `categories_valid_for_delta` and restrict the modal options with it; reject transit categories (Q-004). Tests: one per direction asserting stored sign and `derive_balance == actual`, plus the unknown-category and `credit_limit_minor == 1` boundaries.
- **Alternatives:** Remove the 'Record as' selector and always use the Reconciliation system category (simplest, loses the feature).
- **Effort:** S
- **Related:** ADR-0008, ADR-0011; Q-004, Q-013
- **Verification:** C-01: V1 Confirmed (v_c01), Critical to High (latent). F-07: V3 Confirmed.

### Q-006 — Recurring schedule anchor: with a blank day-of-month `next_due` drifts permanently after a clamped month, and occurrences can be generated before the rule's start date
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** C / `date-boundary`
- **Track aliases and calibration:** C-06 High; C-13 Medium
- **Calibration note:** C-13 is Medium alone (V1) but shares the generator and fix with C-06, so the merged record is High. Operator to confirm no blank-dom rule starts after the 28th (OQ-5).
- **Priority flag:** **Biting on current PLN data**
- **Location(s):** `services/recurring.py:272-306` (`advance_next_due` stub with `start_date = from_date`; `anchor_day = rule.day_of_month or start.day` at `:130`); callers `:464-470,527-533`; `:123,143` (`hard_start` computed but `occ_date >= range_start` used); form field optional `web/templates/partials/recurring/_form.html:196-200`, `web/routers/recurring.py:370`
- **Description:** (C-06) Promoting a rule that started Jan 31 with blank day-of-month yields Feb 28, then Mar 28, Apr 28 (the explicit dom=31 control gives Mar 31, Apr 30): one clamp permanently shifts the schedule. (C-13) A rule starting Jan 20 with dom=5 generates an occurrence on Jan 5, before its start.
- **Evidence:** `tracks/C-correctness.md` C-06, C-13; `repro/C/repro_recurrence_boundaries.py`; V1 repro `repro/verify/V1/v_c06_c13.py` (`out_c06_c13.txt`).
- **Impact:** Forecast, budget committed and Upcoming show bills on the wrong day for the rest of the rule's life (C-06); a spurious pre-start occurrence (C-13, bites PLN data). C-06 latent: operator thinks no rule has a blank dom with a start after the 28th.
- **Mitigation:** Persist the anchor: default `day_of_month = start_date.day` in the create service (plus a one-off data fix in the remediation task) and make `advance_next_due` take the rule (anchored on `rule.start_date`), not a `from_date` stub. In the generator compare against `max(range_start, rule.start_date)`. Property test: repeated promotion yields exactly `generate_occurrences`. Share with the `domain/recurring_schedule.py` extraction (Q-047).
- **Effort:** S-M
- **Related:** ADR-0085; Q-047, Q-019 (recurring mutants)
- **Verification:** V1: C-06 Confirmed (High, latent); C-13 Confirmed (Medium, bites PLN data).

### Q-007 — FX: live rate fetch can never succeed in production, four converter copies apply five different missing-rate policies, and page renders do network I/O
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** A/C/F/G / `duplicate-logic` (also `silent-fallback`)
- **Track aliases and calibration:** G-01 Critical -> High (verifier); A-06 High; C-02 High; C-17 Medium; F-06 High
- **Calibration note:** G-01 orig Critical: downgraded (V2) because there are no non-PLN accounts.
- **Priority flag:** Latent until the first non-PLN account or currency exists
- **Location(s):** `config.py:70` (`fx_api_url` never read); `services/fx.py:55,96-164`; clients without `base_url` at `web/today_data.py:124`, `web/routers/forecast.py:49`, `services/forecast.py:950`; converters `services/forecast.py:204-240`, `web/today_data.py:90-135`, `services/budget.py:55-116`, `web/routers/ledger.py:273-283`; uncaught `FxUnavailableError` at `web/routers/forecast.py:48` and `plan.py` forecast tab; `tests/unit/services/test_fx.py:20-24` (client built with `base_url`)
- **Description:** (G-01) Production clients are `httpx.Client(timeout=5.0)` with no `base_url`; `_fetch_remote` calls a relative URL, `UnsupportedProtocol` (an `httpx.HTTPError`) is swallowed, the code falls back to cache and then rate 1. (A-06/C-02) Arithmetic copies agree (273 samples) but policy does not: budget degrades to the native amount, today uses rate 1 and counts it as base in fortune, ledger returns `None`, forecast raises (HTTP 500). (C-17) ADR-0095 section 2 says renders never touch the network, yet `get_rate` is called on render with a 5 s timeout per currency. (F-06) The fx mutants survive because tests give the client a `base_url` production never sets.
- **Evidence:** `tracks/G-drift.md` G-01; `tracks/A-duplication.md` A-06 (`repro/A/output/inv_10*`); `tracks/C-correctness.md` C-02, C-17; V2 repro `repro/verify/V2/g01_fx_relative_url.py` + `.out` (UnsupportedProtocol, zero requests leave the client; works with a `base_url`).
- **Impact:** Latent: prod has only PLN accounts. The day the first non-PLN account exists, every FX path is wrong (rate 1) or 500s, and the same missing rate shows three different numbers.
- **Mitigation:** One `FxConverter` in `services/fx.py`, built per request by `fx.converter_for(conn, settings, today)`: cache-only (`convert_cached`), client factory `httpx.Client(base_url=settings.fx_api_url, ...)` used by the background refresh (startup and daily, next to the retention loop), returns a typed `Converted | Unconverted(ccy)` (never `Decimal(1)`), carries the rate date so views can flag stale or missing rates. Delete `forecast._convert_native_to_base`, `today_data._convert_minor`, the ledger nested `convert` and the `budget` degrade paths. Tests: integration test that fails if a client without `base_url` reaches `_fetch_remote`, `fx_api_url` read, exact `(rate, date)` of the stale fallback, `convert_cached` hit vs miss. **All FX findings (Q-008, Q-009, Q-010 and the ledger/forecast converters) use this converter.**
- **Effort:** M
- **Related:** ADR-0006, ADR-0095; Q-008, Q-009, Q-010, Q-029; operator Q: prod non-PLN accounts (OQ-1), `fx.convert` dead code (OQ-13), fx_rates CHECK and provider validation (OQ-17)
- **Verification:** V1: A-06, C-02, C-17 Confirmed. V2: G-01 Confirmed (own repro), Critical to High. V3: F-06 Confirmed (mutants on `_fetch_remote` timeout and `convert_cached` fallback date survive).

### Q-008 — Analytics and forecast 'spent' add native minor units across currencies against base-currency budgets
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** A / `duplicate-logic`
- **Track aliases and calibration:** A-02 High; A-03 High
- **Priority flag:** Latent until the first non-PLN account or currency exists
- **Location(s):** `services/analytics.py:123-125,166-168,197-205,236-243` (`_spend_by_category`, `_twelve_month_averages`, `_income_vs_expense_monthly`, `_largest_items`); `services/forecast.py:322-342` (`_spent_so_far`, used at `:465,:699`), `:587` (`primary_account_id = min(a.id ...)` receives a base-currency overlay amount)
- **Description:** T-FIX6 fixed `budget.py` but not its siblings. ADR-0006 and ADR-0095 section 6 require base-currency aggregates; analytics has no FX at all and `_spent_so_far` sums raw `r.amount` next to converted `committed`. The forecast overlay events are also debited to the lowest-id account in that account's native currency.
- **Evidence:** `tracks/A-duplication.md` A-02, A-03; `repro/A/output/inv_01*` (budget spent 85717 = ledger 85717, analytics 52717), `inv_03a*` (budget spent 43000 vs forecast 10000).
- **Impact:** Wrong analytics and forecast spend/residual for any foreign-currency expense; latent while the data is PLN-only.
- **Mitigation:** Inject `budget.base_txn_converter` (built from the Q-007 converter) into the four analytics functions and `_spent_so_far`, or better call one shared `aggregates.sum_by_category(txns, to_base)` (see Q-075); emit overlay events in base currency against a base pseudo-account row, not `min(id)`.
- **Effort:** S (spent) / M (overlay account)
- **Related:** Q-007, Q-009, Q-013; ADR-0042, ADR-0095
- **Verification:** V1: A-02 Confirmed (code), A-03 Confirmed for spent, overlay-on-min(id) Probable; both High (latent).

### Q-009 — Net worth is computed twice; the figure labelled 'all accounts' silently drops non-base accounts while forecast starts from the converted figure
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** A / `duplicate-logic`
- **Track aliases and calibration:** A-07 High
- **Priority flag:** Latent until the first non-PLN account or currency exists
- **Location(s):** `services/fortune.py:30-51` (base-currency accounts only), `web/today_data.py:105-143` (`collect_account_rows` converts; `fortune_base` unused by any template), `web/routers/today.py:55-58,81`, `web/templates/today/index.html:87-93`, `web/templates/accounts/index.html:23-26,39`, `web/routers/accounts.py:110-118`
- **Description:** The Today card says 'Net worth . all accounts' and the Accounts hero says 'No FX conversions needed today' but both use `compute_fortune`, which ignores non-base accounts; `today_data.fortune_base` converts them and forecast day 0 uses it.
- **Evidence:** `tracks/A-duplication.md` A-07; `repro/A/output/inv_02*` (+1000 EUR: `fortune.net_base` 3443969, `today_data.fortune_base` and forecast day 0 3873969).
- **Impact:** Headline net worth silently excludes every non-base account and disagrees with the forecast start. Latent (PLN only).
- **Mitigation:** `services/fortune.compute_fortune(..., converter)` returns per-currency and converted totals using the Q-007 converter; render the converted net worth, delete the fortune math in `collect_account_rows` and the unused template variable; amend ADR-0024/0089 text.
- **Effort:** M
- **Related:** Q-007; ADR-0006, ADR-0024, ADR-0089
- **Verification:** V1: Confirmed (code), High (latent).

### Q-010 — Recurring and Planned strips on the ledger sum raw amounts across currencies and, for planned, across income and expense, under a hard-coded 'PLN'
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** A/B/C/E / `duplicate-logic`
- **Track aliases and calibration:** B-01 Critical -> High (verifier); C-04 High; E-04 High; A-16 Medium
- **Calibration note:** B-01 orig Critical: downgraded (V1). The direction-mixing half bites on current PLN data.
- **Priority flag:** **Biting on current PLN data**
- **Location(s):** `web/routers/ledger.py:343-376` (`_recurring_summary`), `:409-414` (`planned_total_minor`); `web/templates/ledger/index.html:93-114` (literal `PLN`, `/ 100.0`); `services/recurring_formula.py:191-243` (formula sources sum rules in different currencies)
- **Description:** Router aggregates add `effective_amount_minor` of each rule in its own account currency (floor division by cadence), ignore the direction of planned rows (amounts are stored positive for income too) and print the total as PLN. The actual-view `day_net` converts, so the three views disagree. Also a fourth copy of 'monthly equivalent of a rule'.
- **Evidence:** `tracks/B-layering.md` B-01; `tracks/C-correctness.md` C-04; `tracks/E-frontend.md` E-04 (`repro/E/fx_probe.out.json`: strip unchanged after flipping the main rule account to EUR); `repro/B/b_router_logic.out`; `tracks/A-duplication.md` A-16.
- **Impact:** Planned strip is wrong on PLN data as soon as an income row is planned and the direction filter is off (V1); the recurring strip is wrong by the FX factor with a second currency. Informational strips, not totals used elsewhere.
- **Mitigation:** Move both strips (and the formula-source sums) into `services/ledger_totals.py:recurring_monthly_totals` / `planned_totals` using the Q-007 converter, signed by direction (`domain` sign helper, Q-036), HALF_EVEN via the shared rounding helper, return `base_ccy`; template prints `settings.base_currency` through the `money` filter. Test: sum equals sum of converted parts.
- **Effort:** S-M
- **Related:** Q-007, Q-036; ADR-0006
- **Verification:** V1: B-01 and C-04 Confirmed (B-01 Critical to High). V2: E-04 Confirmed, High.

### Q-011 — Money rendered with hard-coded `/ 100.0` and two decimals in 40+ templates, charts and services: zero-decimal currencies show 100x off
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** A/C/E / `money-arith`
- **Track aliases and calibration:** A-01 Critical (cond.) -> High (verifier); C-03 High; E-03 High
- **Calibration note:** A-01 orig Critical (conditional): operator confirms no JPY/KRW/ISK account in prod, so High (latent).
- **Priority flag:** Latent until the first non-PLN account or currency exists
- **Location(s):** `web/templates/today/index.html:32,42,52-55,89-93,100`, `today/_afford_preview.html:3,5`, `today/_upcoming.html:43`, `ledger/_table.html:69`, `ledger/index.html:98-114`, `plan/_forecast_tab.html:85-88`, `plan/_analytics_bundle.html:17-110`, `plan/_year_tab.html:47-75`, `plan/_budget_tab.html:6-57`, `accounts/index.html:23-39`, `partials/budget/_override_form.html:56`, `partials/recurring/_formula_preview.html:4`, `partials/recurring/_promote_inline_row.html:38` (prefills an editable amount); Python `services/forecast.py:956`, `web/routers/plan.py:36,48-56`, `web/routers/forecast.py:31,57`, `web/routers/today.py:126,141` (`round(major * 100)` on input)
- **Description:** T-JPY introduced `money_num` (exponent-aware) but only some templates use it. About 51 sites format `"{:,.Nf}".format(x / 100.0)`, ignoring `currency_decimals()`. A JPY account with 12345 renders 123.45 on /today and 12,345 on /accounts; a JPY promote would prefill 1/100th and persist it if submitted.
- **Evidence:** `tracks/A-duplication.md` A-01 (`repro/A/output/inv_06*`); `tracks/C-correctness.md` C-03 (`repro/C/repro_jpy_display.py`); `tracks/E-frontend.md` E-03 (`repro/E/money_format_repro.py`: PLN equal, JPY 1,234.56 vs 123,456).
- **Impact:** Wrong balance on the landing page for any 0-decimal account, and every base-currency figure wrong if `base_currency` were ever non-2-decimal. Latent: prod has no JPY/KRW/ISK account.
- **Mitigation:** Route every amount through `money` / `money_num(currency)` (templates) and one `domain/money.py:minor_to_major(amount, currency)` (charts, services); replace `_MINOR_UNITS_PER_MAJOR`, `forecast.py:956` and the afford parser with `parse_amount_str` + `to_minor_units(base)`. Compute display strings in the view model. Guard: architecture test rejecting `/ 100` and `* 100` in `web/` and `services/`. The Sourdough redesign (ADR-0107) replaces the templates, so put the rule in the redesign brief; the Python half survives.
- **Effort:** M
- **Related:** Q-029 (exponent table), Q-039, ADR-0006, ADR-0008, ADR-0107, T-JPY
- **Verification:** V1: A-01 Confirmed (Critical to High latent), C-03 Confirmed; V2: E-03 Confirmed.

### Q-012 — Ungated, all-branch GitHub environments hold prod-grade secrets (prod age identity, prod replica read key, prod app key, Tailscale OAuth) and can mint a tailnet identity that reaches prod sshd
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** H1 / `ci-trust-boundary`
- **Track aliases and calibration:** H1-01 High; H1-06 Medium; H4-03 Medium (live confirmation)
- **Calibration note:** H1-06 (orig Medium) merged: same ungated environments, one fix. H4-03 (track Medium, design-level) merged as live confirmation; the merged record keeps High.
- **Location(s):** `.github/workflows/terraform.yml:41-56,204-215`, `drill.yml:60-107,207-218`, `restore-drill.yml`, `replace-rehearsal.yml`, `scripts/ci/tf_env.py:60-79`; live config `repro/H1/gh_api/environments.json` and the three per-environment name listings in the same directory; `docs/plans/v3/runbooks/tailscale-acl.hujson` (`tag:ci` to `tag:prod:22`); `terraform/main.tf` (re-check, see metadata note)
- **Description:** Environments `prod-plan`, `drill`, `drill-plan`, `drill-teardown` have no reviewers and no deployment-branch policy, so a job from any branch that names one receives its secrets, and workflow YAML and local actions come from the branch. Read key plus age identity decrypt the whole prod replica. The same Tailscale OAuth client in those environments can join the tailnet as `tag:ci`, which the ACL lets reach prod port 22 (leftover of the SSH deploy path ADR-0111 removed).
- **Evidence:** `tracks/H1-ci-supply-chain.md` H1-01, H1-06; `repro/H1/workflow_audit.out` sections 4-5; `tracks/H4-infra.md` H4-03 (live: the explore drill host carries `restore-source.env` with the prod replica read key and the age identity, mode 0600 root, and the age key is mounted into three litestream containers; `operator` has passwordless sudo and the docker group, so operator equals root; presence and permissions only, key values not read or used); V2 verified the environment settings from the committed gh_api JSON.
- **Impact:** A stolen write-scoped token, a compromised dev machine or a prompt-injected agent with push rights can read and decrypt every user's financial data and delete or poison the prod replica without any approval. Fork PRs cannot (no secrets for forks). Precondition: same-repo write access (ADR-0121 threat model: single-owner repo).
- **Mitigation:** Split by data sensitivity: new `prod-restore-read` environment (prod restore-reader key plus prod age identity only) with required reviewers and `main`-only branch policy, used only by `restore-drill`; give `prod-plan` and every drill environment a synthetic age identity and the drill app key, and plan with placeholder values; remove the Tailscale OAuth client from `prod-plan` and delete the `tag:ci` to `tag:prod:22` ACL rule. Rotate the secrets after the change.
- **Alternatives:** Keep the secrets but require reviewers and a `main`-only policy on `drill`/`drill-teardown` (cheap, but the operator approves their own gates and teardown must stay ungated).
- **Effort:** M
- **Related:** ADR-0091, 0094, 0099, 0100, 0101, 0104, 0105, 0121, 0111; Q-041, Q-042
- **Verification:** V2: H1-01 Confirmed (High). H1-06 not sampled (Probable; live ACL not readable). H4: H4-03 Confirmed live on drill 44609305750 (presence and permissions); validity of the keys against prod deliberately not tested (OQ-31). Step 0 showed the drill DB itself held no prod data. The drill host is a second place (beside the CI environments) where prod-restore capability sits, so the fix also covers it: do not render `restore-source.env` or the prod age identity into explore drills, scope them to the `restore-drill` run only.

### Q-013 — None of Track A's 16 differential invariants exists as a test; 8 of the 10 failing ones will regress or stay open unguarded
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** F / `missing-invariant-test`
- **Track aliases and calibration:** F-14 High
- **Location(s):** `tests/integration/invariants/` (absent); seed in `repro/A/harness.py`; table in `tracks/F-tests.md` section for F-14
- **Description:** Cross-implementation agreement (budget spent == ledger total == analytics == forecast, in base currency, per category and month) is only checked by the audit's own scripts.
- **Evidence:** `tracks/F-tests.md` F-14; `tracks/A-duplication.md` section 4 (inv_01 to inv_10).
- **Impact:** The duplicate-logic findings (Q-002, Q-003, Q-007, Q-008, Q-009, Q-010) can recur silently after remediation.
- **Mitigation:** Add `tests/integration/invariants/` with one file per Track A script, reusing the multi-currency seed from `repro/A/harness.py` as a conftest fixture (PLN + EUR + JPY, one cached rate, one archived category, one linked planned row). Land each test as `xfail(strict=True)` citing its Q-id and flip it when the finding is fixed.
- **Effort:** L
- **Related:** Q-002, Q-003, Q-007, Q-008, Q-009, Q-010; Phase 4 duplicate-logic control
- **Verification:** V3: Confirmed (High); only `test_linked_dedup.py` is a cross-implementation test.

### Q-014 — The coverage config excludes every line containing `...`, silently removing about 790 statements and 16 whole functions from the report
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** F / `config-drift`
- **Track aliases and calibration:** F-12 High
- **Location(s):** `pyproject.toml:194` (`"\\.\\.\\."` in `[tool.coverage.report] exclude_lines`); affected e.g. `services/balance.py:42`, `services/budget.py:603` (`yearly_grid`), `services/password_change.py:89`, `services/rate_limit.py:149-196`, `services/accounts.py:104`, `services/forecast.py` `monthly_projection`
- **Description:** The pattern intended for `...` stub bodies matches any line with an ellipsis (including f-strings and slices), so the 90 percent gate measures a reduced denominator.
- **Evidence:** `tracks/F-tests.md` F-12; `repro/F/coverage_without_ellipsis_exclusion.txt`.
- **Impact:** The coverage gate is unreliable: money functions look covered or are invisible. The honest figure may drop near 94.5 percent (still above the gate).
- **Mitigation:** Delete the line or replace it with the anchored `"^\\s*\\.\\.\\.$"` in `pyproject.toml` `exclude_lines`; add tests for the 49 newly missed statements (listed in the repro file).
- **Effort:** S (config) + M (tests)
- **Related:** ADR-0108, Q-021
- **Verification:** V3: Confirmed (High); about 790 statements hidden (7741 vs 8531); coverage 94.70 to 94.49 percent, so the gate still passes: the harm is hidden gaps.

### Q-015 — Fixtures never contain a second user or a deleted/inactive row, so 40 money-path mutants (`user_id` or `conn` as `None`, `include_deleted`, `active_only`) survive
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** F / `missing-invariant-test`
- **Track aliases and calibration:** F-09 High; F-10 High
- **Priority flag:** **Fix before a second user is onboarded**
- **Location(s):** `services/forecast.py:277`, `services/budget.py:308,451,501,548`, `services/recurring.py:496`, `services/balance.py:102,133` (rows 5, 7, 22, 30, 43, 51, 60, 78, 101, 104, 105, 126, 138, 220 of `baseline/mutmut-real-gaps.md`); `include_deleted` / `active_only` rows listed under F-10; `tests/unit/services/conftest.py`
- **Description:** A scoping detector is missing: no unit fixture has a second user with overlapping ids/dates, and none has a soft-deleted category, archived account or inactive rule, so the soft-delete and scoping choices of the money services are never asserted.
- **Evidence:** `tracks/F-tests.md` F-09, F-10; `baseline/mutmut-real-gaps.md`.
- **Impact:** A scoping regression (the class of Q-001) or a soft-delete policy change in a money service would not fail any unit test. Matters before the second user is onboarded.
- **Mitigation:** Add a two-user fixture and a `world_with_tombstones` fixture to `tests/unit/services/conftest.py`; one parametrised test per money service function (balance, budget, forecast, analytics, recurring, planned, upcoming, today) asserting user 2's rows never appear and the intended tombstone inclusion (decide policy once, Q-030).
- **Effort:** M
- **Related:** ADR-0061, ADR-0019; Q-001, Q-030
- **Verification:** V3: F-10 Confirmed; F-09 Probable (stays High): the `user_id=None` pattern reproduced in `promote_recurring`, four other None-user mutants were killed, so the '14 rows' claim is only partly reproduced.

### Q-016 — `recurring_formula` (71 surviving mutants): rounding mode, source-rule lookup and validation unasserted
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** F / `weak-assertion`
- **Track aliases and calibration:** F-02 High
- **Location(s):** `services/recurring_formula.py` (rows 234-304 of `baseline/mutmut-real-gaps.md`; `_apply_coefficient` at `:135` `ROUND_HALF_UP` replaced by `None` survives; `validate_formula_sources` 17, `_source_rule_month_value` 15)
- **Description:** No test pins the HALF_UP tie behaviour, two-user isolation of formula sources, inactive source rules or the preview/validation outputs.
- **Evidence:** `tracks/F-tests.md` F-02.
- **Impact:** Formula-derived recurring amounts can change rounding or scope unnoticed.
- **Mitigation:** In `tests/unit/services/test_recurring_formula.py`: HALF_UP tie cases (12.5 percent of 100 minor, odd amounts), a two-user same-name fixture, a category with two items and one inactive source rule, exact `preview` and `parse_percent_to_bps` outputs.
- **Effort:** M
- **Related:** Q-002 (A-17 override sources), Q-015, Q-028
- **Verification:** V3: Confirmed (rounding mutants survive).

### Q-017 — `forecast` (102 surviving mutants): the largest survivor cluster; horizon boundaries, skipped items and FX arguments unasserted
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** F / `weak-assertion`
- **Track aliases and calibration:** F-03 High
- **Location(s):** `services/forecast.py` rows 64-165 of the real-gaps list (`_committed_future_for_category` 16, `forecast_monthly` 13, `_planned_budget_per_month` 12, `forecast` 11, `_month_flow_sums` 9, `_collect_events` 8 incl. `user_id=None`)
- **Description:** Boundary days, override-skipped items, signed legs per direction and the converted-amount/rate-date case are not asserted; the same module hosts Q-002 and Q-008.
- **Evidence:** `tracks/F-tests.md` F-03.
- **Impact:** Forecast regressions (including the Q-002 double count) are not caught by unit tests.
- **Mitigation:** In `tests/unit/services/test_forecast.py`: horizon-end-day case (item on the last day and one day later), skipped-by-override item followed by a valid one, income/expense/transit legs on one day with the exact day balance, and a two-currency case asserting converted amount and rate date; use `test_linked_dedup.py` as the template.
- **Effort:** L
- **Related:** Q-002, Q-008, Q-015
- **Verification:** V3: Confirmed (boundary mutants survive, structural ones are killed).

### Q-018 — `budget` (53 surviving mutants): fiscal-month anchoring, committed window, mean and FX converters unasserted
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** F / `weak-assertion`
- **Track aliases and calibration:** F-04 High
- **Location(s):** `services/budget.py` rows 11-63 (`month_summary` 20, `_committed_by_category` 8 incl. `end + 1 day` and `rule_start > inclusive_end`, `_resolve_period_start`, `base_amount_converter`, `base_txn_converter`)
- **Description:** No test pins the committed window ends, the anchor day, empty/one-item means or the converter's missing-account policy.
- **Evidence:** `tracks/F-tests.md` F-04.
- **Impact:** Period-window regressions (Q-003) and converter policy drift are invisible to unit tests.
- **Mitigation:** In `tests/unit/services/test_budget.py` / `test_budget_fx.py`: `_month_range` and fiscal start for the first of the month and the anchor day; committed item on the last day and the day after; empty and one-item `_mean_minor`; account missing from the converter map (assert the Q-007 policy value); transaction exactly on `date_from`.
- **Effort:** M
- **Related:** Q-003, Q-007
- **Verification:** V3: Confirmed (`_month_range` first-day mutant survives).

### Q-019 — `recurring` (50 surviving mutants): `promote_recurring` audit attribution, override ordering, boundary days
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** F / `weak-assertion`
- **Track aliases and calibration:** F-05 High
- **Location(s):** `services/recurring.py` rows 184-233 (`promote_recurring` 10 incl. `user_id=None` in `write_audit` at `:488-496`, `generate_occurrences` boundary values at `:124,134`, `skip_and_advance`, `batch_promote_due`)
- **Description:** The audit row written by promotion is never read back and the cut-off day of `batch_promote_due` is not parametrised.
- **Evidence:** `tracks/F-tests.md` F-05.
- **Impact:** Audit attribution (ADR-0019) and promotion boundaries can break silently.
- **Mitigation:** In `tests/unit/services/test_recurring.py`: read the `audit_log` row after `promote_recurring` (helper `audit_rows` exists in `tests/integration/auth/conftest.py:41`) and assert user, entity, operation, prev/new JSON; parametrise `batch_promote_due` over the cut-off day, one day before and after; skipped rule followed by a valid one.
- **Effort:** M
- **Related:** ADR-0019; Q-006, Q-015
- **Verification:** V3: Confirmed (audit `user_id=None` and cut-off day mutants survive).

### Q-020 — `balance` (10 surviving mutants) and the untested `sparkline_points` / `balance_series` / `yearly_grid`: include-deleted choice, account filter and series are unasserted
- **Severity / Confidence:** High / Confirmed
- **Track / root cause:** F / `weak-assertion`
- **Track aliases and calibration:** F-08 High; F-27 Medium
- **Location(s):** `services/balance.py:69,81,98,102,129,133,147,156,158` and `:166-217` (`sparkline_points`, `balance_series`); `services/budget.py:603` (`yearly_grid`, 60 percent killed); `tests/integration/web/test_accounts.py:229-244` (skipped v1 test)
- **Description:** Two accounts with transactions, a soft-deleted category/account referenced by a transaction and the pure sparkline function have no unit test; F-27's tests only existed in the skipped v1 card tests.
- **Evidence:** `tracks/F-tests.md` F-08, F-27.
- **Impact:** Balance derivation (the base of fortune, forecast and net worth) can change behaviour unnoticed.
- **Mitigation:** In `tests/unit/services/test_balance.py`: two accounts, one transaction each (balances and `AccountStats.account_id`/`base_balance`); a soft-deleted category and account referenced by an existing transaction (the policy chosen in Q-030, equal to `account_planned` and forecast); `sparkline_points([1,3,2])`, flat, fewer than two points; `balance_series(days=3, today=...)`; `yearly_grid` parametrised over default/recurring/one-off tiers against `resolve_budget`.
- **Effort:** S-M
- **Related:** Q-030, Q-003
- **Verification:** V3: F-08 Confirmed (include-deleted and account-filter mutants survive); F-27 Confirmed (sample).

### Q-021 — The Plan page (non-current months, Year tab, Forecast tab) and `forecast.monthly_projection` are executed by no coverage-measured test
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** F / `missing-invariant-test`
- **Track aliases and calibration:** F-13 High
- **Location(s):** `web/routers/plan.py:87-94,126-133,145-171,180-193,195-222`; `services/forecast.py:932-975` (`monthly_projection`); `tests/integration/web/test_forecast.py:92`, `test_plan_analytics.py:33` (fetch only)
- **Description:** The router branches that re-implement the period for other months (Q-003) and the only caller of `monthly_projection` are never run by a measured test.
- **Evidence:** `tracks/F-tests.md` F-13 (coverage and caller search).
- **Impact:** A money page whose logic was found wrong by review (anchor day capped at 28, committed zeroed) has no regression net.
- **Mitigation:** New `tests/integration/web/test_plan.py`: GET `/plan?tab=forecast` on a seeded world (series length, first/last month label, one end balance), `/plan?month=...` for a past and a future month (committed zero, period bar dates), `/plan?tab=year&year=...`; unit test for `monthly_projection` with a mock converter. Write before Q-003's refactor.
- **Effort:** M
- **Related:** Q-003, Q-014
- **Verification:** V3: Confirmed, High to Medium (untested read-only view, not a proven wrong number).

### Q-022 — `format_money` renders zero as `-0.00 PLN` without any test failing (and the zero/negative sign decision is unasserted)
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** F / `weak-assertion`
- **Track aliases and calibration:** F-01 High
- **Location(s):** `domain/money.py:246-252` (mutant `value <= 0`); `tests/unit/domain/test_money.py` has no zero case
- **Description:** Surviving mutant in a priority money area (row 175 of the Mutmut real-gaps list); the docstring promises 'Zero renders without a sign'.
- **Evidence:** `tracks/F-tests.md` F-01; `baseline/mutmut-real-gaps.md` row 175.
- **Impact:** A sign regression on zero amounts would pass the suite.
- **Mitigation:** Add `test_format_money_zero` parametrised over PLN and JPY (`"0.00 PLN"`, `"0 JPY"`) and `format_money(-1, "JPY")`.
- **Effort:** S
- **Related:** ADR-0008; Q-011, Q-029
- **Verification:** V3: Confirmed as a test gap, High to Medium (production code is correct; display-only module not on the priority list).

### Q-023 — Unvalidated input reaches the 500 handler: seven divergent amount parsers, unguarded year/month/id parameters, oversized magnitudes and pre-auth parser failures
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** A/C/D/H3 / `duplicate-logic`
- **Track aliases and calibration:** A-08 High -> Medium (verifier); C-10 Medium; A-19 Low; D-02 Medium -> Low (verifier); H3-03 Low
- **Calibration note:** Individual severities: A-08 Medium (V1), C-10 Medium, A-19 Low, D-02 Low (V2), H3-03 Low; merged record keeps the highest.
- **Location(s):** `domain/money.py:198-231` (canonical `parse_amount_str`, used only by `web/routers/transactions.py:139,228`; accepts `1e3`, `1e30`, `_`, non-ASCII digits; `quantize` overflow on `1e400`); copies `web/routers/planned.py:209-216`, `accounts.py:171-182,203-206,466-481,474-477`, `budget.py:79-86,251-254,316-324,337-340,402-424`, `recurring.py:107-125,232-239,846-851,1043-1050`, `today.py:126-141`; `_parse_date`/`_parse_int` copies in `transactions.py:55,64`, `planned.py:33`, `recurring.py:40,49`, `ledger.py:44,53`; plain-`int` path ids on 43 routes; pre-auth `web/middleware/csrf.py:155-181`
- **Description:** Only the canonical parser normalises commas, caps fraction digits and rejects non-finite values; the others use bare `Decimal(...)` so `NaN`/`Infinity`/`1e400` crash with `InvalidOperation` (500) and 12.345 is silently rounded. `/budget?year=abc`, `year=99999`, huge ids and magnitudes above int64 end in 500. Pre-auth: non-ASCII CSRF token/header, multipart without boundary, more than 1000 form fields reach the catch-all 500.
- **Evidence:** `tracks/A-duplication.md` A-08 (`repro/A/output/inv_05*`); `tracks/C-correctness.md` C-10; `tracks/D-security.md` D-02; `tracks/H3-auth.md` H3-03 (`repro/H3/h3_csrf_preauth_output.txt` C4); V1 repros `v_c10`, `v_money`; V2 repro `repro/verify/V2/d02_overflow.py`.
- **Impact:** Authenticated users (and, for H3-03, anonymous callers) can produce 500s and error-level log noise; inconsistent behaviour per form; JPY afford preview wrong. No data corruption.
- **Mitigation:** Make `domain/money.py:parse_amount_str` the only parser (reject exponents, `NaN`/`Infinity`, non-ASCII digits, magnitude above a named `MAX_MINOR`, catch `InvalidOperation`); new `web/params.py` with shared `parse_date`, `parse_year_month`, and bounded `Annotated` types (`RecordId`, `Month`, `Year`, `PageNo`) used by every route; in `csrf.py` wrap the token read in `try/except (HTTPException, MultiPartException)` and `compare_digest` on bytes. One test loops over `app.routes` with oversized ids and asserts no 5xx.
- **Effort:** M
- **Related:** Q-011, Q-035, Q-064; ADR-0008
- **Verification:** V1: A-08, C-10 Confirmed (A-08 High to Medium). V2: D-02 Confirmed (Medium to Low). A-19, H3-03 not sampled. Merged severity Medium.

### Q-024 — Batch undo endpoints bypass the repository layer, replay 'the latest audit row' of any operation, do not restore all state and write no audit entry
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** B/C/H2 / `repo-bypass`
- **Track aliases and calibration:** B-03 High -> Medium (verifier); C-16 Medium; H2-03 Medium; B-11 Low
- **Location(s):** `web/routers/planned.py:112-181` (raw SELECT at `140`, raw UPDATE at `155`), `web/routers/recurring.py:470-545` (raw SELECT at `501`, audit-free `set_next_due` at `522`), `repositories/audit.py:30,44` (no scoping parameter)
- **Description:** Undo picks `prev_json` from the newest `audit_log` row of the entity (no operation filter on the recurring variant, no `user_id` on the read), not from the batch. An edit between batch and Undo makes it restore the post-promote state; the planned restore is a raw UPDATE so no audit row is written (ADR-0019/0022). Cross-user replay was tried and is clean (writes are `user_id` scoped).
- **Evidence:** `tracks/B-layering.md` B-03, B-11 (`repro/B/b_undo_replay.out`); `tracks/H2-isolation.md` H2-03 (`repro/H2/h2_02_undo_chain.py`); `tracks/C-correctness.md` C-16.
- **Impact:** Own-data wrong state behind an 'Undone' toast: a recurring rule one period ahead (a missed bill vanishes from forecasts) or inactive, an orphaned promotion link. Happy path (immediate undo) works.
- **Mitigation:** Delete the SQL from both routers. `services/planned.py:undo_batch` and `services/recurring.py:undo_batch` run in one `db_transaction`: soft-delete the posted transactions after verifying ownership, unstamp planned rows by compare-and-set (`WHERE promoted_to_txn_id = :txn_id`) through the audited repository helper, restore rules via `update_rule` from the pre-batch state carried in the undo payload (or a small `promotion_batches` table keyed by batch id and `user_id`), only if the entity is unchanged since (`updated_at`). Add `user_id` to `repositories/audit.list_entries` and rename `recent` to `recent_all_users`.
- **Alternatives:** Keep audit replay but require the newest audit row to carry the batch marker and refuse otherwise (cheaper, less robust).
- **Effort:** M
- **Related:** ADR-0019, ADR-0022; Q-049, Q-045; operator Q: undo an audited action or an erase? (OQ-11)
- **Verification:** V1: B-03 Confirmed (High to Medium), C-16 Probable. V3: H2-03 Confirmed. B-11 not sampled.

### Q-025 — Compound mutations and their guard reads are not inside one transaction: double-submit can promote twice, concurrent writers fail with 'database is locked'
- **Severity / Confidence:** Medium / Probable
- **Track / root cause:** B/C / `txn-boundary`
- **Track aliases and calibration:** C-09 Medium; B-07 Medium
- **Priority flag:** **Fix before a second user is onboarded**
- **Location(s):** `repositories/_shared.py:113-143` (deferred `BEGIN`); `services/planned.py:149-193,221-224`; `services/recurring.py:356-500`; `services/reconciliation.py:62-120`; `web/routers/accounts.py:490-500`; no unique index (`migrations/0012_multi_user.sql:219`)
- **Description:** `promote_*` reads the guard (`promoted_to_txn_id is not None`, rule and override) before `db_transaction` opens and `stamp_promotion` has no `IS NULL` guard, so two near-simultaneous submits can both post a transaction; reconcile then snapshot are two commits; a deferred `BEGIN` makes the second writer fail instead of waiting.
- **Evidence:** `tracks/C-correctness.md` C-09 (`repro/C/repro_concurrency.py`); `tracks/B-layering.md` B-07.
- **Impact:** Duplicate promoted transactions on a double click, 500s under write contention (more likely with more users). Not reproduced under real concurrency.
- **Mitigation:** `BEGIN IMMEDIATE` in `repositories/_shared.transaction` (waits on `busy_timeout`); move the guard reads inside; compare-and-set `UPDATE planned_transactions SET promoted_to_txn_id=? WHERE id=? AND user_id=? AND promoted_to_txn_id IS NULL` (check `rowcount`, raise `AlreadyPromotedError`); partial unique indexes on `transactions(promoted_from_planned_id)` and `(promoted_from_recurring_rule_id, promoted_from_recurring_date)` where `deleted_at IS NULL`; `reconcile_and_snapshot` service function.
- **Effort:** M
- **Related:** ADR-0019; Q-024, Q-034; new root-cause class txn-boundary
- **Verification:** V1: C-09 Probable (no concurrency repro), Medium. B-07 not sampled.

### Q-026 — Soft-deleting an account drops its balance from fortune and leaves live recurring rules and planned rows pointing at it (promotion still posts to it)
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** C / `scoping-gap`
- **Track aliases and calibration:** C-05 High -> Medium (verifier)
- **Location(s):** `web/routers/accounts.py:348-354`; `repositories/accounts.py:138-155`; `repositories/_shared.py:199-200`; `services/_promotion.py:41-60`; `services/recurring.py:356-500`; `web/today_data.py:112-139`
- **Description:** The delete route has no dependency check; a live rule on a deleted account keeps feeding forecasts and can be promoted, and the account's balance silently leaves net worth.
- **Evidence:** `tracks/C-correctness.md` C-05 (`repro/C/repro_deleted_refs.py`); V1 repro `v_c05` (promote on the deleted account returns 200).
- **Impact:** Orphaned rules and an unexpected drop in net worth; no crash.
- **Mitigation:** New `services/accounts.archive_account()` that refuses (typed error, 409 with a message) when the balance is not zero or live rules/planned rows reference it, or deactivates them in the same transaction; liveness checks for account and category in `validate_promotion` and the transaction create service.
- **Effort:** M
- **Related:** ADR-0019; Q-004
- **Verification:** V1: Confirmed (repro v_c05), High to Medium (intentional delete).

### Q-027 — Authentication abuse controls: the real client IP is lost behind Docker NAT (every client is the gateway 172.18.0.1) so the per-IP login bucket is shared and `audit_log.ip` is useless, `--forwarded-allow-ips=*` trusts the header by name, throttled and failed logins write unbounded attacker text to the DB, and one user can lock out another
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** D/H2/H3 / `security-control`
- **Track aliases and calibration:** D-06 Medium; H3-01 Medium; H3-07 Low; H2-04 Low; H3-05 Low; H4-01 Medium
- **Calibration note:** H4 answered the open Caddy question: Caddy overwrites a forged `X-Forwarded-For`, so the header-rotation bypass (H3-01 R3, R5) is not exploitable through Caddy and that part drops to defence in depth. But H4-01 showed the real client IP never reaches the app (Caddy and the app see 172.18.0.1 for every tailnet client), so the per-IP login bucket is one shared bucket (any tailnet peer can lock the owner out of password login for an hour) and `audit_log.ip` never identifies the device. Net severity stays Medium, for a different reason.
- **Priority flag:** **Fix before a second user is onboarded**
- **Location(s):** `Dockerfile:104-108` (`--proxy-headers --forwarded-allow-ips=*`); `web/routers/auth.py:85-143,146-203` (`_client_ip`, `login_rate_limit`, `reauth_rate_limit`); `services/rate_limit.py:120-166` (`audit_throttled`); `services/auth.py:151-172`; `repositories/sessions.py:124-135`; `terraform/cloud-init/bootstrap.yaml.tpl:77` (fail2ban installed, no jail); requirements 6.7 line 346
- **Description:** Limits are per IP-and-email only; with a rotating header 30 wrong guesses on one account were never throttled (H3 R3) and a victim's bucket can be poisoned by sending the victim's address (R5). Every throttled attempt writes an audit row containing the full email (200 kB accepted). Same-IP users can burn each other's bucket (throttled attempts count), and a session-cookie holder can exhaust the owner's step-up bucket. H4 (live drill): Caddy overwrites forged `X-Forwarded-For`, `X-Real-IP` and `X-CSP-Nonce`, so the rotating-header bypass is not exploitable via Caddy; instead the source address seen by Caddy and the app is the Docker bridge gateway 172.18.0.1 for every client (likely a `MASQUERADE` rule on the `edge` bridge, rule not isolated, OQ-30), so the stored identity is `login_ip:3600s:ip=172.18.0.1` for everyone.
- **Evidence:** `tracks/D-security.md` D-06; `tracks/H3-auth.md` H3-01, H3-05, H3-07 (`repro/H3/h3_rate_limit_output.txt` R3-R8); `tracks/H2-isolation.md` H2-04 (`repro/H2/h2_07_login_lockout_and_audit_tail.py`); `tracks/H4-infra.md` H4-01 and section 3 (`repro/H4/h4_xff_probe.sh`, `out_xff_probe.txt`: `auth_rate_limit` rows keyed `ip=172.18.0.1` for both forged probes, `audit_log.ip=172.18.0.1`, Caddy log `client_ip` 172.18.0.1).
- **Impact:** Credential guessing bounded only by bcrypt cost and the 12-character minimum (behind Caddy the per-IP bucket now throttles all clients together rather than being bypassable); targeted lockout of a known user, and of the owner by any tailnet peer; no usable source IP in the audit trail; DB and replica growth from pre-auth requests.
- **Mitigation:** First fix the real-IP chain (H4-01): make the tailnet source address reach Caddy (host networking for Caddy, or avoid the `MASQUERADE` on the `edge` bridge via `iptables`/`--ip-masq` changes), set Caddy `trusted_proxies` explicitly, then pin `--forwarded-allow-ips` to Caddy's address instead of `*`, and add a drill smoke check asserting `audit_log.ip` is a `100.x` address. Then stop trusting the header by name: proxy overwrites `X-Forwarded-For` and `X-Real-IP` (verified live), `_client_ip` validates with `ipaddress.ip_address` and falls back to `request.client.host`. In `services/rate_limit.py`: per-email global bucket (30/h across IPs; stays necessary even with the IP chain fixed), do not count throttled attempts toward the window and reset the (IP, email) bucket on success, one `rate_limited` audit row per bucket per window, truncate stored email to 254, key the re-auth bucket on user plus session, Caddy `request_body max_size`. Either add the missing fail2ban jail or correct requirements 6.7 and ADR-0036 (Q-053).
- **Effort:** M
- **Related:** ADR-0072, ADR-0079, ADR-0036; Q-035, Q-062; OQ-25 (answered by H4), OQ-30
- **Verification:** D-06, H3-01, H3-05, H3-07 not sampled; H2-04 not verified (Low). H4-01 Confirmed by live repro on drill 44609305750; no independent re-verification (the drill is torn down; evidence is the recorded redacted output in `repro/H4/`).

### Q-028 — The recurring-rule save path skips the source-category validation that preview performs: foreign or nonexistent category ids and zero-amount formula rules are persisted
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** H2 / `missing-invariant-test`
- **Track aliases and calibration:** H2-02 Medium
- **Priority flag:** **Fix before a second user is onboarded**
- **Location(s):** `web/routers/recurring.py:181-230` (`_resolve_amount_inputs`, used by create `:268` and update `:632`); validation only in `services/recurring_formula.py:467-520` (`_invalid_source_ids`, called from `preview`)
- **Description:** Preview rejects unknown, archived or foreign category ids and non-positive results; create and update call only `build_term`, a cycle check and `compute_formula_amount`. Evaluation is `user_id` scoped, so a foreign id sums to 0 today (no leak), but the stored rule is a latent isolation hole and a zero-amount rule the UI calls invalid.
- **Evidence:** `tracks/H2-isolation.md` H2-02 (`repro/H2/h2_03_formula_foreign_sources.py`).
- **Impact:** No cross-user exposure today; becomes live if a shared or global category ever exists; zero-amount rules in the ledger.
- **Mitigation:** Move `_invalid_source_ids` to a shared service function and call it (with the positive-amount rule) in `_resolve_amount_inputs`; extend the two-user formula test to the create/update paths.
- **Effort:** S
- **Related:** ADR-0047, ADR-0056; Q-016, Q-015
- **Verification:** V3: Confirmed (bonus read of the code), Medium.

### Q-029 — Currency exponent table lists only JPY/KRW (and a few others): 21 accepted ISO codes are mis-scaled, including ISK which is FX-reachable
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** A/C / `money-arith`
- **Track aliases and calibration:** A-09 Medium; C-15 Medium
- **Priority flag:** Latent until the first non-PLN account or currency exists
- **Location(s):** `domain/money.py:14-23` (`_CURRENCY_DECIMALS`), `:26-195` (accepted list, `currency_decimals`); `services/accounts.py:197-200` (accepts any 3-letter code)
- **Description:** BIF CLP DJF GNF ISK KMF PYG RWF UGX VND VUV XAF XOF XPF are 0-decimal and BHD IQD JOD KWD LYD OMR TND are 3-decimal in ISO 4217, but default to 2; 3-decimal input like `1.234` is rejected and ISK 1000 stores 100000.
- **Evidence:** `tracks/A-duplication.md` A-09 (`repro/A/output/inv_06*` 6a); `tracks/C-correctness.md` C-15 (`repro/C/repro_reconcile_and_parse.py` P3); V1 repro `v_money`.
- **Impact:** Amounts entered, displayed or converted 100x or 10x off for those currencies; latent (PLN only).
- **Mitigation:** Generate the exponent table from ISO 4217 (all codes) next to `ISO_4217_CURRENCIES`; unit test in `tests/unit/domain/test_money.py` that every offered code has an explicit entry; reject accounts whose currency has no known exponent. Land together with Q-011.
- **Effort:** S
- **Related:** Q-011, Q-007; ADR-0006
- **Verification:** V1: C-15 Confirmed (Medium); A-09 Confirmed in code.

### Q-030 — Forecast and budget disagree on which categories and overdue items count: archived categories reserve budget in the daily overlay, overdue planned items are dropped from the forecast stream
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** A / `duplicate-logic`
- **Track aliases and calibration:** A-11 Medium; A-12 Medium
- **Location(s):** `services/forecast.py:581,447` (`directions_by_cat` built `include_deleted=True`), `:686`, `:254,262-283` (`event_start = today + 1`); `services/budget.py:475,605,279-310` (`start=None`)
- **Description:** An archived expense category with a default budget adds to the daily overlay but not to the monthly table or the Budget page; an overdue unpromoted 5000 planned expense is counted by budget (ADR-0105) and absent from the forecast stream. Intent unknown (operator question).
- **Evidence:** `tracks/A-duplication.md` A-11 (`repro/A/output/inv_09*`), A-12 (`inv_03c*`).
- **Impact:** Daily forecast series and monthly forecast table on the same page disagree; end balance ignores money the budget says is committed.
- **Mitigation:** Decide the policy once (operator, OQ-6/OQ-18), then `services/categories.py:expense_category_ids(conn, user, *, include_archived=False)` for all budget-driven paths and an explicit `include_overdue` parameter on the shared `pending_occurrences` (Q-002); forecast places overdue items on `today + 1`.
- **Effort:** S
- **Related:** ADR-0105; Q-002, Q-015
- **Verification:** not sampled by V1/V2.

### Q-031 — Two notions of 'today': display-timezone date (8-9 sites) vs host-clock `date.today()` (16-18 sites); time-dependent tests can fail at month end or in the Warsaw midnight window
- **Severity / Confidence:** Medium / Probable
- **Track / root cause:** A/C/F / `clock`
- **Track aliases and calibration:** A-13 Medium; C-08 Medium -> Low (verifier); F-21 Medium
- **Calibration note:** V1 rated C-08 Low alone. Kept Medium after merging A-13 and F-21 (27 sites, blocks deterministic tests); the operator may lower it to Low if the image has tzdata.
- **Location(s):** tz-aware: `web/routers/today.py:48,109,160`, `plan.py:76,272`, `budget.py:126,156,183`; host clock: `db/migrate.py:155`, `repositories/recurring.py:227`, `services/balance.py:210`, `services/budget.py:69`, `services/planned.py:86`, `web/routers/{accounts.py:46,budget.py:81,forecast.py:48,ledger.py:292,planned.py:80,recurring.py:338,353,435,580,694}`, `web/today_data.py:123`; `docker-compose.yml:45` and `terraform/cloud-init/compose/docker-compose.yml.tpl:31` (`TZ`), `Dockerfile` (no tzdata); tests `tests/integration/web/test_budget.py:561-565`; `baseline/clock-sites.txt`
- **Description:** ADR-0007 defines the display zone Europe/Warsaw. On a UTC host between 00:00 and 01:00/02:00 Warsaw `/today` and `/plan` say day N+1 while `/forecast`, `/budget` and the FX rate date say day N. Mitigated while `TZ=Europe/Warsaw` works in the image (V1: both compose files set it); a silent no-op if tzdata is missing (operator question). Tests using `datetime.now(UTC)` fail on the last day of a month.
- **Evidence:** `tracks/A-duplication.md` A-13 (`repro/A/output/inv_08*`); `tracks/C-correctness.md` C-08 (`repro/C/repro_clock.py`); `tracks/F-tests.md` F-21.
- **Impact:** Different 'today' on different pages for an hour a day if tzdata is absent; intermittent test failures at month end; no way to freeze time in tests.
- **Mitigation:** New `budget_planner/clock.py`: `utc_now()`, `today_local(settings)` and an injectable override (`ContextVar`) used by tests and the visual suite; a `today` FastAPI dependency for routers; services never call `date.today()`; ban `date.today`/`datetime.now` outside the module with ruff `TID251` banned-api (removes the 18 `DTZ011` suppressions). Keep `TZ` in compose for log timestamps only. Freeze the clock in the F-21 tests.
- **Effort:** M
- **Related:** ADR-0007; Q-003; operator Q: tzdata in the image, only Warsaw supported? (OQ-3, OQ-19)
- **Verification:** V1: C-08 Probable, Medium to Low (mitigated by TZ); A-13 not sampled; F-21 not sampled.

### Q-032 — 'Current' balance includes future-dated transactions while forecast day 0 and the sparkline do not
- **Severity / Confidence:** Medium / Probable
- **Track / root cause:** C / `duplicate-logic`
- **Track aliases and calibration:** C-14 Medium
- **Location(s):** `services/balance.py:87-107` (`as_of_date=None` counts all), `:210-217`; `web/today_data.py:116`, `services/fortune.py:36` vs `services/forecast.py:498` (`as_of_date=today`)
- **Description:** Two definitions of 'today's balance' coexist; a future-dated actual transaction moves net worth and the card but not the forecast start.
- **Evidence:** `tracks/C-correctness.md` C-14 (code citation).
- **Impact:** Headline balance and forecast start differ by future-dated actuals; one-day lag in the sparkline on a UTC host.
- **Mitigation:** Decide the rule once (ADR amendment, operator OQ-16): `balance.as_of_today(conn, user, account, today)` used by every consumer; if future-dated actuals are allowed they stay out of 'current'.
- **Effort:** S-M
- **Related:** Q-031; operator Q: future-dated actuals allowed?
- **Verification:** not sampled by V1/V2.

### Q-033 — N+1 query storms on /accounts and /forecast (about 2900 and 2800 statements per request on the demo DB)
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** C / `layer-leak`
- **Track aliases and calibration:** C-07 High -> Medium (verifier)
- **Location(s):** `services/balance.py:191-217` (90 `derive_balance` calls per account, 3 queries each), `:87-107`; `web/routers/accounts.py:68-70`; `services/forecast.py:271-274,380-386,456-461,690-696,756-759`; `services/recurring.py:641-660`
- **Description:** Per-day and per-rule queries instead of one load per request. Statement counts: /accounts 2959, /forecast 2770, /today 224, /budget 116, /plan 110, /ledger 9 (V1; the claim holds for two pages, not five).
- **Evidence:** `tracks/C-correctness.md` C-07 (`repro/C/query_counts.py`); V1 repro `v_c07` (`out_c07.txt`).
- **Impact:** Slow pages that scale with data volume (and with users); no wrong numbers.
- **Mitigation:** `balance.balance_series`: one transactions query then a running sum; in forecast/today/budget load rules, overrides, planned rows and budget tiers once into dicts and pass them down; add a pytest `assert_max_queries(route, n)` helper for `/accounts`, `/today`, `/forecast`, `/budget`, `/plan`. Plan with Q-002 (the same loops).
- **Effort:** M
- **Related:** ADR-0081 (aggregates in Python), Q-035
- **Verification:** V1: Confirmed (statement counts), High to Medium.

### Q-034 — No `user_id`-leading indexes on the large multi-user tables; a session write on every request
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** C / `scoping-gap`
- **Track aliases and calibration:** C-11 Medium
- **Priority flag:** **Fix before a second user is onboarded**
- **Location(s):** `migrations/0012_multi_user.sql:212-219,274-275,338`; `repositories/retention.py:26,37`; `repositories/sessions.py:248`
- **Description:** User-scoped filters scan indexes not led by `user_id`; the retention purge compares a differently formatted timestamp; `last_seen_at` is written on every request.
- **Evidence:** `tracks/C-correctness.md` C-11 (`repro/C/explain_plans.py`).
- **Impact:** Slower queries and write contention as users and data grow.
- **Mitigation:** New migration: `(user_id, operation_date) WHERE deleted_at IS NULL` on `transactions` and `planned_transactions`, `(user_id, id)` on `audit_log`, `(user_id, active)` on `recurring_rules`; index or comparable `changed_at` for the purge; throttle `last_seen_at` to once per minute.
- **Effort:** S-M
- **Related:** ADR-0061; Q-025
- **Verification:** not sampled by V1/V2.

### Q-035 — Unbounded work per request: all-row loads for counts and balances, unbounded page size and body size, full `PRAGMA integrity_check` on every unauthenticated `/ready` probe
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** C/D / `security-control`
- **Track aliases and calibration:** C-12 Medium; D-04 Low; D-05 Low
- **Calibration note:** H4 confirmed `/ready` is unauthenticated on the live drill and returns only `{"status":"ready","db":"ok"}` on success (no detail on the success path); D-05 unchanged, the per-probe `integrity_check` cost and the exception echo remain.
- **Location(s):** `web/routers/ledger.py:68,377-390` (`len(list_filtered(... limit=None))`, `page_size` unbounded), `domain/transactions.py:91`, `services/balance.py:77-82`, `services/budget.py:246-250`; `web/routers/health.py:40-79`, `web/middleware/auth.py:49-58`; `terraform/cloud-init/compose/Caddyfile.tpl:41-58` and `deploy/Caddyfile` (no `request_body max_size`); `routers/accounts.py:185`, `transactions.py:237` (field lengths)
- **Description:** Counts and balances load every row; `page_size=1000000` returns 200; there is no body or field limit; `/ready` runs a full integrity check per probe and echoes exception text.
- **Evidence:** `tracks/C-correctness.md` C-12; `tracks/D-security.md` D-04, D-05.
- **Impact:** Self-inflicted slowness, cheap request amplification against an unauthenticated endpoint, DB and replica growth.
- **Mitigation:** `SELECT COUNT(*)` / `SUM` repository functions for counts, balances and aggregates (also ADR-0081); clamp `page_size` to a named maximum in `parse_filters`; field lengths in service drafts (name 120, description 500); Caddy `request_body { max_size 256KB }`; `/ready` uses `SELECT 1` plus a cached `PRAGMA quick_check(1)` (30 s) and logs instead of echoing exceptions.
- **Effort:** M
- **Related:** ADR-0081; Q-033, Q-027, Q-023
- **Verification:** not sampled by V1/V2.

### Q-036 — Direction-to-sign logic exists in six hand-written copies (and default branches that would swallow a new direction)
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** A / `duplicate-logic`
- **Track aliases and calibration:** A-10 Medium
- **Location(s):** `services/balance.py:42`, `services/ledger_totals.py:22`, `services/forecast.py:128,751,770`, `services/account_planned.py:74`, `web/routers/transactions.py:145-150` (`else: delta = amount_minor`), `services/analytics.py:202-205`; template `_partials/components/_amount.html:5-6`
- **Description:** ADR-0008 is one rule implemented per call site; adjustment is counted by balance/ledger and skipped by planned/forecast by design. The copies agree today.
- **Evidence:** `tracks/A-duplication.md` A-10 (`repro/A/output/inv_04a*`).
- **Impact:** Any new direction or sign rule must be changed six times (latent wrong money).
- **Mitigation:** One `domain` function `signed_legs(direction, amount, account, dest)` returning legs with an exhaustive `match` and `assert_never`; the others become one-line adapters; adjustment policy stays an explicit parameter.
- **Effort:** M
- **Related:** ADR-0008, ADR-0011; Q-010
- **Verification:** not sampled by V1/V2.

### Q-037 — HTMX 404/409/500 responses carry an out-of-band flash that htmx never swaps; failed saves and expired CSRF tokens are silent
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** E / `htmx-contract`
- **Track aliases and calibration:** E-01 Medium
- **Location(s):** `web/errors.py:55-77,91,107,129`; `static/js/app-init.js:4-10` (only 422/429 forced to swap); `static/js/users-admin.js:73-82`; `templates/base.html:6-7`; `static/htmx-csrf.js:36-41`
- **Description:** htmx 2 does not swap 4xx/5xx by default; the server builds a flash for 404/409/500 but the client whitelists only 422/429 (and 409 on the users page). There is no `htmx:responseError` handler; a CSRF 403 (JSON) and a missing token are invisible.
- **Evidence:** `tracks/E-frontend.md` E-01 (`repro/E/runtime_audit.py` probe P3, `runtime_audit.out.json`).
- **Impact:** A failed save or a stale-row conflict looks like 'nothing happened'; the user re-clicks or assumes success.
- **Mitigation:** One global `htmx:beforeSwap` handler in `app-init.js` replacing the 422/429 block: for any 4xx/5xx with `hx-swap-oob` set `shouldSwap = true; isError = false`, plus an `htmx:responseError`/`sendError` fallback writing a generic message to `#flash-region-assertive`; one e2e test (error to flash visible). Behaviour layer, survives the ADR-0107 redesign.
- **Effort:** S
- **Related:** ADR-0107; Q-038
- **Verification:** not sampled by V1/V2.

### Q-038 — HTMX event contract is half dead: four `*-stale` events (27 emit sites, 45 string literals) have no listener, toast payload uses `kind` and `variant` inconsistently
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** A/E / `htmx-contract`
- **Track aliases and calibration:** A-18 Low; E-02 Medium; E-07 Low
- **Location(s):** emit sites `routers/{categories,recurring,accounts,transactions,budget,planned}.py` (e.g. `transactions.py:313,432,443,457`, `budget.py:262-427`, `planned.py:91,162`, `recurring.py:446,530`, `categories.py:226-237`), helper `web/htmx.py:18`; listeners `templates/ledger/_table.html:22`, `partials/forecast/_view.html:2`, `static/js/app-init.js:36-61`; toast `routers/accounts.py:356,386` (`kind`) vs `planned.py:91,162` (`variant`), `app-init.js:41`
- **Description:** `budget-stale`, `balance-stale`, `today-stale`, `settings-categories-stale` are emitted and nothing listens; pages stay correct only because `refresh_unless_on` falls back to full-page reloads. 'Account deleted' and 'Snapshot saved' render with the info style.
- **Evidence:** `tracks/E-frontend.md` E-02, E-07 (`repro/E/htmx_matrix.py`, `htmx_matrix.out.md`, runtime listener enumeration on 19 routes); `tracks/A-duplication.md` A-18.
- **Impact:** Future work will assume refreshes that do not happen; wrong toast style.
- **Mitigation:** `web/htmx.py`: `Event` constants and `invalidate(response, *domains)` mapping domain to events once, `toast_payload(variant, message, undo=...)` for all emitters; drop the four unlistened names or add listeners where a region needs them; test that fails when an emitted name has no listener (template/router parse).
- **Effort:** S-M
- **Related:** ADR-0107; Q-037, Q-072
- **Verification:** not sampled by V1/V2.

### Q-039 — 'Left per day' and percent-used are re-derived in templates in float, ignoring the service value; per-day divisors and zero guards differ per page
- **Severity / Confidence:** Medium / Probable
- **Track / root cause:** A/E / `template-logic`
- **Track aliases and calibration:** E-05 High -> Medium (verifier); A-15 Medium -> Low (verifier)
- **Location(s):** `web/templates/today/index.html:28-36`, `plan/_budget_tab.html:2-12,56-59`, `_partials/components/_period_header.html:4-8`, `budget/index.html:102-108`, `plan/_analytics_bundle.html:24-35`, `_partials/components/_heatmap_cell.html:4-6`; authoritative `services/budget.py:583-587` (`left_daily_spend_minor`, half-even) and `services/today.py:96-102`
- **Description:** The service computes per-day with Decimal half-even (None for zero budget); the hero and Plan re-divide floats with different divisors and guards, three results for one question; the divergence is at most one minor unit plus cosmetic clamping (V1/V2).
- **Evidence:** `tracks/E-frontend.md` E-05 (code citation); `tracks/A-duplication.md` A-15.
- **Impact:** Hero and Plan can differ by 0.01; 'over budget' thresholds evaluated on floats.
- **Mitigation:** Add `left_per_day_minor`, `spent_pct`, `committed_pct`, `remaining_after` to `MonthSummary` (or a `BudgetView` in `web/`), render only those, delete the `set` blocks; decide the afford clamp once. View-model work that survives ADR-0107.
- **Effort:** M
- **Related:** ADR-0107; Q-003, Q-011
- **Verification:** V2: E-05 code-confirmed, High to Medium. V1: A-15 Confirmed, Medium to Low.

### Q-040 — Prod accepts an image signed by `build.yml` from any ref; any branch can push and sign `sha-*` images, and rollback resolves mutable tags without an ancestry check
- **Severity / Confidence:** Medium / Probable
- **Track / root cause:** H1 / `ci-trust-boundary`
- **Track aliases and calibration:** H1-02 High -> Medium (verifier)
- **Location(s):** `terraform/modules/compute/user_data.tf:118` (`identity_regexp` ends at `build.yml@`), `terraform/host/agent/bp_agent.py:410-411`, `.github/workflows/build.yml:26-48,97-99`, `drill.yml:149-158`, `rollback.yml:84-92`, `scripts/ci/ref_guard.py:resolve_rollback_target`, `scripts/ci/host_release.py:resolve_ref` (re-check at remediation, see metadata note)
- **Description:** The host verifies the Sigstore identity only up to the workflow file, so `build.yml@refs/heads/<any branch>` is accepted; GHCR tags are mutable and pushable by any branch workflow; a rollback resolves its target tag at approval time and accepts `sha-<hex>` of an unmerged branch build. A release itself is safe (tag and digest come from the signed release run).
- **Evidence:** `tracks/H1-ci-supply-chain.md` H1-02; `repro/H1/gate_and_signing_probe.out` sections 2 and 5.
- **Impact:** With H1-01-level access an attacker overwrites a release tag and waits for a legitimate rollback; one human approval then runs attacker code with prod credentials. Defence in depth.
- **Mitigation:** Pin the verified identity: `identity_regexp = ...build\.yml@refs/(heads/main|tags/v[0-9]+\.[0-9]+\.[0-9]+)$` (drill hosts keep a looser pattern via a variable); `resolve_rollback_target` accepts only tags previously applied to prod or commits that are ancestors of `origin/main`; print the resolved digest in the job summary before the `prod` approval.
- **Effort:** S
- **Related:** ADR-0037, 0099, 0109, 0111; Q-012
- **Verification:** V2: Probable, High to Medium (still needs an approved rollback pointing at the image).

### Q-041 — The merge gate is self-attested: required checks come from PR-editable workflows, are not bound to an app, and need no review
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** H1 / `ci-trust-boundary`
- **Track aliases and calibration:** H1-03 Medium
- **Location(s):** ruleset `protect-main` (`repro/H1/gh_api/ruleset_protect_main.json`: six required contexts without `integration_id`, zero required approvals, no code-owner review, no `CODEOWNERS`); `.github/workflows/drill.yml:262-322` (`gate-result` job in the branch), `ci.yml`, `security.yml`, `lock-check.yml`
- **Description:** `drill-gate-skip.yml` is safe by `pull_request_target`, but the real gate and the other checks run from the PR's own workflow definitions, so a PR can post a green `drill-gate` itself or no-op the checks under the same job names; the PR author is the only party that can merge.
- **Evidence:** `tracks/H1-ci-supply-chain.md` H1-03; `repro/H1/gate_and_signing_probe.out` section 3.
- **Impact:** The gate protects against honest mistakes, not against a compromised or malicious author; a release still needs the `prod` approval.
- **Mitigation:** Ruleset `workflows` rule (workflows referenced from `main`) for `ci`, `security`, `lock-check`; `integration_id` 15368 on every required context; `.github/CODEOWNERS` over `.github/`, `scripts/ci/`, `terraform/`, `.security-allowlist.yml` with code-owner review (needs a second human or bot; otherwise record as accepted risk, operator OQ-26).
- **Effort:** S
- **Related:** ADR-0099, ADR-0121; Q-042
- **Verification:** not sampled by V1/V2.

### Q-042 — The `drill-gate-skip` classifier treats paths as inert that deploy, CI and agent tooling consume, and its verdict and status target come from different moments (TOCTOU)
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** H1 / `ci-trust-boundary`
- **Track aliases and calibration:** H1-04 Medium; H1-05 Medium
- **Location(s):** `scripts/ci/drill_gate_skip.py:16-37` (`SAFE_DIRS`: docs, `.claude`, tests, top-level `*.md`); consumers `.github/workflows/terraform.yml:140` (`tests/render/render_check.py`), `litestream-plaintext-cleanup.yml:65` (`docs/plans/v3/runbooks/restore-log.md`), `tests/**` under `just ci`, `.claude/**` and `CLAUDE.md`; `.github/workflows/drill-gate-skip.yml:23-25,55-60,88`
- **Description:** A PR changing only `tests/render/render_check.py`, `restore-log.md` or `.claude/**`/`CLAUDE.md` is classified `skip` and gets a green `drill-gate` without a drill. Separately the file list is read live from `pulls/N/files` but posted on the event's head SHA with no comparison, so a stale list or a force-push race can attach `skip` to a deploy-relevant head.
- **Evidence:** `tracks/H1-ci-supply-chain.md` H1-04 (`repro/H1/classifier_probe.out`), H1-05 (`repro/H1/gate_and_signing_probe.out` section 1; race not reproduced).
- **Impact:** A docs/tests-only PR can weaken a deploy gate or steer the agents that author later PRs without being drilled.
- **Mitigation:** Shrink the allowlist to what nothing executes: `docs/**` except `restore-log.md`, top-level `*.md` except `CLAUDE.md`; drop `.claude/` and `tests/`; unit test greps `.github/` and `scripts/ci/` for paths under allowlisted dirs. TOCTOU: list files from `gh api repos/$REPO/compare/${BASE_SHA}...${HEAD_SHA}` and re-read `pulls/$PR --jq .head.sha` before posting.
- **Effort:** S
- **Related:** ADR-0121, ADR-0112; Q-041
- **Verification:** not sampled by V1/V2.

### Q-043 — Unused dev dependency `httpx2` of unverified provenance is locked and installed by `uv sync` on every developer machine and CI run
- **Severity / Confidence:** Medium / Probable
- **Track / root cause:** G / `dependency`
- **Track aliases and calibration:** G-07 Low
- **Calibration note:** G-07 orig Low: raised to Medium for the unverified provenance; becomes Low if the package is legitimate.
- **Location(s):** `pyproject.toml:44` (`httpx2>=0.1`), `uv.lock:739-746` (2.16.0); no import in `src/`, `tests/`, `scripts/`; leftovers `pyproject.toml:136,172` (plotly overrides)
- **Description:** `httpx2` is not the well-known `httpx` and nothing imports it. An unexplained package in the dev group executes at install time in CI (release `ci` job has `id-token`/`packages: write`, see Q-069). Plotly mypy/pytest entries are stale.
- **Evidence:** `tracks/G-drift.md` G-07 (grep for imports).
- **Impact:** Possible typosquat or accidental dependency in the toolchain; if legitimate it is dead weight.
- **Mitigation:** Check provenance first (PyPI project page, who added it in `git log -S httpx2`); then remove `httpx2` and the plotly entries and re-lock. If provenance fails, treat as a security incident (rotate CI-reachable credentials).
- **Effort:** S
- **Related:** Q-069; operator Q: what is `httpx2`? (OQ-20)
- **Verification:** Not sampled.

### Q-044 — `just ci` and PR CI omit checks that pre-commit enforces (ruff format, bandit, detect-secrets, tailwind-check) and tool versions drift between pre-commit pins, `uv.lock` and CI
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** G / `config-drift`
- **Track aliases and calibration:** G-05 Medium; G-06 Medium
- **Location(s):** `justfile:92-98,116`; `.pre-commit-config.yaml:26,33-58,70,76-83,125-131`; `.github/workflows/ci.yml:26,42,51,68` (re-check: `audit/quality` absorbed T-D158 CI changes)
- **Description:** `just lint` lacks `ruff format --check`, bandit and detect-secrets; sqlfluff 3.1.1 vs lock 4.4.0, djlint v1.35.2 vs 1.47.0, bandit 1.7.10 vs 1.9.4, mypy hook dependencies unpinned ranges; `uv` is `latest` in `ci.yml`.
- **Evidence:** `tracks/G-drift.md` G-05, G-06 (section 5 parity table).
- **Impact:** A check passes locally and fails in CI (or the reverse), and CI does not run security hooks the local gate does.
- **Mitigation:** Run the hooks as `repo: local`, `language: system`, `entry: uv run <tool>` so every linter uses the lock (as `pytest-fast` already does), drop hook-side `rev` pins, pin `uv` in `ci.yml`, and run `pre-commit run --all-files` (with `SKIP=pytest-fast`) as one CI step.
- **Effort:** S
- **Related:** ADR-0017, ADR-0120; operator Q: bandit/detect-secrets excluded from CI on purpose? (OQ-23)
- **Verification:** V2: G-05 Confirmed (Medium). G-06 not sampled.

### Q-045 — No service layer for CRUD: 13 routers import repositories and 6 write through them
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** B / `layer-leak`
- **Track aliases and calibration:** B-04 Medium
- **Location(s):** writes from routers: `categories.py:109,192,211`, `accounts.py:225,325,354,377,497`, `transactions.py:295,416,441,453`, `planned.py:269,385,413,427`, `budget.py:256,271,281,341,365,421`, `recurring.py:358,730,761,852,884`; reads in `ledger.py`, `today.py`, `settings.py`, `settings_security.py`, `plan.py`, `auth.py`; `repositories._shared.transaction` imported at `recurring.py:486`, `planned.py:124`; `web/today_data.py:20,112`, `web/deps.py:18-19`
- **Description:** 'Thin web, fat services' (CLAUDE.md, ADR-0021) is not enforced: validation and orchestration live in routers, which is why the same rule appears per route (Q-004, Q-023).
- **Evidence:** `tracks/B-layering.md` B-04 and section 5.
- **Impact:** Validation drift and bypass of audit/soft-delete conventions; harder to port to field encryption (v4 Phase 3).
- **Mitigation:** One CRUD service per entity (`services/transactions.py`, `planned.py`, `accounts.py`, `recurring_rules.py`, `budget_overrides.py`; `categories.py` exists) that validates and calls repositories; enable an import-linter contract `routers -> repositories` with `ignore_imports` for not-yet-migrated modules and shrink it per PR. Do after Q-047; sequence against the ADR-0107 redesign (operator OQ-12).
- **Effort:** L
- **Related:** ADR-0019, ADR-0021, ADR-0107, ADR-0081; Q-046
- **Verification:** not sampled by V1/V2.

### Q-046 — Two files over 800 lines and 16 router functions of complexity C or worse
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** B / `oversized-module`
- **Track aliases and calibration:** B-09 Medium
- **Location(s):** `web/routers/recurring.py` (1115 lines, MI B 17.61, 17 suppressions, 109 `Any`), `services/forecast.py` (978), `web/routers/plan.py:68` (E 31), `web/routers/ledger.py:140` (D 29); table 2.4 of `tracks/B-layering.md`; `baseline/sizes.txt`, `radon-cc.txt`
- **Description:** Size and complexity hot spots; the same files host findings Q-002, Q-003 and Q-006.
- **Evidence:** `tracks/B-layering.md` B-09 and table 2.4.
- **Impact:** Higher change risk where most defects were found.
- **Mitigation:** Do the splits of table 2.4 after Q-045 (routers shrink as services appear); introduce xenon at `--max-absolute C` in `just lint` only after the E and D blocks are gone.
- **Effort:** L
- **Related:** ADR-0021; Q-003, Q-002
- **Verification:** V1: Confirmed (Medium).

### Q-047 — Import cycle `repositories.recurring <-> services.recurring <-> services.recurring_formula` forces nine `PLC0415` lazy imports; 28 unnecessary function-level imports; `next_due` seeding copied in three places
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** A/B / `import-cycle`
- **Track aliases and calibration:** B-06 Medium; B-12 Low; A-21 Low
- **Location(s):** `repositories/recurring.py:31,128,227`, `services/recurring.py:309,384,408,515,603,635-638`, `services/recurring_formula.py:166,167,213,336,392`, `db/migrate.py:134-212`; router-to-router private imports `planned.py:184`, `transactions.py:195`, `today.py:216`; `baseline/suppressions.txt`
- **Description:** A repository imports a service for scheduling math, producing the cycle; the migration hook and repository each re-implement `next_due` seeding (and the repository calls `date.today()`). 28 other lazy imports are unnecessary.
- **Evidence:** `tracks/B-layering.md` B-06, B-12 (table 2.2); `tracks/A-duplication.md` A-21; `baseline/import-graph.txt`.
- **Impact:** Fragile import order, hidden dependencies, and a repository that depends on services (breaks the layering contract).
- **Mitigation:** Extract the pure scheduling code (`generate_occurrences`, `advance_next_due`, `first_due_on_or_after`, `occurrence_in_month`, `_STEP_MONTHS`, `_build_lookup_stub`) into `domain/recurring_schedule.py`; repositories and services import it from there; `recurring_formula` imports `services.recurring` at top level and the bottom re-export is dropped; the migration hook calls `first_due_on_or_after`; the repository takes `today` as a parameter. Hoist the 28 remaining lazy imports; move `render_table_for` and the formula-form helpers out of the routers; add the `repositories` not-`services` contract to CI.
- **Effort:** M
- **Related:** ADR-0021; Q-006, Q-031
- **Verification:** B-06, B-12, A-21 not sampled by V1/V2.

### Q-048 — Eight service signatures have adjacent same-typed positional parameters; the rule is noise on 24 route handlers
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** B / `wide-signature`
- **Track aliases and calibration:** B-08 Medium
- **Location(s):** `services/reconciliation.py:62`, `services/budget.py:408`, `services/forecast.py:433,530,778`, `services/recurring.py:641`, `services/recurring_formula.py:322`, `services/fx.py:119`; 24 handler suppressions in `web/routers/*.py` (table 2.3)
- **Description:** Risk of swapped `user_id`/`account_id`/amount arguments that mypy cannot catch.
- **Evidence:** `tracks/B-layering.md` B-08 (table 2.3).
- **Impact:** A swapped-argument bug is silent.
- **Mitigation:** Keep `conn, user_id` positional and make everything after them keyword-only (`*`) in the eight service functions (about 12 callers); replace the 24 router `noqa` comments with a `per-file-ignores` entry `"src/budget_planner/web/routers/*.py" = ["PLR0917"]`.
- **Effort:** S
- **Related:** ADR-0021
- **Verification:** not sampled by V1/V2.

### Q-049 — Audit-free repository helpers are public API and `user_preferences` writes are unaudited
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** B / `repo-bypass`
- **Track aliases and calibration:** B-10 Medium
- **Location(s):** `repositories/recurring.py:269` (`set_next_due`), `:294` (`set_inactive`), `:406` (`mark_override_promoted`), `repositories/preferences.py:43,59`
- **Description:** Helpers that skip `audit_log` by design are importable from anywhere (the undo router uses one), and preference writes (incl. the income anchor) leave no audit row.
- **Evidence:** `tracks/B-layering.md` B-10.
- **Impact:** A future caller silently bypasses ADR-0019 audit.
- **Mitigation:** Move the three helpers to `repositories/_unaudited.py` and add an architecture test (beside `tests/architecture/test_user_id_filter.py`) that fails when anything other than `services/recurring.py` imports it; route `preferences.upsert/delete` through `mutate` with entity type `user_preference`. Decide whether domain mutations should also record `ip`/`session_id` (operator OQ-10, ADR-0122 records only `user_id`).
- **Effort:** S
- **Related:** ADR-0019, ADR-0022, ADR-0122; Q-024
- **Verification:** not sampled by V1/V2.

### Q-050 — Routes with no caller; the ADR-0056 live formula preview is unreachable from the UI
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** G / `dead-code`
- **Track aliases and calibration:** G-13 Medium
- **Location(s):** `web/routers/recurring.py:546` (formula preview), `:424` (batch promote-due), `web/routers/accounts.py:133`, `budget.py:347`, `plan.py:254`; section 2.4 of `tracks/G-drift.md`
- **Description:** A user-visible feature (live preview of formula-derived amounts) exists server-side but nothing calls it; the other four routes are orphaned.
- **Evidence:** `tracks/G-drift.md` G-13 (grep of all callers).
- **Impact:** One missing feature; dead surface to maintain and secure.
- **Mitigation:** Decide per route: re-wire the preview in the entry form (or in the ADR-0107 redesign) or delete route, template and tests; delete the other four.
- **Effort:** S (M for the re-wire)
- **Related:** ADR-0056, ADR-0107
- **Verification:** not sampled by V1/V2.

### Q-051 — ADR status and index hygiene: 15 ADRs say Proposed but are live, amendments live only in the README index, duplicate numbers and broken links
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** G / `doc-drift`
- **Track aliases and calibration:** G-02 Medium; G-03 Medium; G-04 Low
- **Location(s):** `docs/adr/` 0032, 0033, 0034, 0035, 0037, 0050, 0051, 0054, 0056, 0061, 0078, 0106, 0107, 0118, 0127 (status line 3); status lines of 0002, 0011, 0012, 0015, 0017, 0018, 0019, 0022, 0023, 0025, 0026, 0027, 0030, 0031, 0041, 0045, 0067, 0099, 0100, 0101, 0102, 0110; duplicate 0105 and 0121, gap 0044, three broken links in 0091/0092, 21 index title mismatches
- **Description:** ADR status lines contradict the code and the plans; amendments are recorded only in the README index.
- **Evidence:** `tracks/G-drift.md` G-02 (verified by V2), G-03, G-04 (section 3 table).
- **Impact:** Agents and the operator read a Proposed ADR as non-binding or miss an amendment.
- **Mitigation:** One docs-first PR: flip the 13 implemented ADRs to Accepted, 0106/0107 to 'Accepted, implementation pending' (operator OQ-24); status-line convention `Accepted (amended by ADR-N ...)` with a generator or `tests/architecture/test_adr_index.py` (unique numbers except the grandfathered 0105/0121 pairs, index sorted, links resolve); the new Mutmut ADR takes the next free number.
- **Effort:** S-M
- **Related:** Q-052; operator Q: grandfather 0105/0121? (OQ-25)
- **Verification:** V2: G-02 Confirmed. G-03, G-04 not sampled.

### Q-052 — ADR bodies and comments contradicted by code (ADR-0002, 0023, 0026, 0036, 0052, 0057; stale ADR-0005 and 'Phase 7' comments)
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** G / `doc-drift`
- **Track aliases and calibration:** G-16 Medium; G-15 Low
- **Location(s):** ADR-0002 lines 15-16, ADR-0023 section 1, ADR-0026/0028 (`fab_target_for`), ADR-0036 lines 68, 108-109 vs `terraform/cloud-init/compose/docker-compose.yml.tpl:122`, ADR-0052 vs `package.json:16`, ADR-0057 line 24; comments `justfile:23`, `config.py:49,162,166`, `web/templating.py:183`, `web/routers/today.py:174`, `services/balance.py:206`, `web/routers/analytics.py:8`, `docker-compose.yml.tpl:4`
- **Description:** ADR-0002 still says Tailwind CDN + Plotly (code: local Tailwind, server SVG); ADR-0036 says a custom Caddy image (compose uses `caddy:2.8`).
- **Evidence:** `tracks/G-drift.md` G-16 (V2 checked 0002 and 0036), G-15.
- **Impact:** Misleading design record; wrong comments cite superseded ADRs.
- **Mitigation:** Edit each status line to the true state (partly superseded by N); ADR-0036 gets a dated addendum (stock `caddy:2.8`, app-side rate limiting per ADR-0072); ADR-0057 either gets validation or the text is corrected; update the comments to cite ADR-0061/0036 and delete the Phase-7 promises.
- **Effort:** M
- **Related:** Q-051
- **Verification:** V2: G-16 Confirmed (0002, 0036). G-15 not sampled.

### Q-053 — CLAUDE.md, the orchestrator skill and `requirements.md` section 3 and 6.7 contradict the code (paths that do not exist, Plotly/CDN stack, FAB and shortcuts, fail2ban and CSP claims)
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** D/G / `doc-drift`
- **Track aliases and calibration:** G-08 Medium; G-09 Medium; D-13 Low
- **Location(s):** `CLAUDE.md` (change policy item 1, handoff checklist, Stack line); `.claude/skills/orchestrator-mode/SKILL.md:62-63`; `docs/requirements.md:109,136-147,156-157,171,174,177,180` and `:340-346`; `terraform/cloud-init/bootstrap.yaml.tpl:77`, `Caddyfile.tpl` header comment, `deploy/Caddyfile:5-8`
- **Description:** CLAUDE.md names `docs/tasks.md` and `docs/implementation_plan.md` (they live under `docs/plans/<plan>/`), lists Tailwind CDN and Plotly, omits `demo-build`, `test-fast`, `set-password`; requirements describe controls that were never implemented (fail2ban jails, Mozilla Observatory, app-propagated CSP).
- **Evidence:** `tracks/G-drift.md` G-08, G-09; `tracks/D-security.md` D-13.
- **Impact:** Agents following CLAUDE.md edit the wrong files; the documented security posture is not the real one.
- **Mitigation:** Docs-first edits (CLAUDE.md order): CLAUDE.md and the skill name `docs/plans/<plan>/{tasks,implementation_plan}.md` and the real stack and commands; requirements 3.1/3.5/3.6/3.9 updated (3.9 replaced by a pointer to ADR-0051/0077 until ADR-0107 lands); 6.7 either implemented (Q-027, Q-065) or edited to the real state with ADR-0036.
- **Effort:** S
- **Related:** Q-051
- **Verification:** G-08, G-09, D-13 not sampled by V1/V2.

### Q-054 — Task status in `tasks.md` disagrees with CHANGELOG and ADRs
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** G / `doc-drift`
- **Track aliases and calibration:** G-10 Medium
- **Location(s):** `docs/plans/v1/tasks.md:515,519,670`; `docs/plans/v3/tasks.md:920,952`; `docs/plans/v2/tasks.md` (60 rows open, e.g. T-R71 to T-R73); `docs/plans/ui-redesign/tasks.md:12` vs `docs/plans/ui-test-harness/tasks.md:19,28`; nine v1 tasks, T-D21, T-D22, T-CS03 with a check mark and no CHANGELOG line
- **Description:** Status marks and the CHANGELOG diverge, so 'done' is not reliable.
- **Evidence:** `tracks/G-drift.md` G-10.
- **Impact:** Wrong picture of what shipped; remediation planning starts from stale status.
- **Mitigation:** Reconcile the listed rows once (operator decides whether the v2 plan is closed as superseded by ADR-0107, OQ-22); architecture test that every `### ✅ T-*` id appears in the CHANGELOG and every id named done in the CHANGELOG has the check mark.
- **Effort:** M
- **Related:** Q-051
- **Verification:** not sampled by V1/V2.

### Q-055 — Non-priority modules: 213 surviving mutants rule-defaulted (analytics, users, planned, upcoming, today, export, replication_health, preferences)
- **Severity / Confidence:** Medium / Probable
- **Track / root cause:** F / `weak-assertion`
- **Track aliases and calibration:** F-11 Medium
- **Location(s):** `baseline/mutmut-real-gaps.md` rows 310-516 (`analytics` 322-358, `users` 488-516, `planned` 403-429, `upcoming` 471-487, `replication_health` 440-454, `today` 458-470 incl. `_div_round_half_even` zero denominator, `preferences` 430-438, `export` 375-382, `account_planned` 310-316)
- **Description:** Mutants in money-adjacent modules survive; rule-defaulted rows were not individually proven (the baseline sampled about a third).
- **Evidence:** `tracks/F-tests.md` F-11; `baseline/mutmut.txt` (services 84.3 percent killed).
- **Impact:** Regressions in analytics and today arithmetic would not fail unit tests.
- **Mitigation:** Fix after the priority-module findings, module by module with the 'suggested killing test' column, starting with `analytics` (after Q-008) and `today`; re-triage the sampled rows first.
- **Effort:** L
- **Related:** Q-008
- **Verification:** Not sampled (F-11).

### Q-056 — Four of the five 'critical flow' e2e tests are API tests run in a browser; no test submits the add, reconcile, promote or budget forms through the UI
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** F / `weak-assertion`
- **Track aliases and calibration:** F-15 Medium
- **Location(s):** `tests/e2e/test_add_transaction_flow.py:19-68`, `test_reconcile_flow.py:19-65`, `test_recurring_promote_flow.py:26-100`, `test_set_budget_flow.py:19-62`, `test_credit_card_journey.py` (skipped); `tests/e2e/test_csp_buttons.py`
- **Description:** The flows seed and act through `request.post`, so form markup, HTMX wiring and swap behaviour are not exercised.
- **Evidence:** `tracks/F-tests.md` F-15.
- **Impact:** A broken form or HTMX swap passes the e2e suite.
- **Mitigation:** Rewrite the four tests to drive the visible forms (`get_by_role(...).click()/fill`) for one happy path each; keep `request.post` only for seeding.
- **Effort:** M
- **Related:** Q-037, Q-058
- **Verification:** Not sampled (F-15).

### Q-057 — `test_pagination_keeps_filters` races two in-flight HTMX responses; the product has no `hx-sync`
- **Severity / Confidence:** Medium / Probable
- **Track / root cause:** F / `htmx-contract`
- **Track aliases and calibration:** F-16 Medium
- **Location(s):** test `tests/e2e/test_ledger_filters.py:73-81,109-114`; product `templates/ledger/index.html:25-29`, `templates/ledger/_table.html:386-389`
- **Description:** The filter form and the 'Older' button can issue overlapping requests whose responses arrive out of order; the test cannot wait on the right condition.
- **Evidence:** `tracks/F-tests.md` F-16 (derived from template and test, not reproduced under delay).
- **Impact:** A flaky e2e test and a real stale-response race for fast users.
- **Mitigation:** Product: `hx-sync="#ledger-table:replace"` on the form and the button. Test: wait for the filtered response with `page.expect_response(lambda r: "/ledger/table" in r.url and "category_id=" in r.url)` before clicking 'Older'.
- **Effort:** S
- **Related:** Q-038
- **Verification:** V3: Confirmed (no `hx-sync` anywhere in templates), Medium.

### Q-058 — The web test client hides transport-level bugs: CSRF header attached to every request, https forced, FX client built with a `base_url` production never sets
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** F / `weak-assertion`
- **Track aliases and calibration:** F-17 Medium
- **Location(s):** `tests/integration/web/conftest.py:45-70` (`_CSRFAwareTestClient`), `tests/e2e/conftest.py:217`, `tests/unit/services/test_fx.py:20-24`, `test_forecast*`
- **Description:** Test infrastructure removes the very conditions under which G-01 and the bulk-select CSRF issue would show.
- **Evidence:** `tracks/F-tests.md` F-17.
- **Impact:** Real transport bugs pass the suite.
- **Mitigation:** FX: one client factory in `services/fx.py` (Q-007) with tests injecting a transport into the same factory; add a route-enumerating test to `tests/integration/web/test_csrf.py` that iterates every POST/PUT/PATCH/DELETE route with a raw client and asserts 403 without a token.
- **Effort:** M
- **Related:** Q-007, Q-072
- **Verification:** V3: Confirmed (9 test sites build clients with a `base_url`), Medium.

### Q-059 — 141 HTTP tests assert only the status code and the reconciliation 'rollback' test is vacuous (it fails the only write)
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** F / `weak-assertion`
- **Track aliases and calibration:** F-18 Medium; F-19 Medium
- **Location(s):** `tests/integration/web/test_recurring.py` (24), `test_budget.py` (17, e.g. `:83-85,103-105`), `test_categories.py` (14), `test_planned.py` (11), `test_accounts.py` (11), `test_settings_users.py` (10), `test_transactions.py` (6), `test_auth_rate_limit.py` (6); `tests/unit/services/test_reconciliation.py:137-150`; `repro/F/weak_assert_scan.out`
- **Description:** Success paths do not check persistence; `test_rollback_on_failure` patches the only write so there is nothing to roll back.
- **Evidence:** `tracks/F-tests.md` F-18, F-19.
- **Impact:** Regressions in persistence and transaction atomicity are not caught.
- **Mitigation:** Add a read-back assertion through the repository (or the rendered value) to each success-path test and a row-count-unchanged assertion to each rejection test, starting with `test_budget.py`, `test_recurring.py`, `test_accounts.py`; patch `audit_svc.write_audit` to raise in the reconciliation test and assert zero transactions and zero audit rows.
- **Effort:** M
- **Related:** ADR-0019; Q-005
- **Verification:** V3: F-18 Confirmed (sample); F-19 not sampled.

### Q-060 — Prod-DB isolation in tests depends on `BUDGET_ENV=test` being set by default and on convention; there is no tripwire
- **Severity / Confidence:** Medium / Probable
- **Track / root cause:** F / `scoping-gap`
- **Track aliases and calibration:** F-20 Medium
- **Location(s):** `tests/conftest.py:19` (`os.environ.setdefault("BUDGET_ENV", "test")`), `config.py:20-21,45` (relative default `sqlite:///data/budget.sqlite`), `services/users.py:231-233`, `web/app.py:1`
- **Description:** A shell exporting `BUDGET_ENV=dev` wins over the default and the default database path resolves against the current directory, so a test run could open `data/budget.sqlite`. No test or script resolves to it today (grep clean).
- **Evidence:** `tracks/F-tests.md` F-20 (mechanism confirmed, not exercised to avoid touching the file).
- **Impact:** Would violate the CLAUDE.md prod-DB rule; candidate High if V3 or the operator agrees, because the consequence is writes to prod data.
- **Mitigation:** Autouse session fixture in `tests/conftest.py` that sets `BUDGET_DATABASE_URL` to a session temp path and unsets `BUDGET_PLANNER_ADMIN_*`; `db.connection.get_connection` raises when the resolved path equals the repository's `data/budget.sqlite` while `PYTEST_CURRENT_TEST` is set; replace `setdefault` by an unconditional assignment.
- **Effort:** S
- **Related:** CLAUDE.md Databases, ADR-0069; Q-077
- **Verification:** Not sampled (F-20); candidate High, see Details.

### Q-061 — The visual suite is opt-in, byte-exact, silently creates missing baselines, and its baselines predate the last template change
- **Severity / Confidence:** Medium / Confirmed
- **Track / root cause:** F / `config-drift`
- **Track aliases and calibration:** F-22 Medium
- **Location(s):** `justfile:78-84`, `pyproject.toml:159-160`, `.github/workflows/*.yml` (no visual job), `tests/visual/test_snapshots.py:105-109,116`
- **Description:** The gate does not run in CI, a missing baseline passes as a skip, and PNGs are compared byte-for-byte.
- **Evidence:** `tracks/F-tests.md` F-22.
- **Impact:** Visual regressions are not gated (CLAUDE.md requires the frontend audit per change).
- **Mitigation:** Scheduled/nightly workflow on a pinned Playwright image, perceptual threshold (`max_diff_pixel_ratio`), a missing baseline is a failure in CI, and a pre-commit check that baselines change when `templates/` change. Re-plan against the ADR-0107 redesign.
- **Effort:** M
- **Related:** ADR-0027, ADR-0107
- **Verification:** Not sampled (F-22).

### Q-062 — Session and passkey hardening (defence in depth): challenges not single-use, in-flight request re-sets the rotated token, passkey revoke keeps its sessions, CSRF token unbound
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** H3 / `security-control`
- **Track aliases and calibration:** H3-02 Low; H3-04 Low; H3-06 Low; H3-08 Low
- **Calibration note:** H3-04 rises to Medium if pages issue concurrent requests during re-auth (H3-Q2).
- **Location(s):** `web/auth_cookies.py:150-205`, `web/routers/auth.py:392-425,583-592`, `services/auth.py:383-392,411-413,455-465`, `services/reauth.py:135-169`, `web/middleware/auth.py:168-176`, `web/middleware/csrf.py:155-181`, `web/routers/auth.py` `_start_session`
- **Description:** (H3-02) A captured login assertion and challenge cookie replays for 300 s; with a counter-bearing key the replay revokes the owner's passkey. (H3-04) A response in flight during re-auth rotation re-sets the old token and signs the user out. (H3-06) Revoking a passkey leaves sessions created with it alive. (H3-08) The double-submit CSRF token is any cookie value, unbound to the session and never rotated.
- **Evidence:** `tracks/H3-auth.md` H3-02, H3-04, H3-06, H3-08 (`repro/H3/h3_passkey_ceremonies_output.txt` P1,P2,P7; `h3_rotation_race_output.txt`; `h3_csrf_preauth_output.txt` C1,C2).
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** (H3-02) single-use challenge nonce table (`DELETE ... RETURNING` at finish) and do not revoke on a regression with `new == stored == 0`. (H3-04) re-issue the cookie only if the token is still live after `call_next`, or a short grace window. (H3-06) store the credential id on `sessions` and revoke those sessions in `revoke_passkey`. (H3-08) HMAC-signed CSRF token bound to session or anonymous nonce, rotated at login and logout.
- **Effort:** S-M each (M for H3-02 and H3-08)
- **Related:** ADR-0067, ADR-0076, ADR-0033; Q-027; operator Q: H3-02 threat acceptable, authenticator counters, sessions with passkey (OQ-27)
- **Verification:** Not sampled (H3). Severities per track.

### Q-063 — Admin edge cases: an absent `is_admin` field demotes the target; concurrent admin changes surface 'database is locked' as 500
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** H2 / `htmx-contract`
- **Track aliases and calibration:** H2-05 Low
- **Priority flag:** **Fix before a second user is onboarded**
- **Location(s):** `web/routers/settings_users.py:77-78,228-264`; `services/users.py:385-392`; `repositories/_shared.py:113-143`
- **Description:** `_checkbox(None)` is False and becomes the new `is_admin`; the last-admin invariant holds under a forced race but the loser raises `OperationalError` (500) instead of 409.
- **Evidence:** `tracks/H2-isolation.md` H2-05 (`repro/H2/h2_04_admin_chain.py`).
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** Treat a missing `is_admin` as unchanged (or require an explicit hidden 0); `BEGIN IMMEDIATE` for admin mutations and map `OperationalError` to the 409 flow.
- **Effort:** S
- **Related:** Q-025
- **Verification:** H2-05 not verified by V3 (Low).

### Q-064 — 500 responses skip the security-header and no-store middleware; exception text bypasses log redaction
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** D / `security-control`
- **Track aliases and calibration:** D-03 Low; D-09 Low
- **Calibration note:** H4 reproduced the D-02 pre-auth 500 (non-ASCII CSRF token on `/auth/login`, see Q-023) live behind Caddy: HTML 500 with the full security headers and a CSP (Caddy's `handle_response @html` adds them), generic body, no traceback. Behind Caddy the baseline headers are therefore present on 500s; the gap remains in the app itself (direct access, tests, any other proxy). Stays Low.
- **Location(s):** `web/errors.py:117-125,155-156`; `web/app.py:187-199`; `logging.py:25-55,77-90`
- **Description:** The catch-all handler responds outside the header middleware, and redaction works on structured keys only so exception messages carrying user input are logged verbatim.
- **Evidence:** `tracks/D-security.md` D-03, D-09; `tracks/H4-infra.md` section 2 (`repro/H4/out_error_path.txt`).
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** One pure-ASGI middleware registered outermost for the baseline headers and no-store, plus a test that forces a 500 and asserts all headers; fix exceptions at the source (Q-023) and log only the exception type and frame for `ValueError`/`InvalidOperation`.
- **Effort:** S
- **Related:** ADR-0078; Q-023
- **Verification:** Not sampled by V1/V2/V3.

### Q-065 — CSP exists only at the proxy; the app trusts a client-supplied nonce and carries dead nonce and `csrf_token` stubs
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** D/E / `security-control`
- **Track aliases and calibration:** D-08 Low; E-11 Low
- **Location(s):** `web/middleware/security_headers.py:41-78`; `terraform/cloud-init/compose/Caddyfile.tpl:49-54`; `deploy/Caddyfile:5-8`; `web/rendering.py:39,59`, `web/errors.py`, `web/templating.py:182-185,219`, `templates/base.html:9,44`
- **Description:** The app sends no CSP and inherits a nonce header from the client; the nonce is unused by any template; a `csrf_token` global returns an empty string.
- **Evidence:** `tracks/D-security.md` D-08; `tracks/E-frontend.md` E-11.
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** Emit the CSP from `SecurityHeadersMiddleware` (app-generated nonce, inbound header ignored, Caddy stays a second layer) with a test; remove the `csrf_token` stub and the unused `csp_nonce` context key, render the meta tag unconditionally from `request.state`.
- **Effort:** M
- **Related:** ADR-0036, requirements 6.7; Q-053
- **Verification:** Not sampled by V1/V2/V3.

### Q-066 — Declared-but-unenforced and exposed surfaces: `BUDGET_TRUSTED_HOSTS` never enforced; `/docs`, `/openapi.json` and `/dev/components` live in production
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** D / `config-drift`
- **Track aliases and calibration:** D-07 Low; D-12 Low
- **Calibration note:** H4 (live drill): unauthenticated requests to `/docs`, `/openapi.json`, `/redoc` and `/dev/components` all return 302 to `/auth/login`, so there is no anonymous exposure; only an authenticated session (single owner today) could reach them. Authenticated reachability was not tested (OQ-34). Stays Low; impact is authenticated exposure only.
- **Location(s):** `config.py:54-57,169-176`; `terraform/cloud-init/compose/docker-compose.yml.tpl:23`; `web/app.py:168,187-199`; `web/routers/dev_components.py:17-27`
- **Description:** The setting exists and is set in prod but no `TrustedHostMiddleware` is registered; schema and dev pages are reachable (authenticated).
- **Evidence:** `tracks/D-security.md` D-07, D-12; `tracks/H4-infra.md` sections 1 and 3 (D-12 note).
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** Register Starlette `TrustedHostMiddleware(allowed_hosts=settings.trusted_hosts)` when non-empty; register `dev_components` only when `settings.env != "production"` and build the app with `docs_url=None, openapi_url=None` in production.
- **Effort:** S
- **Related:** T-D07, ADR-0079; operator Q: docs routes intended in prod? (OQ-21)
- **Verification:** Not sampled by V1/V2/V3; H4 verified the unauthenticated redirect live.

### Q-067 — Docker-published ports bypass ufw; the tailnet-only drill relies on the cloud security group alone
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** D / `infra-exposure`
- **Track aliases and calibration:** D-11 Low
- **Calibration note:** H4 verified the mechanism on the live drill: Docker publishes `0.0.0.0:443` (tcp and udp) past ufw, but from the public side the barrier held (see Evidence). Stays Low; the controlling layer (probably the provider security group) is unconfirmed.
- **Location(s):** `terraform/cloud-init/compose/docker-compose.yml.tpl:125-130`; `terraform/cloud-init/bootstrap.yaml.tpl:125-135,238` (re-check at remediation)
- **Description:** Caddy publishes 80/443 on all interfaces and `daemon.json` lacks `"iptables": false`, so the ufw rule for tailscale0 does not filter published ports.
- **Evidence:** `tracks/D-security.md` D-11; `tracks/H4-infra.md` section 1 and Notes (`repro/H4/out_net_probe.txt`, `out_host_probe.txt`): on the drill only 22 and 443 (plus tailscaled peerapi 47390 on the tailnet) are open and 8000 is not published; from the laptop the drill's public IP is filtered on 22/80/443/2019/8000; ufw does not govern the DNAT'd published port, so the only barrier observed is upstream of the VM (likely the provider security group, not provable from inside).
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** Bind the Caddy ports to the tailnet address for the drill (Terraform variable) or filter in the `DOCKER-USER` chain beside the metadata guard; update ADR-0101 to say where the control sits.
- **Effort:** S
- **Related:** ADR-0094, ADR-0101; OQ-32
- **Verification:** H4: mechanism Confirmed live; not exploitable from the internet in this run. No independent re-verification (drill torn down). Mitigation unchanged and concrete: publish `100.x:443:443` instead of relying on the security group.

### Q-068 — Pinning gaps: mutable Caddy/Litestream/base-image tags, floating `uv`/tailscale/cloud-init versions, Actions repo settings weaker than the runbook
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** D/H1 / `dependency`
- **Track aliases and calibration:** D-10 Low; H1-09 Low; H1-10 Low; H4-04 Low
- **Location(s):** `terraform/cloud-init/compose/docker-compose.yml.tpl:4,60,77,102,122`; `Dockerfile:9,24,43`; `.github/workflows/ci.yml:25`, `security.yml:50,111,126`, `terraform.yml:135-137,337`, `drill.yml:213`; `.github/workflows/README.md` (`uptime.yml` row); `repro/H1/gh_api/actions_permissions.json`, `actions_fork_pr.json`
- **Description:** Pinned action SHAs do not pin what they download; images are tags; `sha_pinning_required` is false and fork-PR approval covers first-time contributors only; the compose comment claims a digest pin.
- **Evidence:** Track sections of the aliases (see Details of each alias in the track files); `tracks/H4-infra.md` H4-04 (live: the rendered compose pins `caddy:2.8` and `litestream/litestream:0.3.14` by tag on lines 60, 77, 102, 122 while the app is `tag@sha256`; running digests recorded in `repro/H4/out_host_probe.txt`; Caddy terminates TLS and carries the CSP logic, so a rebuilt tag changes it without a repo diff and `restore-drill` and prod could run different digests).
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** Pin `caddy`, `litestream` by `@sha256:` digest (the host agent can verify), the base image digest and `uv`; pin tailscale and `cloud-init` versions; set `sha_pinning_required: true`, `allowed_actions: selected`, fork approval for all outside collaborators; test that every `uses:` is a SHA; fix or remove the README row.
- **Effort:** S
- **Related:** ADR-0036, ADR-0103, ADR-0111, ADR-0099; re-check workflow lines after the T-D158 merge
- **Verification:** Not sampled by V1/V2/V3; H4-04 Confirmed live.

### Q-069 — Release `ci` job runs third-party installers with write-capable tokens; `.security-allowlist.yml` is read from the PR checkout and reaches a `run:` line unescaped
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** H1 / `ci-trust-boundary`
- **Track aliases and calibration:** H1-07 Low; H1-08 Low
- **Location(s):** `.github/workflows/release.yml:27-31,76-79`, `ci.yml:16-86`, `security.yml:62-75`, `.security-allowlist.yml`
- **Description:** A called workflow without `permissions` inherits `packages: write`, `id-token: write`, `pull-requests: write`; a crafted `cve` entry injects shell and extra `GITHUB_OUTPUT` keys (job has `contents: read`, no secrets).
- **Evidence:** `tracks/H1-ci-supply-chain.md` H1-07, H1-08 (`repro/H1/allowlist_injection.out`, `gate_and_signing_probe.out` section 4).
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** `permissions: contents: read` on `ci.yml` and the `ci` job of `release.yml`, grant the rest per job; pass the allowlist through `env:` and a validated array (`^[A-Za-z0-9-]+$`) and read it from `origin/main`.
- **Effort:** S
- **Related:** Q-041, Q-040, Q-043
- **Verification:** Not sampled by V1/V2/V3.

### Q-070 — Credit-card utilisation computed in three templates plus the router; hard-coded `10` default month and `'PLN'` fallbacks in templates
- **Severity / Confidence:** Low / Probable
- **Track / root cause:** E / `template-logic`
- **Track aliases and calibration:** E-06 Medium -> Low (verifier); E-09 Low
- **Location(s):** `partials/accounts/_card.html:3-7`, `_row.html:17-19`, `accounts/index.html:77-79`, `routers/accounts.py` (`_uses_available`); `partials/budget/_override_form.html:8`, `_partials/components/_heatmap_cell.html:1-3`, `partials/recurring/_row.html:38,41,45` and others listed in E-09
- **Description:** Copies with slightly different guards; a missing account silently renders PLN and a missing month defaults to October.
- **Evidence:** `tracks/E-frontend.md` E-06, E-09.
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** One `credit_utilisation(card)` returning `used_minor, available_minor, used_pct` in the accounts view model; the view model supplies `currency` and month and templates fail (StrictUndefined) instead of defaulting.
- **Effort:** S
- **Related:** ADR-0107, T-D52; Q-039
- **Verification:** V2: E-06 Confirmed, Medium to Low. E-09 not sampled.

### Q-071 — `passkeys.js` duplicates the login and re-auth flows and swallows every error
- **Severity / Confidence:** Low / Probable
- **Track / root cause:** E / `duplicate-logic`
- **Track aliases and calibration:** E-10 Low
- **Location(s):** `static/js/passkeys.js:21-24,65-72,111-192,240-244`; `static/htmx-csrf.js:26-30`
- **Description:** About 35 identical lines differ only in URL and message; `resp403` tests an error string; failures (including user-cancelled `NotAllowedError`) map to one generic message with no console trace.
- **Evidence:** `tracks/E-frontend.md` E-10.
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** Extract `runAssertion(beginUrl, finishUrl, status, errorMsg)`, share `csrfToken()` via a tiny `csrf.js`, log `err.name` to `console.debug`, rename `resp403` to `isReauthRequired`.
- **Effort:** S
- **Related:** ADR-0067
- **Verification:** Not sampled by V1/V2/V3.

### Q-072 — Dead code kept alive: legacy redirects and aliases past expiry, symbols used only by tests, `bulk-select.js` (no markup, would omit the CSRF header if revived)
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** E/G / `dead-code`
- **Track aliases and calibration:** G-11 Low; G-17 Low; E-08 Low
- **Location(s):** `web/routers/analytics.py`, `routers/budget.py:306`, `categories.py:22`, `planned.py:55`, `recurring.py:58`, `transactions.py:113`, `plan.py:284`, `today.py:175`, `web/templates/partials/_nav.html:26,31`; `repositories/rate_limit.py:36`, `web/htmx.py:13,31`, `web/rendering.py:51`, `domain/accounts.py:97`, `config.py:52`, `web/charts.py:414-415`, `services/planned.py:37`; `static/js/bulk-select.js:62-70` (loaded at `templates/base.html:74`); `services/fx.py:119` `convert` (test-only caller)
- **Description:** Aliases kept past their stated expiry, helpers referenced only by tests, a script with no markup.
- **Evidence:** `tracks/G-drift.md` G-11, G-17; `tracks/E-frontend.md` E-08; `baseline/vulture.txt`.
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** One cleanup task: remove the redirects, `routers/analytics.py`, the `/afford` and `/budget-legacy` aliases, update `_ROUTER_NAMES` and `extra_paths`; delete the listed symbols and their tests; delete `bulk-select.js` and its `<script>`; add a vulture whitelist and run `vulture` at 80 percent confidence in `just lint`.
- **Effort:** S
- **Related:** ADR-0107; Q-038
- **Verification:** Not sampled by V1/V2/V3.

### Q-073 — Router registration swallows `ImportError`: a router that fails to import is silently skipped
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** C/G / `silent-fallback`
- **Track aliases and calibration:** C-20 Low; G-14 Medium
- **Calibration note:** G-14 orig Medium, C-20 Low: Low (trivial fix, integration tests hit the routes).
- **Location(s):** `web/app.py:236-247` (`except ImportError: continue  # pragma: no cover`)
- **Description:** A broken import removes a feature instead of failing startup, and the branch is excluded from coverage.
- **Evidence:** `tracks/G-drift.md` G-14; `tracks/C-correctness.md` C-20.
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** Replace the loop by explicit imports and `include_router` calls (no `importlib`, no `try`).
- **Effort:** S
- **Related:** Q-072
- **Verification:** Not sampled by V1/V2/V3.

### Q-074 — Small layering and functional-first deviations: module-level mutable state, two SQL queries in a service, `web -> db` contract broken by five modules, docstrings contradicting soft-delete
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** B / `layer-leak`
- **Track aliases and calibration:** B-13 Low; B-14 Low; B-15 Low; B-16 Low
- **Location(s):** `repositories/_shared.py:98` (`_TX_DEPTH` keyed by `id(conn)`), `services/recurring_formula.py:240`, `web/routers/recurring.py:78`; `services/accounts.py:35-53,63-80`; `web/app.py:59`, `web/routers/health.py:53,64`, `web/deps.py`, `web/middleware/auth.py`, `web/retention_task.py:16`; `services/accounts.py:33`, `services/balance.py:65`
- **Description:** Minor deviations from ADR-0021/0022 and wrong sentences about soft-delete.
- **Evidence:** `tracks/B-layering.md` B-13 to B-16.
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** `ContextVar` for transaction depth; `MappingProxyType` for `_EMPTY_TERM_INPUT`; ADR-0021 sentence on framework classes and memo parameters; `snapshots_repo.latest_taken_at_by_account` and `transactions_repo.latest_operation_date_by_account`; `db/health.py` for the PRAGMA probes and an import contract; fix the two docstrings.
- **Effort:** S
- **Related:** ADR-0021, ADR-0022; Q-045
- **Verification:** Not sampled by V1/V2/V3.

### Q-075 — Tier resolution has two implementations and the receiving screens use three different 'monthly average' definitions
- **Severity / Confidence:** Low / Probable
- **Track / root cause:** A / `duplicate-logic`
- **Track aliases and calibration:** A-20 Low; A-22 Low
- **Location(s):** `services/budget.py:183,603,515-523`, `web/routers/budget.py:99,206`, `services/analytics.py:152`, `_mean_minor` in `budget.py:240` and `analytics.py:138`
- **Description:** Parity holds today (`inv_08a` PASS); averages divide by active months, months elapsed or always 12 (intent unverified).
- **Evidence:** `tracks/A-duplication.md` A-20, A-22.
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** New `services/aggregates.py` (`mean_minor`, `sum_by_category(txns, to_base)`) and one pure `pick_tier(one_off, recurring, default)`; document one average definition after the operator decides.
- **Effort:** S
- **Related:** ADR-0056, ADR-0041; Q-008; operator Q: averages intentional? (OQ-7)
- **Verification:** Not sampled by V1/V2/V3.

### Q-076 — No single rounding policy (HALF_UP, HALF_EVEN, float `round()`, floor division) and retention window compares mismatched timestamp formats
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** C / `money-arith`
- **Track aliases and calibration:** C-18 Low; C-19 Low
- **Location(s):** `domain/money.py:198-207`, `services/recurring_formula.py:68,135`, `services/fx.py:142,164`, `services/today.py:50`, `web/routers/today.py:141`, `web/routers/ledger.py:363`, `web/today_data.py:157`; `repositories/planned.py:254`, `categories.py:56`, `transactions.py:266`, `repositories/_shared.py:35`
- **Description:** HALF_UP on input and formulas versus HALF_EVEN on conversion is deliberate but undocumented and implemented ad hoc; `deleted_at > datetime('now', ?)` compares formats with `T` vs space and ms vs us.
- **Evidence:** `tracks/C-correctness.md` C-18, C-19.
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** `domain/money.py` exports `round_div` (HALF_EVEN) and `round_scaled`; document the policy in ADR-0006; compare with `strftime('%Y-%m-%dT%H:%M:%fZ','now',?)` and one precision (`utc_now_iso`).
- **Effort:** S
- **Related:** ADR-0006, ADR-0007; Q-011
- **Verification:** Not sampled by V1/V2/V3.

### Q-077 — Test hygiene: duplicated tests and fixtures, 15 permanently skipped pre-redesign tests, tests with no meaningful assertion
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** F / `weak-assertion`
- **Track aliases and calibration:** F-23 Low; F-24 Low; F-25 Low; F-26 Low
- **Location(s):** `tests/e2e/test_accessibility.py:24-31`; `conn` fixture in `tests/integration/conftest.py:54`, `tests/unit/services/conftest.py:17`, `tests/unit/repositories/conftest.py:23` and ten bcrypt-cost patches; `tests/integration/web/test_accounts.py` (10 skips), `test_settings.py` (4), `tests/e2e/test_credit_card_journey.py`; no-assert tests `tests/integration/web/test_fab.py:23`, `tests/unit/deploy/test_host_release.py:430`, `tests/unit/repositories/test_transactions.py:80`, `tests/unit/web/test_production_assertions.py:47`
- **Description:** Redundancy and skipped dead tests (the v1 layout is superseded, ADR-0107) slow the suite and hide signal.
- **Evidence:** `tracks/F-tests.md` F-23 to F-26 (`repro/F/redundant_candidates.out`).
- **Impact:** Low impact: maintainability or defence in depth.
- **Mitigation:** Delete the e2e landmarks test and one of the duplicate promotion tests; move `conn` and an autouse fast-bcrypt fixture to `tests/conftest.py` and route URLs through `sqlite_url` (also helps Q-060); delete or rewrite the 15 skips with the redesign; add assertions to the four tests.
- **Effort:** S
- **Related:** ADR-0108, ADR-0107
- **Verification:** Not sampled (F Lows).

### Q-078 — Unauthenticated status endpoints disclose the exact running image ref and digest, deploy generation, restore result and replica generation
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** H4 / `infra-exposure`
- **Track aliases and calibration:** H4-02 Low
- **Location(s):** Caddy `handle /.well-known/bp-deploy-status.json` (file server on `/srv/bp-status`), `/health` (version string), `/health/replication`
- **Description:** On the live drill the unauthenticated deploy-status JSON returns the full `desired_ref` and `running_ref` including the image digest and short sha, the deploy `generation` hash, `restore.result`, `updated_at` and `error`; `/health/replication` returns `generation`, `newest_object_at` and `age_seconds`. No secrets.
- **Evidence:** `tracks/H4-infra.md` H4-02 (`repro/H4/out_http_probe.txt`).
- **Impact:** Tailnet peers learn the exact running commit and digest (target selection) and whether a restore happened. Tailnet-only, so defence in depth.
- **Mitigation:** Keep the status JSON for the CI monitor but trim it to `state`, `generation` and a short ref, or require a deploy token header at Caddy for that path; or accept it and record the decision in ADR-0111.
- **Effort:** S
- **Related:** ADR-0111; Q-035 (`/ready`)
- **Verification:** Confirmed by live repro on drill 44609305750; not independently re-verified (drill torn down; evidence is the recorded redacted output).

### Q-079 — Hardening is app-only: Caddy and the three Litestream containers run as root with a writable rootfs and no dropped capabilities, and the flat `edge` network lets them reach the app
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** H4 / `security-control`
- **Track aliases and calibration:** H4-05 Low
- **Location(s):** rendered `docker-compose.yml` (`terraform/cloud-init/compose/docker-compose.yml.tpl`); host `daemon.json`
- **Description:** `docker inspect` on the drill: the app runs as user 10001 with a read-only rootfs; Caddy, litestream and litestream-probe run as root with `ro=false` and `caps_drop=[]`. `icc:false` affects only the default bridge, so from the probe container `http://budget-planner-app:8000/health` returns 200. `no-new-privileges` is set at daemon level.
- **Evidence:** `tracks/H4-infra.md` H4-05 (`repro/H4/out_host_probe.txt`).
- **Impact:** A compromise of Caddy or a Litestream container (the latter hold bucket write keys and the age identity) yields root-in-container, write access to the replica and no network segmentation from the app.
- **Mitigation:** Add `read_only`, `cap_drop: [ALL]` and `user:` where the images allow; put the Litestream services on a separate network from the app.
- **Effort:** M
- **Related:** Q-012, Q-068
- **Verification:** Confirmed by live repro on drill 44609305750; not independently re-verified (drill torn down).

### Q-080 — The initial admin password and the cookie secret stay in the app container environment for its lifetime and are readable via `docker inspect` by any `docker` group member
- **Severity / Confidence:** Low / Confirmed
- **Track / root cause:** H4 / `infra-exposure`
- **Track aliases and calibration:** H4-06 Low
- **Location(s):** the initial-admin-password, cookie-signing and database-URL variables in the app container env (names in `tracks/H4-infra.md` only); rendered compose; `bp-config`; Terraform state
- **Description:** The variables are not removed after the first login (the seeded admin shows `must_change_password: true` in audit row 1). The app container cannot read the age key or bucket keys (its mounts are `/data` and `/replication` read-only). `operator` is in `sudo` (passwordless) and `docker`, so operator equals root on the host.
- **Evidence:** `tracks/H4-infra.md` H4-06 and section 3 (values redacted at source in `repro/H4/out_host_probe.txt`).
- **Impact:** Readable by any `docker` group member and recurs in `bp-config` and Terraform state. The initial password is valid only until the forced change, so the exposure is bounded; the cookie secret is longer-lived.
- **Mitigation:** Seed via a one-shot container or file that is removed, or drop the variable from the rendered compose after first login (host-agent generation bump).
- **Effort:** S
- **Related:** Q-012 (same host-root root cause)
- **Verification:** Confirmed by live repro on drill 44609305750; not independently re-verified (drill torn down).

## Dismissed

No finding was **Rejected** by V1, V2 or V3 (0 of 58 verification verdicts). Items below are out of scope or not findings.

| Item | Disposition | Reason |
|---|---|---|
| G-12 Orphan templates and a duplicated partial tree (13 files; E notes 15 unreferenced templates) | `superseded-by-ADR-0107` | Markup is out of scope after the Sourdough redesign (ADR-0107); the redesign replaces every template. The guard idea (an architecture test that every template is referenced) is kept in the redesign brief, not as a finding. |
| Track E markup, CSS tokens, duplicate partials, presentational JS, the 49 `style=` attributes, `numeric-input.js` and the other presentational form helpers | `superseded-by-ADR-0107` | Out of scope per ADR-0107 (plan section 3 Track E). Only logic-in-templates, HTMX contracts, CSRF/CSP and kept behaviour JS were recorded. |
| Admin password reset equals account takeover (D section 6) | Accepted documented risk | v3 position (requirements 6.8, ADR-0078 section 8, ADR-0079 A1), closed by v4 envelope encryption. Not rediscovered by H2/H3. |
| `/debug/audit-tail` shows cross-user metadata to admins (D section 6) | Accepted documented risk | ADR-0078 section 1; payloads of other users are replaced by a placeholder (verified by H2). |
| Replica age identity stored next to the database (D section 6) | Accepted documented risk | ADR-0078 section 3. |
| pip-audit: three `cryptography 48.0.1` advisories (D section 4) | Not a finding | `uv.lock` selects 48.0.1 only for darwin x86_64 (dev); Linux and the image resolve 50.0.2 with the fixes. |
| bandit B608 x51, B704 x4, B101 x3; detect-secrets 8 hits; semgrep 0 | Not findings | Triaged as false positives in D section 4. |
| Silent 200 on foreign-id deletes (D section 6) | Not a finding | Behaves like a nonexistent id (no oracle); only inconsistent with the 404s elsewhere. |
| Verified clean under attack (H2 section 2, H3 section 3, D sections 3, 6) | Not findings | Cross-user reads (2,777 requests, 0 leaks), IDOR matrix (43 routes), session fixation, replay, re-auth, enumeration timing, open redirect, CSRF on all unsafe verbs: no defect. |

## Verification status

| File | Scope | Result |
|---|---|---|
| `verification/V1.md` | A, B, C: 18 Critical/High + 8 sampled Mediums | 22 Confirmed, 2 Probable, 0 Rejected; Criticals A-01, B-01, C-01 reclassified High (latent) |
| `verification/V2.md` | D, E, G, H1, H3: 7 Critical/High + 5 sampled Mediums | 11 Confirmed, 1 Probable, 0 Rejected; G-01 Critical to High |
| `verification/V3.md` | F, H2: 14 High + 4 sampled Mediums + 2 bonus | 19 Confirmed, 1 Probable (F-09, stays High), 0 Rejected; F-01 and F-13 High to Medium; H2-01 = D-01 |
| `tracks/H4-infra.md` | Infrastructure exposure (live explore drill 44609305750, Step 0 clean) | 6 findings Confirmed by live repro (H4-01 and H4-03 Medium by the track, 4 Low); 0 Critical, no prod data on the drill. No independent re-verification pass was done for H4: the drill is torn down, so the evidence is the recorded redacted output in `repro/H4/` and the Mediums are proven by the drill run itself. |
