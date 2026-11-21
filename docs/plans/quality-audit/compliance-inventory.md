# Full-compliance principles inventory (T-Q14b)

> Deliverable: complete inventory of every violation of the project's architectural principles, per principle, on the current `audit/quality` tree.
> Status: DOCS ONLY. No source, test, config, `prevention.md`, `findings.md` or `tasks.md` is changed by this file.
> Operator ruling (2026-11-20): *converge the architecture to FULL compliance with the principles (DRY, functional paradigm, no side effects, ...). No violations in the codebase, not only the ones that caused bugs. Tighten development rules to prevent drift.*
> Purpose: (a) each automated guard's allowlist (`prevention.md` section 2, allowlist format in 2.1) starts as the **complete** list below; (b) the remediation backlog burns every entry down to zero.

## 0. Method, tree identity, how to regenerate

- **Tree**: `src/` of `audit/quality` is byte-identical to `AUDIT_SHA 9fb18cb` (`git diff 9fb18cb HEAD -- src` is empty). 120 Python files, 22 254 lines; 110 templates; kept JS: `htmx-csrf.js`, `passkeys.js` (ADR-0107 section 2; `users-admin.js` conditional).
- **Detection**: every count comes from a committed, deterministic, stdlib-only script under `docs/plans/quality-audit/repro/inventory/` (AST + regex; nothing is imported or executed from `src`; `data/budget.sqlite` is never opened). Run `bash docs/plans/quality-audit/repro/inventory/run_all.sh` from the repo root; it rewrites `docs/plans/quality-audit/inventory/*.txt` (sorted, tab-separated `path:line<TAB>rule<TAB>detail`, header lines explain the rule) and `inventory/SUMMARY.txt` (counts per rule and package). A second run produces no diff.
- **Generated files** (the complete lists; the tables below inline them when under ~100 rows, otherwise they summarise): `p01-clones-ast`, `p01-same-name`, `p01-pylint`, `p01-jscpd`, `p02-functional`, `p03-immutability`, `p04-side-effects`, `p05-thin-web`, `p05-thin-web-thin-ok`, `p06-sql-outside-repos`, `p06-unaudited-mutations`, `p06-read-filters`, `p07-clock`, `p07-clock-sql`, `p07-clock-migrations`, `p08-money`, `p09-layering`, `p09-lazy-imports`, `p10-size`, `p10-radon`, `p11-suppressions`, `p12-templates`, `p12-js-kept`, `p13-other`, `p13-repeated-literals-all`.
- **Counting convention**: a *violation* is one row in the generated file after removing rows tagged `:canonical` (inside the file that is the canonical home today) and rows whose disposition below says `accept`. Columns "raw rows" and "to remediate" are both given where they differ. Heuristic rules over-approximate; every table has a disposition so a reviewer can overrule. Known limits are in section 17.
- **Cross-references**: Q-ids are `findings.md`; `A-xx` / `B-xx` are `tracks/A-duplication.md` / `tracks/B-layering.md`; `G#`/`S#`/`R#` are `prevention.md` section 2. "NEW Gx" are guards this inventory adds (section 15).

## 1. Summary

Counts are over the current tree. "Raw" = generated rows; "Remediate" = rows that need a code change to reach zero (excludes framework-imposed and canonical-home rows, which instead get a *named* allowlist category). Effort is for **full convergence** (every row to zero or to a justified, reason-tagged allowlist entry), S = under 1 agent-day, M = 1-3, L = 3+ or touches many files with behaviour risk.

| # | Principle | Violations (current tree) | Guard (existing / NEW) | Q-ids | Effort (full convergence) |
|---|---|---|---|---|---|
| 1 | DRY / single source of truth | 13 concepts / ~75 copies (Track A); 9 identical-body groups (38 functions); 19 pylint blocks (15 real incl. mechanical, 4 boilerplate); 17 jscpd clones (2 in kept JS); 94 domain literals | G6 + S1 (money/FX/period/sign only); **NEW G18** clone ratchet, **NEW G19** literal registry | Q-002, Q-003, Q-007..Q-010, Q-023, Q-029, Q-030, Q-032, Q-036, Q-038, Q-071, Q-075, Q-076 | L |
| 2 | Functional-first (ADR-0021) | 53 raw; 25 to remediate (13 mutable constants, 2 globals, 2 hidden caches, 2 plain + 6 framework classes) | none; **NEW G20** | Q-074, B-13 | S |
| 3 | Immutability | 20 raw; 6 to remediate (14 framework-required) | none; **NEW G20** (rule set b) | Q-074, B-13 | S |
| 4 | No side effects in pure layers | 61 rows: domain 0; services 52; web view-models 5 (+4 router reach rows) | G1 (imports only); **NEW G22** purity guard | Q-007, Q-031, Q-074 | M |
| 5 | Thin web / fat services | 88 router functions with logic (of 212), 66 non-route helpers living in routers | G1 (routers not repositories); **NEW G23** router-logic ratchet | Q-003, Q-004, Q-010, Q-024, Q-028, Q-039, Q-045, Q-046, Q-070, B-01..B-05 | L |
| 6 | Repository discipline | 6 real SQL statements outside repositories (14 literal rows); 50 bootstrap rows; 3 unaudited domain mutations (+13 on exempt tables); 20 reads w/o filter (+4 flagged-intentional) | G2, G8, G7b (existing user-id test); **NEW G24** read-filter guard | Q-024, Q-025, Q-049, Q-074, B-11, B-14 | M |
| 7 | Clock / time (ADR-0007) | 45 Python call sites (+38 SQL-side); 20 naive host-clock | G3 + S4 (single clock) | Q-031 | M |
| 8 | Money (ADR-0008/0006) | 78 non-canonical code rows (+55 float-geometry rows reviewed, not counted) + 83 template sites | G6, G9, S1 | Q-005, Q-007, Q-011, Q-022, Q-029, Q-036, Q-076 | L |
| 9 | Layering / imports | 42 contract-breaking imports + 1 cycle (3 modules); 4 extra-contract rows; 37 lazy imports (PLC0415); 3 E402 | G1, G4 (ceilings) | Q-045, Q-047, Q-074, B-12, B-15 | M |
| 10 | Signatures / size | 41 functions > 50 lines; 2 files > 800 (+14 > 400); 33 functions radon C+; 32 PLR0917; 66 > 5 params; 3 nesting > 4 | G4 (PLR0917 ceiling) only; **NEW G25** size/complexity ratchet | Q-046, Q-047, Q-048 | L |
| 11 | Suppressions | 155 inline (121 noqa, 27 pragma no cover, 5 type: ignore, 1 nosec, 1 fmt: skip); 94 without a same-line reason; 9 pyproject suppressions | G4, G5 | Q-014, Q-046, Q-048 | M |
| 12 | Logic in templates (counts only; ADR-0107 replaces all) | 457 sites in 69 files | G9 (new templates start at zero) | Q-011, Q-039, Q-070 | n/a (redesign) |
| 13 | Other stated principles | literal user id 4; swallowed errors 22; broad except 9; assert in src 32; print 2; Any in signatures 80; magic numbers 20 | G7b (literal id); **NEW G26** error-handling/hygiene | Q-001, Q-073 | M |

## 2. Principle 1: DRY / single source of truth

**Definition.** Every domain rule, helper and domain literal has exactly one implementation; consumers reuse it. Copies that differ in policy are the dangerous case (Track A). Mechanical copies (identical bodies) are the cheap case.

**Detection.** (a) Track A concept map (13 concepts, `grep` + manual diff, section 2.1). (b) `p01_dry.py`: AST type-2 clone detection (function bodies with identifiers and constants normalised, >= 4 statements and >= 8 lines), and same-name functions across modules. (c) `pylint duplicate-code` and `jscpd` baselines (identical src), triaged by hand. (d) `p13_other.py`: domain string literals and repeated literals. (e) router-local helpers (section 6, `helper-in-router`).

### 2.1 Concept map (Track A): every concept with more than one implementation

| # | Concept | Implementations (`path:line`) | Copies | Findings | Canonical home / guard |
|---|---|---|---|---|---|
| 1 | FX conversion + rate lookup | `services/fx.py:119,146`; `services/forecast.py:221`; `web/today_data.py:90`; `services/budget.py:55,88`; `web/routers/ledger.py:273` (+ `_collect_fx_rates` forecast.py:204, today_data.py:119) | 6 + 2 collectors | Q-007, Q-008, A-06 | S1/G6 `services/fx.py` one converter + explicit policy |
| 2 | Minor-unit parse / format / exponent | `domain/money.py` (canonical) vs router parsers `transactions.py:223`, `planned.py:209`, `accounts.py:171,203,474`, `budget.py:316`, `recurring.py:232,846,1043`, `today.py:126`; `forecast.py:956`; `plan.py:36`/`forecast.py:31` `_MINOR_UNITS_PER_MAJOR`; 62 template sites | 7 parsers, 3 scale constants | Q-011, Q-023, Q-029, Q-076, A-08, A-09 | G6/G9 |
| 3 | Signed amount from direction | `balance.py:42`, `ledger_totals.py:22`, `forecast.py:128,751,770`, `account_planned.py:74`, `transactions.py:145`, `analytics.py:202`, SQL `repositories/transactions.py:98`, templates | 6 + templates | Q-036, A-10 | S1 `domain/transactions.signed_legs` |
| 4 | Account balance + fortune | `balance.py:85,122`, `fortune.py:30`, `today_data.py:105`, `forecast.py:546`, `account_planned.py:130` | 5 | Q-009, Q-032, A-07 | S1 `services/fortune.py` |
| 5 | Period / month ranges / left-per-day / today | month bounds `budget.py:203`, `analytics.py:84`, `forecast.py:317`, `recurring_formula.py:123`, `account_planned.py:66`, `planned.py:86`; prev/next `budget.py:176`, `forecast.py:621`, `plan.py:96`; `budget.py:388` vs `:408`; left-per-day `budget.py:551,584`, `today.py:46,98`, template | 10+ | Q-003, Q-031, Q-039, A-05, A-13..A-15 | S1 `domain/periods.py` |
| 6 | Budget tier resolution | `budget.py:183` `resolve_budget` vs `:603` `yearly_grid`; router reads `web/routers/budget.py:99,206` | 3 | Q-075, A-20 | S1 `pick_tier` |
| 7 | Recurring expansion / next_due / overrides | `recurring.py:107,177,222`, `recurring_formula.py:322`, consumers `budget.py:296`, `forecast.py:262,373,710`, `account_planned.py:106`, `income.py:25`, `upcoming.py:74`; `next_due` seeding `recurring.py:309`, `db/migrate.py:134`, `repositories/recurring.py:227` | 7 consumers + 3 seeders | Q-002, Q-006, Q-047, Q-030, A-04, A-12, A-17, A-21 | S1 `pending_occurrences` |
| 8 | Aggregates / means | `budget.py:240` `_mean_minor`, `analytics.py:138` `_mean_minor`, `balance.py:112` `_mean`, `today.py:46`, inline `budget.py:584`, `forecast.py:409`; per-category sums `budget.py:228`, `analytics.py:123,166`, `forecast.py:322`; router totals `ledger.py:343,409` | 9 | Q-008, Q-075, A-02, A-22 | S1 `services/aggregates.py` |
| 9 | User scoping | hand-written `user_id = ?` in every repository (guard exists: `test_user_id_filter`) | n/a | Q-001 | G7b |
| 10 | Validation (amount, direction, transit) | amount parsers (concept 2); transit rule `_promotion.py:55`, `transactions.py:274`, `recurring.py:174`; zero-amount `_promotion.py:46` vs routers | 3 + 7 | Q-004, Q-023, Q-028, A-08 | service validators |
| 11 | HTMX trigger names / targets | 45 string-literal emit sites (72 literal occurrences by the AST scan, section 2.5), 7 hand-built `HX-Trigger` JSON sites; 3 listeners | 45+ | Q-038, A-18 | G12 + G19 `web/htmx.Event` |
| 12 | Category scope (archived) | live-only `budget.py:475,605`, `forecast.py:686`; include-archived `forecast.py:447`, `analytics.py:113,156,188`, `balance.py:69`, `account_planned.py:93` | 2 policies, 7 sites | Q-030, A-11 | S1 `expense_category_ids` |
| 13 | Date-string / int parsers in routers | `_parse_date`/`_parse_int` in `transactions.py:55,64`, `planned.py:33`, `recurring.py:40,49`, `ledger.py:44,53`; `budget.py:81` unguarded | 4 byte-identical + 1 divergent | Q-023, A-19 | `web/params.py` |

Status: every row above is a finding already (Q-ids) and has a differential test planned (G7); the inventory adds nothing new here except completeness checks (sections 2.2-2.6).

### 2.2 Structurally identical function bodies (AST type-2 clones): 9 groups, 38 functions

`p01_dry.py` normalises names and constants; a group means the bodies are token-for-token the same shape. All but G04 are the per-entity repository CRUD copies (accounts, categories, planned, recurring, transactions, budgets) that differ only in table/column names: the generic helper belongs in `repositories/_shared.py` parameterised by a table spec. G04 is `ledger._hydrate_txn_rows` vs `transactions._hydrate_rows` (also pylint P01).

| Group | Function | Members | Lines | Locations |
|---|---|---|---|---|
| G01 | `soft_delete` | 5 | 18 | `repositories/accounts.py:138`, `repositories/categories.py:136`, `repositories/planned.py:222`, `repositories/recurring.py:347`, `repositories/transactions.py:235` |
| G02 | `undelete` | 4 | 10 | `repositories/accounts.py:163`, `repositories/categories.py:160`, `repositories/planned.py:267`, `repositories/transactions.py:279` |
| G03 | `find_by_id` | 8 | 12 | `repositories/accounts.py:39`, `repositories/accounts.py:53`, `repositories/budgets.py:71`, `repositories/categories.py:35`, `repositories/categories.py:64`, `repositories/planned.py:54`, `repositories/recurring.py:170`, `repositories/transactions.py:55` |
| G04 | `_hydrate_txn_rows` | 2 | 23 | `web/routers/ledger.py:83`, `web/routers/transactions.py:90` |
| G05 | `update` | 3 | 37 | `repositories/planned.py:183`, `repositories/recurring.py:304`, `repositories/transactions.py:196` |
| G06 | `update` | 5 | 11 | `repositories/accounts.py:121`, `repositories/categories.py:119`, `repositories/planned.py:200`, `repositories/recurring.py:321`, `repositories/transactions.py:213` |
| G07 | `undelete` | 4 | 24 | `repositories/accounts.py:158`, `repositories/categories.py:155`, `repositories/planned.py:262`, `repositories/transactions.py:274` |
| G08 | `list_recently_deleted` | 3 | 13 | `repositories/categories.py:49`, `repositories/planned.py:247`, `repositories/transactions.py:259` |
| G09 | `list_all` | 4 | 11 | `repositories/accounts.py:67`, `repositories/budgets.py:85`, `repositories/budgets.py:177`, `repositories/categories.py:78` |

### 2.3 pylint duplicate-code blocks (19): triage

| Block | Location | Pair | Verdict | Note |
|---|---|---|---|---|
| P01 | `web/routers/ledger.py:79` | web.routers.ledger:79-110 <> web.routers.transactions:86-121 | real | ledger/transactions `_hydrate_rows`; same as clone G04 |
| P02 | `web/routers/ledger.py:44` | web.routers.ledger:44-66 <> web.routers.transactions:55-77 | real | `_parse_date`/`_parse_int` copies (A-19) |
| P03 | `web/routers/recurring.py:40` | web.routers.recurring:40-65 <> web.routers.transactions:55-74 | real | same router parsers (recurring vs transactions) |
| P04 | `repositories/planned.py:191` | repositories.planned:191-204 <> repositories.transactions:204-217 | real-mechanical | repository update/patch block (planned vs transactions) |
| P05 | `services/auth.py:437` | services.auth:437-450 <> services.reauth:121-132 | real | WebAuthn assertion verification call (auth vs reauth) |
| P06 | `web/routers/planned.py:230` | web.routers.planned:230-240 <> web.routers.transactions:249-259 | real | transit/account/category validation block in routers (planned vs transactions) |
| P07 | `repositories/accounts.py:176` | repositories.accounts:176-188 <> repositories.categories:173-185 | real-mechanical | soft_delete/undelete scaffold (accounts vs categories) |
| P08 | `repositories/planned.py:309` | repositories.planned:309-321 <> repositories.transactions:293-305 | real-mechanical | undelete scaffold (planned vs transactions) |
| P09 | `domain/planned.py:49` | domain.planned:49-63 <> domain.transactions:60-74 | boilerplate-shape | frozen-DTO field lists + `as_dict` (Planned/Transaction patches); share a base or helper |
| P10 | `services/auth.py:162` | services.auth:162-183 <> services.rate_limit:131-149 | boilerplate | `write_audit` auth-event call shape (auth vs rate_limit): one `audit_auth_event` helper would remove it |
| P11 | `repositories/recurring.py:214` | repositories.recurring:214-226 <> repositories.transactions:143-157 | real-mechanical | row-to-DTO hydration (recurring vs transactions) |
| P12 | `repositories/accounts.py:176` | repositories.accounts:176-186 <> repositories.transactions:292-302 | real-mechanical | soft_delete scaffold (accounts vs transactions) |
| P13 | `repositories/planned.py:32` | repositories.planned:32-40 <> repositories.transactions:33-41 | real-mechanical | list filter scaffold (planned vs transactions) |
| P14 | `repositories/planned.py:145` | repositories.planned:145-153 <> repositories.transactions:163-171 | real-mechanical | list_filtered tail (planned vs transactions) |
| P15 | `domain/planned.py:15` | domain.planned:15-23 <> domain.transactions:25-33 | boilerplate-shape | DTO field list (domain planned vs transactions) |
| P16 | `web/routers/planned.py:352` | web.routers.planned:352-361 <> web.routers.transactions:382-390 | real | transit validation block on update (planned vs transactions) |
| P17 | `web/middleware/auth.py:119` | web.middleware.auth:119-133 <> web.middleware.must_change_password:59-73 | real | `_wants_json` / safe-next helper copied across middleware (auth vs must_change_password) |
| P18 | `db/migrate.py:177` | db.migrate:177-184 <> repositories.recurring:106-113 | real | `next_due` seeding / rule-to-row mapping (db/migrate vs repositories/recurring; A-21) |
| P19 | `services/password_change.py:106` | services.password_change:106-113 <> services.reauth:54-61 | boilerplate | `write_audit` call shape (password_change vs reauth) |

Triage totals: 15 real (incl. 'real-mechanical'), 4 boilerplate. Verdicts are reviewer judgement from the block text; the generated file is `inventory/p01-pylint.txt`.

### 2.4 jscpd clones over templates, CSS and JS (17): triage

| Id | Kind | Clone | Disposition |
|---|---|---|---|
| J08 | markup | accounts/index.html [64:12 - 135:16] (72 lines, 717 tokens) <> partials/accounts/_row.html [4:28 - 75:6] | replaced by ADR-0107 redesign: record only; new fragments must be macros |
| J01 | css | app.css [91:10 - 100:2] (10 lines, 63 tokens) <> app.css [1289:21 - 1298:2] | replaced by ADR-0107 redesign: record only |
| J02 | css | auth.css [76:42 - 88:5] (13 lines, 107 tokens) <> settings-security.css [19:44 - 31:5] | replaced by ADR-0107 redesign: record only |
| J09 | markup | auth/_layout.html [9:40 - 22:16] (14 lines, 66 tokens) <> base.html [10:29 - 23:16] | replaced by ADR-0107 redesign: record only; new fragments must be macros |
| J03 | javascript | js/passkeys.js [118:35 - 128:27] (11 lines, 86 tokens) <> js/passkeys.js [161:36 - 171:27] | KEPT JS: real duplicate (passkeys.js login/re-auth flows, Q-071): extract one ceremony function |
| J04 | javascript | js/passkeys.js [129:40 - 143:28] (15 lines, 108 tokens) <> js/passkeys.js [172:41 - 186:28] | KEPT JS: real duplicate (passkeys.js login/re-auth flows, Q-071): extract one ceremony function |
| J10 | markup | partials/forecast/_chart.html [13:33 - 25:7] (13 lines, 139 tokens) <> plan/_forecast_tab.html [40:22 - 56:9] | replaced by ADR-0107 redesign: record only; new fragments must be macros |
| J11 | markup | partials/planned/_form.html [29:22 - 37:24] (9 lines, 54 tokens) <> partials/transactions/_form.html [46:72 - 54:24] | replaced by ADR-0107 redesign: record only; new fragments must be macros |
| J12 | markup | partials/planned/_form.html [44:71 - 53:20] (10 lines, 53 tokens) <> partials/transactions/_form.html [61:59 - 70:20] | replaced by ADR-0107 redesign: record only; new fragments must be macros |
| J13 | markup | partials/planned/_promote_inline_row.html [17:34 - 30:22] (14 lines, 110 tokens) <> partials/recurring/_promote_inline_row.html [16:62 - 29:22] | replaced by ADR-0107 redesign: record only; new fragments must be macros |
| J14 | markup | partials/planned/_promote_inline_row.html [41:26 - 56:18] (16 lines, 98 tokens) <> partials/recurring/_promote_inline_row.html [40:36 - 55:18] | replaced by ADR-0107 redesign: record only; new fragments must be macros |
| J15 | markup | partials/planned/_promote_modal.html [43:84 - 55:7] (13 lines, 67 tokens) <> partials/recurring/_promote_modal.html [56:84 - 68:7] | replaced by ADR-0107 redesign: record only; new fragments must be macros |
| J16 | markup | partials/recurring/_form.html [108:26 - 126:39] (19 lines, 126 tokens) <> partials/recurring/_form.html [232:69 - 250:31] | replaced by ADR-0107 redesign: record only; new fragments must be macros |
| J17 | markup | partials/recurring/_override_form.html [34:86 - 42:23] (9 lines, 50 tokens) <> partials/recurring/_promote_modal.html [17:83 - 25:23] | replaced by ADR-0107 redesign: record only; new fragments must be macros |
| J05 | css | rising-dough.css [138:5 - 147:2] (10 lines, 54 tokens) <> rising-dough.css [1083:2 - 1092:2] | replaced by ADR-0107 redesign: record only |
| J06 | css | rising-dough.css [147:21 - 156:24] (10 lines, 55 tokens) <> rising-dough.css [1092:17 - 1101:24] | replaced by ADR-0107 redesign: record only |
| J07 | css | rising-dough.css [510:11 - 521:2] (12 lines, 66 tokens) <> rising-dough.css [1027:9 - 1038:2] | replaced by ADR-0107 redesign: record only |

### 2.5 Domain literals and repeated literals

| Literal | Occurrences | Files |
|---|---|---|
| `'forecast-stale'` | 22 | `web/routers/accounts.py` 2, `web/routers/planned.py` 7, `web/routers/recurring.py` 9, `web/routers/transactions.py` 4 |
| `'ledger-stale'` | 20 | `web/routers/planned.py` 7, `web/routers/recurring.py` 9, `web/routers/transactions.py` 4 |
| `'budget-stale'` | 14 | `web/routers/budget.py` 6, `web/routers/categories.py` 4, `web/routers/recurring.py` 4 |
| `'balance-stale'` | 11 | `web/routers/accounts.py` 4, `web/routers/planned.py` 3, `web/routers/transactions.py` 4 |
| `'expense'` | 7 | `services/analytics.py` 3, `web/charts.py` 2, `web/routers/ledger.py` 1, `web/routers/plan.py` 1 |
| `'income'` | 7 | `services/analytics.py` 3, `web/charts.py` 2, `web/routers/ledger.py` 1, `web/routers/plan.py` 1 |
| `'PLN'` | 4 | `config.py` 1, `db/seed.py` 2, `services/forecast.py` 1 |
| `'today-stale'` | 4 | `web/routers/planned.py` 2, `web/routers/recurring.py` 2 |
| `'monthly'` | 2 | `web/routers/ledger.py` 2 |
| `'Europe/Warsaw'` | 1 | `config.py` 1 |
| `'settings-categories-stale'` | 1 | `web/routers/categories.py` 1 |
| `'yearly'` | 1 | `web/routers/ledger.py` 1 |

- HTMX invalidation events (`forecast-stale`, `ledger-stale`, `budget-stale`, `balance-stale`, `today-stale`, `settings-categories-stale`): 72 occurrences in 6 router files; target `web/htmx.py` `Event` constants + `invalidate(response, *domains)` (A-18, Q-038). New guard G19 below.
- `'PLN'` (4 in config, seed and forecast; 10 template literals) and `'Europe/Warsaw'` (1): base currency and display timezone come from `Settings`; literal fallbacks are the Q-007/Q-010/Q-070 class.
- `'income'`/`'expense'`/`'monthly'`/`'yearly'`: enum values written as strings instead of `Direction.*` / `Cadence.*` members (14 occurrences).
- Repeated non-trivial literals (>= 3 uses, >= 2 files, hyphen/slash/uppercase shapes; 30 rows in `inventory/p13-other.txt`, all >= 3 uses in `p13-repeated-literals-all.txt`): HTTP header names (`HX-Trigger` x8, `HX-Reswap`, `HX-Refresh`, `Cache-Control`, `Retry-After`, `Content-Disposition`), content types (`text/html` x17), the audit timestamp format `'%Y-%m-%dT%H:%M:%S.%fZ'` x4, template path `'partials/_slideover.html'` x13, route paths (`/ledger` x10, `/new`, `/settings`), `'utf-8'` x9, SQL transaction verbs in `db/migrate.py`.

### 2.6 Same-name functions defined in two or more modules (53 names, 167 definitions)

| Name | Defs | Modules | Disposition |
|---|---|---|---|
| `_action` | 30 | repositories/accounts, repositories/budgets, repositories/categories, repositories/fx, ... | convention: nested closure passed to `mutate` (not a violation) |
| `_append_filter_clauses` | 2 | repositories/planned, repositories/transactions | REAL: per-entity repository copies (see clone groups / G18) |
| `_hx_trigger_payload` | 2 | web/routers/planned, web/routers/recurring | REAL candidate: parallel implementation (private helper or cross-layer) |
| `_hydrate` | 4 | repositories/auth_users, repositories/sessions, repositories/webauthn, web/routers/acco... | REAL candidate: parallel implementation (private helper or cross-layer) |
| `_iso` | 2 | repositories/rate_limit, repositories/sessions | REAL: per-entity repository copies (see clone groups / G18) |
| `_mean_minor` | 2 | services/analytics, services/budget | REAL candidate: parallel implementation (private helper or cross-layer) |
| `_month_bounds` | 3 | services/analytics, services/forecast, services/recurring_formula | REAL candidate: parallel implementation (private helper or cross-layer) |
| `_normalise_patch` | 2 | repositories/planned, repositories/transactions | REAL: per-entity repository copies (see clone groups / G18) |
| `_parse_date` | 4 | web/routers/ledger, web/routers/planned, web/routers/recurring, web/routers/transactions | REAL candidate: parallel implementation (private helper or cross-layer) |
| `_parse_int` | 3 | web/routers/ledger, web/routers/recurring, web/routers/transactions | REAL candidate: parallel implementation (private helper or cross-layer) |
| `_reject` | 2 | web/middleware/csrf, web/routers/accounts | REAL candidate: parallel implementation (private helper or cross-layer) |
| `_validate_amount` | 2 | web/routers/planned, web/routers/transactions | REAL candidate: parallel implementation (private helper or cross-layer) |
| `_wants_json` | 3 | web/middleware/auth, web/middleware/must_change_password, web/routers/auth | REAL candidate: parallel implementation (private helper or cross-layer) |
| `afford` | 2 | services/today, web/routers/today | REAL candidate: parallel implementation (private helper or cross-layer) |
| `as_dict` | 5 | domain/accounts, domain/categories, domain/planned, domain/recurring, domain/transactions | REAL candidate: parallel implementation (private helper or cross-layer) |
| `audit_tail` | 2 | services/audit_tail, web/routers/debug | REAL candidate: parallel implementation (private helper or cross-layer) |
| `batch_promote_due` | 2 | services/planned, services/recurring | REAL candidate: parallel implementation (private helper or cross-layer) |
| `convert` | 2 | services/fx, web/routers/ledger | REAL candidate: parallel implementation (private helper or cross-layer) |
| `create` | 5 | repositories/accounts, repositories/categories, repositories/planned, repositories/snap... | REAL: per-entity repository copies (see clone groups / G18) |
| `create_rule` | 2 | repositories/recurring, web/routers/recurring | REAL candidate: parallel implementation (private helper or cross-layer) |
| `create_user` | 3 | repositories/users, services/users, web/routers/settings_users | REAL candidate: parallel implementation (private helper or cross-layer) |
| `deactivate_rule` | 2 | repositories/recurring, web/routers/recurring | REAL candidate: parallel implementation (private helper or cross-layer) |
| `delete_override` | 2 | repositories/recurring, web/routers/recurring | REAL candidate: parallel implementation (private helper or cross-layer) |
| `edit_form` | 6 | web/routers/accounts, web/routers/categories, web/routers/planned, web/routers/recurrin... | route handlers sharing a conventional name (not a violation unless bodies match) |
| `export` | 2 | web/routers/planned, web/routers/transactions | route handlers sharing a conventional name (not a violation unless bodies match) |
| `find_by_id` | 4 | repositories/accounts, repositories/categories, repositories/planned, repositories/tran... | REAL: per-entity repository copies (see clone groups / G18) |
| `find_by_name` | 2 | repositories/accounts, repositories/categories | REAL: per-entity repository copies (see clone groups / G18) |
| `is_exempt` | 2 | web/middleware/auth, web/middleware/must_change_password | REAL candidate: parallel implementation (private helper or cross-layer) |
| `last_checked` | 2 | services/accounts, web/routers/accounts | REAL candidate: parallel implementation (private helper or cross-layer) |
| `list_all` | 2 | repositories/accounts, repositories/categories | REAL: per-entity repository copies (see clone groups / G18) |
| `list_filtered` | 2 | repositories/planned, repositories/transactions | REAL: per-entity repository copies (see clone groups / G18) |
| `list_recently_deleted` | 3 | repositories/categories, repositories/planned, repositories/transactions | REAL: per-entity repository copies (see clone groups / G18) |
| `list_upcoming` | 2 | services/upcoming, web/today_data | REAL candidate: parallel implementation (private helper or cross-layer) |
| `logout` | 2 | services/auth, web/routers/auth | REAL candidate: parallel implementation (private helper or cross-layer) |
| `new_form` | 5 | web/routers/accounts, web/routers/categories, web/routers/planned, web/routers/recurrin... | route handlers sharing a conventional name (not a violation unless bodies match) |
| `new_override_form` | 2 | web/routers/budget, web/routers/recurring | route handlers sharing a conventional name (not a violation unless bodies match) |
| `parse_filter` | 2 | web/routers/planned, web/routers/transactions | route handlers sharing a conventional name (not a violation unless bodies match) |
| `promote_form` | 2 | web/routers/planned, web/routers/recurring | route handlers sharing a conventional name (not a violation unless bodies match) |
| `promote_inline` | 2 | web/routers/planned, web/routers/recurring | route handlers sharing a conventional name (not a violation unless bodies match) |
| `promote_submit` | 2 | web/routers/planned, web/routers/recurring | route handlers sharing a conventional name (not a violation unless bodies match) |
| `register_passkey_begin` | 2 | services/auth, web/routers/auth | REAL candidate: parallel implementation (private helper or cross-layer) |
| `register_passkey_finish` | 2 | services/auth, web/routers/auth | REAL candidate: parallel implementation (private helper or cross-layer) |
| `reset_password` | 3 | repositories/users, services/users, web/routers/settings_users | REAL candidate: parallel implementation (private helper or cross-layer) |
| `revoke_passkey` | 2 | services/auth, web/routers/auth | REAL candidate: parallel implementation (private helper or cross-layer) |
| `revoke_session` | 2 | repositories/sessions, web/routers/auth | REAL candidate: parallel implementation (private helper or cross-layer) |
| `set_default` | 2 | repositories/budgets, web/routers/budget | REAL candidate: parallel implementation (private helper or cross-layer) |
| `set_one_off` | 2 | repositories/budgets, web/routers/budget | REAL candidate: parallel implementation (private helper or cross-layer) |
| `set_recurring` | 2 | repositories/budgets, web/routers/budget | REAL candidate: parallel implementation (private helper or cross-layer) |
| `soft_delete` | 5 | repositories/accounts, repositories/categories, repositories/planned, repositories/tran... | REAL: per-entity repository copies (see clone groups / G18) |
| `table_fragment` | 3 | web/routers/ledger, web/routers/planned, web/routers/transactions | route handlers sharing a conventional name (not a violation unless bodies match) |
| `undelete` | 4 | repositories/accounts, repositories/categories, repositories/planned, repositories/tran... | REAL: per-entity repository copies (see clone groups / G18) |
| `update` | 4 | repositories/accounts, repositories/categories, repositories/planned, repositories/tran... | REAL: per-entity repository copies (see clone groups / G18) |
| `write_audit` | 2 | repositories/_shared, services/audit | REAL candidate: parallel implementation (private helper or cross-layer) |

31 names are cross-layer candidates (e.g. `_parse_date`, `_parse_int`, `_month_bounds`, `_mean_minor`, `_wants_json`, `_hx_trigger_payload`, `convert`, `write_audit`, `_validate_amount`); the rest are repository CRUD copies (clone groups) or route handlers whose bodies differ.

### 2.7 Remediation notes (DRY)

- Canonical modules S1 covers concepts 1-8, 10, 12 (prevention.md). Concepts 11 and 13 plus the repository CRUD copies, the audit-event call shape (P10, P19), the WebAuthn verification block (P05) and the middleware helpers (P17) are **not** in S1 today: add rows (`web/params.py`, `web/htmx.Event`, `repositories/_shared` generic CRUD, `services/audit.audit_auth_event`, `web/middleware/_common.py`).
- A guard cannot find semantic copies (pylint missed all FX copies). G18 (new) ratchets the mechanical ones; S1 plus the differential invariants (G7) cover the semantic ones.

## 3. Principle 2: Functional-first (ADR-0021)

**Definition.** Services and repositories are modules of pure functions. Allowed classes: frozen dataclasses, `NamedTuple`/`TypedDict`, `Protocol`, `Enum` family, exception subclasses, pydantic `BaseModel`/`BaseSettings` DTOs. Everything else, a non-frozen dataclass, module-level mutable state (`list`/`dict`/`set` literals or constructors, `global`, locks, caches) and mutable default arguments is a violation.

**Detection.** `repro/inventory/p02_functional.py` (AST). Rules: `class-plain`, `class-framework`, `dataclass-not-frozen`, `class-nested`, `mutable-constant`, `module-state`, `module-singleton`, `global-stmt`, `mutable-default`, `hidden-cache`. Result: **0** non-frozen dataclasses, 0 nested classes, 0 mutable defaults, 0 locks/ContextVars.

| Location | Rule | Detail | Disposition |
|---|---|---|---|
| `config.py:228` | hidden-cache | @lru_cache get_settings | fix: explicit memo passed or injected settings |
| `db/migrate.py:260` | mutable-constant | _POST_APPLY_HOOKS = {6: _backfill_recurring_next_due, 10: _upgrade_... | fix: tuple / frozenset / MappingProxyType |
| `domain/money.py:14` | mutable-constant | _CURRENCY_DECIMALS = {'JPY': 0, 'KRW': 0, 'HUF': 2, 'PLN': 2, 'EUR'... | fix: tuple / frozenset / MappingProxyType |
| `logging.py:63` | class-plain | _StripQueryFilter(Filter) [root] | violation (middleware class / logging.Filter); replace with function or accept as framework |
| `logging.py:103` | global-stmt | global _CONFIGURED | fix: module-level flag state |
| `repositories/_shared.py:30` | module-singleton | _EMPTY_REQUEST_CTX = RequestCtx.empty() | accept-frozen: immutable sentinel (but defined 4x: DRY) |
| `repositories/_shared.py:98` | mutable-constant | _TX_DEPTH = {} | fix: tuple / frozenset / MappingProxyType |
| `repositories/users.py:46` | module-singleton | _EMPTY_REQUEST_CTX = RequestCtx.empty() | accept-frozen: immutable sentinel (but defined 4x: DRY) |
| `repositories/webauthn.py:34` | module-singleton | _EMPTY_CTX = RequestCtx.empty() | accept-frozen: immutable sentinel (but defined 4x: DRY) |
| `services/_passwords.py:70` | hidden-cache | @lru_cache _dummy_hash_for | fix: explicit memo passed or injected settings |
| `services/audit.py:36` | module-singleton | _EMPTY_REQUEST_CTX = RequestCtx.empty() | accept-frozen: immutable sentinel (but defined 4x: DRY) |
| `services/audit.py:46` | mutable-constant | _SHAPE_RULES = {'create': (False, True), 'update': (True, True... | fix: tuple / frozenset / MappingProxyType |
| `services/export.py:82` | mutable-constant | _DTYPES = {'int': pd.Int64Dtype(), 'money_minor': pd.Int6... | fix: tuple / frozenset / MappingProxyType |
| `services/rate_limit.py:67` | module-singleton | ALLOWED = RateDecision(allowed=True) | accept-frozen: immutable sentinel (but defined 4x: DRY) |
| `services/recurring.py:39` | mutable-constant | _STEP_MONTHS = {Cadence.MONTHLY: 1, Cadence.QUARTERLY: 3, Cade... | fix: tuple / frozenset / MappingProxyType |
| `services/users.py:293` | module-singleton | _EMPTY_REQUEST_CTX = RequestCtx.empty() | accept-frozen: immutable sentinel (but defined 4x: DRY) |
| `web/app.py:86` | global-stmt | global _SIGTERM_INSTALLED | fix: module-level flag state |
| `web/app.py:250` | module-singleton | app = create_app() | accept: immutable / framework entry point |
| `web/middleware/admin.py:40` | class-framework | AdminRequiredMiddleware(BaseHTTPMiddleware) [web.middleware] | framework-imposed (BaseHTTPMiddleware); convert to pure ASGI functions to comply |
| `web/middleware/auth.py:67` | mutable-constant | _UNAUTHORIZED_BODY = {'error': 'unauthorized'} | fix: tuple / frozenset / MappingProxyType |
| `web/middleware/auth.py:68` | module-singleton | _log = get_logger('budget_planner.auth') | accept: immutable / framework entry point |
| `web/middleware/auth.py:145` | class-framework | AuthRequiredMiddleware(BaseHTTPMiddleware) [web.middleware] | framework-imposed (BaseHTTPMiddleware); convert to pure ASGI functions to comply |
| `web/middleware/cache_control.py:28` | class-plain | CacheControlMiddleware() [web.middleware] | violation (middleware class / logging.Filter); replace with function or accept as framework |
| `web/middleware/csrf.py:152` | class-framework | CSRFMiddleware(BaseHTTPMiddleware) [web.middleware] | framework-imposed (BaseHTTPMiddleware); convert to pure ASGI functions to comply |
| `web/middleware/must_change_password.py:37` | mutable-constant | _BODY = {'error': ERROR_CODE, 'location': PASSWORD_PATH} | fix: tuple / frozenset / MappingProxyType |
| `web/middleware/must_change_password.py:83` | class-framework | MustChangePasswordMiddleware(BaseHTTPMiddleware) [web.middleware] | framework-imposed (BaseHTTPMiddleware); convert to pure ASGI functions to comply |
| `web/middleware/request_id.py:26` | class-framework | RequestIdMiddleware(BaseHTTPMiddleware) [web.middleware] | framework-imposed (BaseHTTPMiddleware); convert to pure ASGI functions to comply |
| `web/middleware/security_headers.py:61` | class-framework | SecurityHeadersMiddleware(BaseHTTPMiddleware) [web.middleware] | framework-imposed (BaseHTTPMiddleware); convert to pure ASGI functions to comply |
| `web/routers/accounts.py:40` | module-singleton | router = APIRouter(prefix='/accounts', tags=['accounts']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/analytics.py:19` | module-singleton | router = APIRouter(prefix='/analytics', tags=['analytics']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/auth.py:69` | module-singleton | router = APIRouter(prefix='/auth', tags=['auth']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/budget.py:46` | module-singleton | router = APIRouter(prefix='/budget', tags=['budget']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/categories.py:19` | module-singleton | router = APIRouter(prefix='/categories', tags=['categories']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/debug.py:20` | module-singleton | router = APIRouter(prefix='/debug', tags=['debug'], include_in_sch... | accept: framework idiom (`router = APIRouter`) |
| `web/routers/dev_components.py:17` | module-singleton | router = APIRouter(tags=['dev']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/forecast.py:26` | module-singleton | router = APIRouter(prefix='/forecast', tags=['forecast']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/health.py:29` | module-singleton | router = APIRouter(tags=['health']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/ledger.py:38` | module-singleton | router = APIRouter(prefix='/ledger', tags=['ledger']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/plan.py:28` | module-singleton | router = APIRouter(tags=['plan']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/planned.py:30` | module-singleton | router = APIRouter(prefix='/planned', tags=['planned']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/recurring.py:37` | module-singleton | router = APIRouter(prefix='/recurring', tags=['recurring']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/recurring.py:78` | mutable-constant | _EMPTY_TERM_INPUT = {'sign': '+', 'coefficient_percent': '', 'sourc... | fix: tuple / frozenset / MappingProxyType |
| `web/routers/settings.py:34` | module-singleton | _VALID_TABS = get_args(TabKind) | accept: immutable / framework entry point |
| `web/routers/settings.py:38` | module-singleton | router = APIRouter(prefix='/settings', tags=['settings']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/settings_password.py:35` | module-singleton | router = APIRouter(prefix='/settings', tags=['settings']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/settings_security.py:31` | module-singleton | router = APIRouter(prefix='/settings', tags=['settings']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/settings_users.py:50` | module-singleton | router = APIRouter(prefix=LIST_PATH, tags=['settings-users']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/today.py:32` | module-singleton | router = APIRouter(tags=['today']) | accept: framework idiom (`router = APIRouter`) |
| `web/routers/transactions.py:52` | module-singleton | router = APIRouter(prefix='/transactions', tags=['transactions']) | accept: framework idiom (`router = APIRouter`) |
| `web/templating.py:98` | mutable-constant | _DIRECTION_COLORS = {Direction.INCOME.value: 'pill-income', Directi... | fix: tuple / frozenset / MappingProxyType |
| `web/templating.py:108` | mutable-constant | _DIRECTION_CSS_VARS = {Direction.INCOME.value: 'var(--income)', Dir... | fix: tuple / frozenset / MappingProxyType |
| `web/today_data.py:29` | mutable-constant | _PACE_LABELS = {'on_track': 'on track', 'pacing_high': 'pacing... | fix: tuple / frozenset / MappingProxyType |
| `web/today_data.py:35` | mutable-constant | _WINDOWS = {'7': 7, '30': 30, 'all': None} | fix: tuple / frozenset / MappingProxyType |

Totals: 53 raw rows. Accept (framework idiom / frozen sentinel): 28. To remediate: 25: 13 `mutable-constant` (module dicts that should be `MappingProxyType`/tuples; one is the **real shared state** `_TX_DEPTH` in `repositories/_shared.py:98`), 2 `global-stmt` (`logging.py:103`, `web/app.py:86`), 2 `hidden-cache` (`config.get_settings` process-wide cache, `_passwords._dummy_hash_for`), 6 `BaseHTTPMiddleware` subclasses (framework-imposed; converting them to pure ASGI callables removes the letter violation), 2 plain classes (`CacheControlMiddleware`, `logging._StripQueryFilter`). Note `Settings` is a pydantic model that mutates itself via `object.__setattr__` (P3). No service or repository module defines a class.

## 4. Principle 3: Immutability by default

**Rule (precise).** Allowed: a *local accumulator*, a name the function creates (`out = []; out.append(x)`, `d = {}; d[k] = v`) and returns or consumes inside the same function. Violation: in-place mutation of anything the function did not create: (i) a parameter (`p.append/extend/update/...`, `p[k] = v`, `del p[k]`, `p.attr = v`, and chains rooted at a parameter), (ii) module-level mutable state, (iii) `object.__setattr__`/`setattr` on frozen instances. Aliases (`x = p; x.append`) are not followed (limit, section 17).

**Detection.** `repro/inventory/p03_immutability.py`.

| Location | Rule | Detail | Disposition |
|---|---|---|---|
| `config.py:189` | setattr-bypass | _finalise: object.__setattr__(self, 'database_url', _PROD_DATABASE_URL) | violation: frozen-dataclass bypass in `Settings._finalise` |
| `config.py:207` | setattr-bypass | _finalise: object.__setattr__(self, 'cookie_secret', _DEV_COOKIE_SECRET) | violation: frozen-dataclass bypass in `Settings._finalise` |
| `logging.py:73` | param-mutation:data | root filter: record.args = (*args[:idx], path.split('?', 1)[0], *args[idx + 1:]) | violation: mutates caller's object |
| `repositories/_shared.py:108` | module-mutation | repositories _set_depth: _TX_DEPTH.pop(key, None) | violation: process-global dict keyed by `id(conn)` |
| `repositories/_shared.py:110` | module-mutation | repositories _set_depth: _TX_DEPTH[key] = value | violation: process-global dict keyed by `id(conn)` |
| `services/recurring_formula.py:240` | param-mutation:data | services _sum_category_in_month: cache[key] = value | violation: mutates caller's object |
| `web/htmx.py:28` | param-mutation:framework | web trigger: response.headers['HX-Trigger'] = json.dumps(payload) | framework-required (starlette `request.state` / `response.headers`); allowlist as `framework` |
| `web/htmx.py:42` | param-mutation:framework | web refresh_unless_on: response.headers['HX-Reswap'] = 'none' | framework-required (starlette `request.state` / `response.headers`); allowlist as `framework` |
| `web/htmx.py:45` | param-mutation:framework | web refresh_unless_on: response.headers['HX-Refresh'] = 'true' | framework-required (starlette `request.state` / `response.headers`); allowlist as `framework` |
| `web/middleware/auth.py:150` | param-mutation:framework | web.middleware dispatch: request.state.user = None | framework-required (starlette `request.state` / `response.headers`); allowlist as `framework` |
| `web/middleware/auth.py:151` | param-mutation:framework | web.middleware dispatch: request.state.session_id = None | framework-required (starlette `request.state` / `response.headers`); allowlist as `framework` |
| `web/middleware/auth.py:162` | param-mutation:framework | web.middleware dispatch: request.state.user = user | framework-required (starlette `request.state` / `response.headers`); allowlist as `framework` |
| `web/middleware/auth.py:163` | param-mutation:framework | web.middleware dispatch: request.state.session_id = session_id | framework-required (starlette `request.state` / `response.headers`); allowlist as `framework` |
| `web/middleware/csrf.py:138` | param-mutation:framework | web.middleware _read_form_token: request._receive = _replay | framework-required (starlette `request.state` / `response.headers`); allowlist as `framework` |
| `web/middleware/csrf.py:149` | param-mutation:framework | web.middleware _read_form_token: request._receive = _replay | framework-required (starlette `request.state` / `response.headers`); allowlist as `framework` |
| `web/middleware/csrf.py:167` | param-mutation:framework | web.middleware dispatch: request.state.csrf_token = token | framework-required (starlette `request.state` / `response.headers`); allowlist as `framework` |
| `web/middleware/request_id.py:33` | param-mutation:framework | web.middleware dispatch: request.state.request_id = rid | framework-required (starlette `request.state` / `response.headers`); allowlist as `framework` |
| `web/middleware/security_headers.py:72` | param-mutation:framework | web.middleware dispatch: request.state.csp_nonce = nonce | framework-required (starlette `request.state` / `response.headers`); allowlist as `framework` |
| `web/routers/categories.py:237` | param-mutation:framework | web.routers _toast_trigger: resp.headers['HX-Trigger'] = json.dumps(payload) | framework-required (starlette `request.state` / `response.headers`); allowlist as `framework` |
| `web/routers/settings_users.py:82` | param-mutation:framework | web.routers _no_store: response.headers['Cache-Control'] = 'no-store' | framework-required (starlette `request.state` / `response.headers`); allowlist as `framework` |

Totals: 20 raw rows, 6 to remediate: `_TX_DEPTH` (2 rows), `Settings._finalise` setattr bypass (2), `recurring_formula._sum_category_in_month` memo dict passed as argument (1), `logging._StripQueryFilter` record rewrite (1). The 14 framework rows (`request.state.*` in 5 middlewares, `response.headers[...]` in `htmx.py`, `categories._toast_trigger`, `settings_users._no_store`, `csrf._read_form_token`) are required by Starlette; they get the allowlist category `framework` and should be funnelled through two helpers (`set_hx_trigger(response, ...)`, `request_state` setters) so the count stays fixed.

## 5. Principle 4: No side effects in pure layers

**Pure layers (definition used here).**

| Layer | Allowed | Forbidden |
|---|---|---|
| `domain/` | pure functions over values | any I/O, DB, network, clock, logging, env, random, settings, filesystem |
| `services/` | DB access **through the passed connection**; clock/network **only via injected ports** | network, clock, env, random/entropy, logging, filesystem, settings singleton, `httpx` imports |
| web view-model builders (`web/*.py` except `app`, `deps`, `errors`, `retention_task`, `auth_cookies`) | pure shaping of service results | network, clock, env, random, subprocess |
| `repositories/` | SQL via the connection | clock/env/settings are listed under P7 / P1 |

**Detection.** `repro/inventory/p04_p07_effects_clock.py`: forbidden imports per layer, forbidden calls (clock, random/secrets/uuid, env, logging, filesystem, print, settings, network, sleep, subprocess), and a **name-resolved call graph** that marks every function that transitively reaches a function performing network I/O (`eff-net-reach`, approximate: callee resolved through first-party imports). Result: **domain/ has 0 rows** (fully pure; its only impurity is the comment-free `_CURRENCY_DECIMALS` dict, P2).

### 5.1 Rows by layer and rule

| Layer | Rule | Rows |
|---|---|---|
| services | eff-clock | 4 |
| services | eff-import | 18 |
| services | eff-log | 17 |
| services | eff-net | 3 |
| services | eff-net-reach | 5 |
| services | eff-random | 2 |
| services | eff-settings | 3 |
| web | eff-clock | 2 |
| web | eff-import | 1 |
| web | eff-net | 2 |

### 5.2 Network I/O and clock on the render path (Q-007, Q-031)

| Location | Rule | Detail |
|---|---|---|
| `services/_passwords.py:71` | eff-random | [services] _dummy_hash_for: secrets.token_urlsafe(16) |
| `services/auth.py:132` | eff-settings | [services] relying_party_from_settings: get_settings() |
| `services/balance.py:210` | eff-clock | [services] balance_series: dt.date.today() |
| `services/budget.py:69` | eff-clock | [services] base_amount_converter: dt.date.today() |
| `services/budget.py:70` | eff-settings | [services] base_amount_converter: get_settings() |
| `services/budget.py:101` | eff-settings | [services] base_txn_converter: get_settings() |
| `services/forecast.py:204` | eff-net-reach | [services] _collect_fx_rates -> services.fx.get_rate |
| `services/forecast.py:530` | eff-net-reach | [services] forecast -> services.forecast._collect_fx_rates |
| `services/forecast.py:778` | eff-net-reach | [services] forecast_monthly -> services.forecast._collect_fx_rates |
| `services/forecast.py:932` | eff-net | [services] monthly_projection performs network I/O directly |
| `services/forecast.py:950` | eff-net | [services] monthly_projection: httpx.Client(timeout=5.0) |
| `services/fx.py:49` | eff-net | [services] _fetch_remote performs network I/O directly |
| `services/fx.py:83` | eff-net-reach | [services] get_rate -> services.fx._fetch_remote |
| `services/fx.py:119` | eff-net-reach | [services] convert -> services.fx.get_rate |
| `services/planned.py:86` | eff-clock | [services] _default_window: dt.date.today() |
| `services/recurring.py:249` | eff-clock | [services] _build_lookup_stub: dt.datetime.now(dt.UTC) |
| `services/users.py:340` | eff-random | [services] generate_password: secrets.token_urlsafe(GENERATED_PASSWORD_BYTES) |
| `web/routers/forecast.py:65` | eff-net-reach-web | [web.routers] index -> web.routers.forecast._compute |
| `web/routers/forecast.py:84` | eff-net-reach-web | [web.routers] view_fragment -> web.routers.forecast._compute |
| `web/routers/plan.py:68` | eff-net-reach-web | [web.routers] plan -> services.forecast.monthly_projection |
| `web/routers/today.py:42` | eff-net-reach-web | [web.routers] today -> web.today_data.collect_account_rows |
| `web/templating.py:192` | eff-clock | [web-vm] _today_local_factory._today_local: datetime.now(tz) |
| `web/today_data.py:106` | eff-net | [web-vm] collect_account_rows performs network I/O directly |
| `web/today_data.py:123` | eff-clock | [web-vm] collect_account_rows: date.today() |
| `web/today_data.py:124` | eff-net | [web-vm] collect_account_rows: httpx.Client(timeout=5.0) |

Reading: `services/forecast.py` builds an `httpx.Client` inside `monthly_projection` (line 950) and `_collect_fx_rates` calls `fx.get_rate` per currency (so `forecast`, `forecast_monthly`, the `/forecast` and `/plan` routers do network I/O on a GET render); `web/today_data.collect_account_rows` does the same for `/today` (line 124). `services/fx.py` takes the client as a parameter (the right shape) but `convert`/`get_rate`/`_fetch_remote` are the sinks. Target: services receive a pre-fetched rate map (or an injected `RatePort`); the fetch moves to a scheduled job or an explicit "refresh rates" action (Q-007).

### 5.3 Logging, entropy, settings and import rows in services

| File | Rows |
|---|---|
| `services/_passwords.py` | import 1, random 1 |
| `services/account_planned.py` | import 1 |
| `services/auth.py` | import 1, settings 1 |
| `services/balance.py` | clock 1 |
| `services/budget.py` | import 2, log 3, settings 2, clock 1 |
| `services/categories.py` | import 1, log 2 |
| `services/forecast.py` | import 2, log 2 |
| `services/fortune.py` | import 1 |
| `services/fx.py` | import 2, log 2 |
| `services/planned.py` | clock 1 |
| `services/preferences.py` | import 1, log 4 |
| `services/rate_limit.py` | import 1 |
| `services/recurring.py` | import 1, log 3, clock 1 |
| `services/recurring_formula.py` | import 1, log 1 |
| `services/retention.py` | import 1 |
| `services/users.py` | import 2, random 1 |
| `web/templating.py` | clock 1 |
| `web/today_data.py` | import 1, clock 1 |

Dispositions: **logging** in services (17 rows, 7 modules) is an allowed cross-cutting concern only if routed through an injected/`get_logger` facade; a strict reading of "no side effects" makes services return structured warnings (e.g. `fx_fallback` events in the result) and let the router/adapter log. Decision for the operator (see section 17, Q1). **Entropy** (`secrets` in `_passwords.py`, `users.py`) should be an injected `TokenSource` port. **Settings singleton** reads (`auth.relying_party_from_settings`, `budget.base_amount_converter` x2) are hidden global reads: pass `Settings` values as arguments. **Config imports** (`account_planned`, `fortune`, `rate_limit`, `retention`, `users`, `budget`, `auth`) import `Settings` for type annotation only in most cases; pass a tiny frozen params dataclass instead.

## 6. Principle 5: Thin web, fat services

**Definition.** A router function parses/validates transport input, calls **one** service, and renders. Business logic means any of: R repository call; S SQL; A arithmetic on non-string operands; G aggregation (`sum/min/max/sorted`, accumulator loop); D domain branching on enum/direction/kind/cadence/status; T transaction control; F money/FX function call; C date arithmetic; P a private non-route helper living in a router (logic outside a handler).

**Detection.** `repro/inventory/p05_p06_web_repo.py`: every function in `web/routers/*.py` (handlers and helpers) with its signals (`inventory/p05-thin-web.txt`; the compliant ones are in `p05-thin-web-thin-ok.txt`). Repository calls are resolved through imports (a call whose target is in `budget_planner.repositories.*`).

### 6.1 Per router

| Router | Functions | Thin (ok) | Logic in router | Non-route helpers |
|---|---|---|---|---|
| `accounts.py` | 18 | 3 | 11 | 4 |
| `analytics.py` | 1 | 1 | 0 | 0 |
| `auth.py` | 39 | 14 | 2 | 23 |
| `budget.py` | 13 | 4 | 6 | 3 |
| `categories.py` | 11 | 4 | 4 | 3 |
| `debug.py` | 1 | 1 | 0 | 0 |
| `dev_components.py` | 1 | 1 | 0 | 0 |
| `forecast.py` | 5 | 2 | 2 | 1 |
| `health.py` | 3 | 1 | 2 | 0 |
| `ledger.py` | 17 | 1 | 12 | 4 |
| `plan.py` | 4 | 2 | 2 | 0 |
| `planned.py` | 19 | 4 | 11 | 4 |
| `recurring.py` | 29 | 4 | 20 | 5 |
| `settings.py` | 3 | 1 | 1 | 1 |
| `settings_password.py` | 6 | 2 | 0 | 4 |
| `settings_security.py` | 2 | 1 | 1 | 0 |
| `settings_users.py` | 17 | 6 | 0 | 11 |
| `today.py` | 7 | 3 | 4 | 0 |
| `transactions.py` | 16 | 3 | 10 | 3 |
| **total** | 212 | 58 | 88 | 66 |

Signal totals over the 88 logic rows: A 13, C 4, D 7, F 14, G 10, P 33, R 71, S 3. 71 of 88 call a repository directly (the layering finding Q-045); 13 do arithmetic in the router; 7 branch on domain enums; 3 execute SQL.

### 6.2 Complete list: router functions with logic (88)

| Location | Function | Kind | Lines | CC (approx) | Signals |
|---|---|---|---|---|---|
| `web/routers/accounts.py:59` | `_card_context` | helper | L35 | cc4 | PR |
| `web/routers/accounts.py:96` | `_hydrate` | helper | L24 | cc4 | PR |
| `web/routers/accounts.py:171` | `_parse_credit_limit` | helper | L12 | cc4 | FP |
| `web/routers/accounts.py:186` | `create_account` | route | L62 | cc11 | FR |
| `web/routers/accounts.py:251` | `edit_form` | route | L25 | cc2 | R |
| `web/routers/accounts.py:279` | `update_account` | route | L67 | cc7 | R |
| `web/routers/accounts.py:349` | `delete_account` | route | L15 | cc1 | R |
| `web/routers/accounts.py:367` | `take_snapshot` | route | L23 | cc2 | R |
| `web/routers/accounts.py:397` | `_available_mode_context` | helper | L11 | cc3 | AGP |
| `web/routers/accounts.py:411` | `reconcile_form` | route | L31 | cc3 | R |
| `web/routers/accounts.py:445` | `reconcile_submit` | route | L65 | cc10 | FR |
| `web/routers/auth.py:556` | `revoke_session` | route | L24 | cc7 | R |
| `web/routers/auth.py:610` | `_reauth_page` | helper | L20 | cc1 | PR |
| `web/routers/budget.py:88` | `_rules_rows` | helper | L24 | cc5 | DPR |
| `web/routers/budget.py:170` | `new_override_form` | route | L62 | cc12 | R |
| `web/routers/budget.py:235` | `create_override` | route | L59 | cc12 | FR |
| `web/routers/budget.py:327` | `set_default` | route | L18 | cc4 | FR |
| `web/routers/budget.py:348` | `set_recurring` | route | L25 | cc6 | FR |
| `web/routers/budget.py:403` | `set_one_off` | route | L26 | cc6 | FR |
| `web/routers/categories.py:79` | `create_category` | route | L40 | cc6 | R |
| `web/routers/categories.py:122` | `edit_form` | route | L25 | cc2 | R |
| `web/routers/categories.py:150` | `update_category` | route | L48 | cc6 | R |
| `web/routers/categories.py:201` | `delete_category` | route | L14 | cc3 | R |
| `web/routers/forecast.py:34` | `_parse_horizon_months` | helper | L6 | cc2 | GP |
| `web/routers/forecast.py:55` | `_series_to_chart` | helper | L7 | cc3 | AP |
| `web/routers/health.py:41` | `ready` | route | L39 | cc5 | S |
| `web/routers/health.py:83` | `replication` | route | L16 | cc4 | C |
| `web/routers/ledger.py:62` | `parse_filters` | helper | L19 | cc7 | GP |
| `web/routers/ledger.py:83` | `_hydrate_txn_rows` | helper | L23 | cc6 | PR |
| `web/routers/ledger.py:108` | `_hydrate_planned_rows` | helper | L30 | cc6 | PR |
| `web/routers/ledger.py:140` | `_hydrate_recurring_rows` | helper | L80 | cc28 | DGPR |
| `web/routers/ledger.py:235` | `_actual_rows` | helper | L17 | cc1 | APR |
| `web/routers/ledger.py:254` | `_actual_day_nets` | helper | L30 | cc7 | FP |
| `web/routers/ledger.py:286` | `_planned_rows` | helper | L20 | cc6 | ACP |
| `web/routers/ledger.py:308` | `_render_table` | helper | L33 | cc6 | PR |
| `web/routers/ledger.py:343` | `_recurring_summary` | helper | L32 | cc10 | AGP |
| `web/routers/ledger.py:377` | `_tab_counts` | helper | L15 | cc1 | PR |
| `web/routers/ledger.py:395` | `index` | route | L43 | cc10 | GR |
| `web/routers/ledger.py:452` | `recently_deleted` | route | L23 | cc3 | R |
| `web/routers/plan.py:40` | `_analytics_charts` | helper | L25 | cc3 | AP |
| `web/routers/plan.py:68` | `plan` | route | L184 | cc31 | ACGR |
| `web/routers/planned.py:112` | `planned_batch_undo` | route | L60 | cc8 | RS |
| `web/routers/planned.py:190` | `new_form` | route | L17 | cc1 | R |
| `web/routers/planned.py:209` | `_validate_amount` | helper | L8 | cc3 | FP |
| `web/routers/planned.py:220` | `create_planned` | route | L67 | cc13 | R |
| `web/routers/planned.py:305` | `edit_form` | route | L30 | cc2 | R |
| `web/routers/planned.py:338` | `update_planned` | route | L64 | cc12 | R |
| `web/routers/planned.py:405` | `delete_planned` | route | L12 | cc2 | R |
| `web/routers/planned.py:420` | `restore_planned` | route | L13 | cc2 | R |
| `web/routers/planned.py:436` | `promote_form` | route | L23 | cc2 | R |
| `web/routers/planned.py:462` | `promote_inline` | route | L19 | cc3 | R |
| `web/routers/planned.py:484` | `promote_submit` | route | L61 | cc10 | R |
| `web/routers/recurring.py:69` | `_formula_source_candidates` | helper | L7 | cc2 | DPR |
| `web/routers/recurring.py:87` | `_parse_terms_from_form` | helper | L30 | cc5 | GP |
| `web/routers/recurring.py:120` | `new_form` | route | L20 | cc1 | R |
| `web/routers/recurring.py:149` | `_resolve_dest_account` | helper | L30 | cc12 | DPR |
| `web/routers/recurring.py:181` | `_resolve_amount_inputs` | helper | L59 | cc10 | FP |
| `web/routers/recurring.py:242` | `_render_form_errors` | helper | L24 | cc1 | PR |
| `web/routers/recurring.py:269` | `create_rule` | route | L119 | cc18 | R |
| `web/routers/recurring.py:390` | `_formula_prefill` | helper | L21 | cc4 | AP |
| `web/routers/recurring.py:470` | `recurring_batch_undo` | route | L70 | cc10 | RS |
| `web/routers/recurring.py:593` | `edit_form` | route | L37 | cc2 | R |
| `web/routers/recurring.py:633` | `update_rule_handler` | route | L108 | cc20 | R |
| `web/routers/recurring.py:753` | `deactivate_rule` | route | L15 | cc2 | R |
| `web/routers/recurring.py:771` | `new_override_form` | route | L36 | cc3 | AR |
| `web/routers/recurring.py:810` | `add_override` | route | L58 | cc10 | FR |
| `web/routers/recurring.py:871` | `delete_override` | route | L28 | cc3 | R |
| `web/routers/recurring.py:904` | `_override_on_next_due` | helper | L11 | cc3 | PR |
| `web/routers/recurring.py:917` | `_render_promote_modal` | helper | L47 | cc7 | PR |
| `web/routers/recurring.py:977` | `promote_inline` | route | L36 | cc7 | R |
| `web/routers/recurring.py:1016` | `promote_submit` | route | L69 | cc12 | FR |
| `web/routers/recurring.py:1088` | `skip_next` | route | L28 | cc4 | R |
| `web/routers/settings.py:52` | `drawer` | route | L40 | cc14 | DR |
| `web/routers/settings_security.py:34` | `security_context` | helper | L27 | cc3 | ACPR |
| `web/routers/today.py:42` | `today` | route | L52 | cc4 | AGR |
| `web/routers/today.py:97` | `today_upcoming_fragment` | route | L27 | cc3 | R |
| `web/routers/today.py:126` | `_parse_amount_arg` | helper | L16 | cc4 | AP |
| `web/routers/today.py:197` | `add_entry_overlay` | route | L28 | cc3 | R |
| `web/routers/transactions.py:90` | `_hydrate_rows` | helper | L21 | cc6 | PR |
| `web/routers/transactions.py:125` | `_compute_limit_preview` | helper | L39 | cc10 | ADFGPR |
| `web/routers/transactions.py:201` | `new_form` | route | L20 | cc1 | R |
| `web/routers/transactions.py:223` | `_validate_amount` | helper | L12 | cc3 | FP |
| `web/routers/transactions.py:238` | `create_txn` | route | L80 | cc17 | DR |
| `web/routers/transactions.py:321` | `edit_form` | route | L34 | cc2 | R |
| `web/routers/transactions.py:358` | `update_txn` | route | L77 | cc13 | R |
| `web/routers/transactions.py:438` | `delete_txn` | route | L7 | cc1 | R |
| `web/routers/transactions.py:448` | `restore_txn` | route | L11 | cc2 | R |
| `web/routers/transactions.py:462` | `export` | route | L46 | cc7 | R |

### 6.3 Complete list: non-route helpers living in routers (66), grouped by file

| File | Helpers (name:line) |
|---|---|
| `web/routers/accounts.py` | `_today`:45, `_planned_now`:49, `_parse_liability`:167, `_uses_available`:392 |
| `web/routers/auth.py` | `_client_ip`:85, `_rate_limit_now`:94, `_ip_identity`:99, `_wants_json`:103, `_throttled_json`:108, `login_rate_limit`:116, `passkey_login_rate_limit`:144, `register_rate_limit`:163, `reauth_rate_limit`:183, `_redirect`:203, `_dev_host_is_ip`:211, `_derives_rp_from_request`:216, `_is_ip`:220, `_rp`:228, `_passkey_host_error`:245, `_start_session`:249, `_json_body`:264, `_begin_response`:274, `_login_page`:293, `_throttled_login`:314, `_clean_label`:488, `_reauth_target`:604, `_reauth_success`:632 |
| `web/routers/budget.py` | `_year_month`:78, `_render_index`:119, `_parse_decimal`:316 |
| `web/routers/categories.py` | `_validate_direction`:49, `_resolve_color_form`:65, `_toast_trigger`:220 |
| `web/routers/forecast.py` | `_compute`:42 |
| `web/routers/ledger.py` | `_parse_date`:44, `_parse_int`:53, `_direction_tuple`:222, `render_table_for`:477 |
| `web/routers/planned.py` | `_parse_date`:33, `parse_filter`:42, `_hx_trigger_payload`:69, `_from_persisted`:289 |
| `web/routers/recurring.py` | `_parse_date`:40, `_parse_int`:49, `_validate_cadence`:142, `_hx_trigger_payload`:417, `_effective_amount_for_render`:743 |
| `web/routers/settings.py` | `_coerce_tab`:41 |
| `web/routers/settings_password.py` | `password_change_rate_limit`:43, `_target`:63, `_default_target`:68, `_render_form`:76 |
| `web/routers/settings_users.py` | `current_admin`:53, `_not_found`:64, `_checkbox`:77, `_no_store`:81, `_see_other`:86, `_page_context`:90, `_toast`:101, `_render_toast`:105, `_conflict`:115, `_table_with_flash`:126, `_edit_response`:177 |
| `web/routers/transactions.py` | `_parse_date`:55, `_parse_int`:64, `parse_filter`:73 |

Known router-local re-implementations of shared logic among these (Track A concept 13/2/3/10): `_parse_date`, `_parse_int` (4 routers), `_parse_decimal` (budget), `_parse_amount_arg` (today), `_validate_amount` (planned), `_resolve_amount_inputs`, `_resolve_dest_account` and `_validate_cadence` (recurring), `_validate_direction` (categories), `_actual_day_nets.convert` (ledger FX closure), `_hydrate_*_rows` (ledger/transactions/recurring), `_recurring_summary` (ledger: sums native amounts, B-01/Q-010), `_shift_month` nested in `plan()` (concept 5), `_series_to_chart`. Router auth helpers (23 in `auth.py`, 11 in `settings_users.py`) are mostly cookie/redirect/rate-limit dependency factories; they are not business logic but still count as non-route code in a router module: move to `web/auth_deps.py` / `web/params.py`.

## 7. Principle 6: Repository discipline (ADR-0019, ADR-0022)

**Definition.** All SQL lives in `repositories/` (plus `db/` bootstrap). Every mutation of a soft-delete/audited table goes through `_shared.mutate`/`write_audit` inside `_shared.transaction`. Every read of a soft-delete table filters `deleted_at` (or takes an explicit `include_deleted`), and every read of a user-owned table filters `user_id` (ADR-0061).

**Detection.** `p05_p06_web_repo.py`: (a) string constants/f-strings that look like SQL and `.execute/.executemany/.executescript` calls outside `repositories/`; `conn.commit/rollback` outside; (b) in `repositories/`, `INSERT/UPDATE/DELETE` whose top-level function calls neither `mutate` nor `write_audit`; (c) `SELECT` over a table that has `deleted_at` (resp. `user_id`, derived from `migrations/*.sql`) whose enclosing top-level function contains no `deleted_at` (resp. `user_id`) string anywhere. (c) is function-level, so it can both over- and under-report; the existing `tests/architecture/test_user_id_filter.py` remains the statement-level authority for `user_id`.

### 7.1 SQL outside `repositories/` (real DML/SELECT/PRAGMA, excluding `db/` bootstrap)

| Location | Statement | Disposition |
|---|---|---|
| `services/accounts.py:35` | [services] _latest_snapshot_by_account: conn.execute('\n SELECT s.account_id AS account... | B-14 / Q-074: two SELECTs belong in `repositories/snapshots` + `transactions` |
| `services/accounts.py:63` | [services] _latest_reconcile_by_account: conn.execute('\n SELECT account_id, MAX(operat... | B-14 / Q-074: two SELECTs belong in `repositories/snapshots` + `transactions` |
| `services/users.py:112` | [services] _assert_schema: conn.execute('PRAGMA table_info(users)') | schema assertion via `PRAGMA table_info`; move to `db/` |
| `web/routers/planned.py:140` | [web.routers] planned_batch_undo: conn.execute("\n SELECT prev_json FROM audit_log\n WH... | Q-024: audit_log SELECT + direct UPDATE in a router (unaudited write) |
| `web/routers/planned.py:155` | [web.routers] planned_batch_undo: conn.execute("UPDATE planned_transactions SET promote... | Q-024: audit_log SELECT + direct UPDATE in a router (unaudited write) |
| `web/routers/recurring.py:501` | [web.routers] recurring_batch_undo: conn.execute("\n SELECT prev_json FROM audit_log\n ... | Q-024: audit_log SELECT in a router (no user_id predicate, B-11) |
| `web/app.py:59` | [web] PRAGMA wal_autocheckpoint; | health/startup PRAGMA outside `db/`: move behind `db.connection` helper (web -> db contract, B-15) |
| `web/routers/health.py:64` | [web.routers] PRAGMA integrity_check; | health/startup PRAGMA outside `db/`: move behind `db.connection` helper (web -> db contract, B-15) |

Bootstrap SQL (50 rows, allowed by G2): `db/connection.py` 12, `db/migrate.py` 34, `db/startup_migrate.py` 2, `web/app.py` 1, `web/routers/health.py` 1. `domain/enums.py` (3 rows) is an enum-member false positive. Transaction control (`commit`/`rollback`/`BEGIN`) outside `_shared.transaction`: 0 rows outside `db/`.

### 7.2 Mutations not through the audited helpers

| Location | Rule | Statement | Disposition |
|---|---|---|---|
| `repositories/_shared.py:79` | mutation-exempt-table | write_audit: INSERT audit_log | ADR-sanctioned unaudited table (sessions, rate limit, preferences, audit_log itself): allowlist with reason |
| `repositories/preferences.py:46` | mutation-exempt-table | upsert: INSERT user_preferences | ADR-sanctioned unaudited table (sessions, rate limit, preferences, audit_log itself): allowlist with reason |
| `repositories/preferences.py:62` | mutation-exempt-table | delete: DELETE user_preferences | ADR-sanctioned unaudited table (sessions, rate limit, preferences, audit_log itself): allowlist with reason |
| `repositories/rate_limit.py:28` | mutation-exempt-table | hit: INSERT auth_rate_limit | ADR-sanctioned unaudited table (sessions, rate limit, preferences, audit_log itself): allowlist with reason |
| `repositories/rate_limit.py:47` | mutation-exempt-table | prune: DELETE auth_rate_limit | ADR-sanctioned unaudited table (sessions, rate limit, preferences, audit_log itself): allowlist with reason |
| `repositories/recurring.py:282` | mutation-unaudited | set_next_due: UPDATE recurring_rules | violation: audited domain table |
| `repositories/recurring.py:297` | mutation-unaudited | set_inactive: UPDATE recurring_rules | violation: audited domain table |
| `repositories/retention.py:25` | mutation-exempt-table | scrub_audit_request_context: UPDATE audit_log | ADR-sanctioned unaudited table (sessions, rate limit, preferences, audit_log itself): allowlist with reason |
| `repositories/retention.py:37` | mutation-exempt-table | delete_ended_sessions: DELETE sessions | ADR-sanctioned unaudited table (sessions, rate limit, preferences, audit_log itself): allowlist with reason |
| `repositories/sessions.py:138` | mutation-exempt-table | create_session: INSERT sessions | ADR-sanctioned unaudited table (sessions, rate limit, preferences, audit_log itself): allowlist with reason |
| `repositories/sessions.py:189` | mutation-exempt-table | revoke_session_by_id: UPDATE sessions | ADR-sanctioned unaudited table (sessions, rate limit, preferences, audit_log itself): allowlist with reason |
| `repositories/sessions.py:214` | mutation-exempt-table | revoke_all_user_sessions: UPDATE sessions | ADR-sanctioned unaudited table (sessions, rate limit, preferences, audit_log itself): allowlist with reason |
| `repositories/sessions.py:248` | mutation-exempt-table | touch_session: UPDATE sessions | ADR-sanctioned unaudited table (sessions, rate limit, preferences, audit_log itself): allowlist with reason |
| `repositories/sessions.py:260` | mutation-exempt-table | mark_authenticated: UPDATE sessions | ADR-sanctioned unaudited table (sessions, rate limit, preferences, audit_log itself): allowlist with reason |
| `repositories/sessions.py:275` | mutation-exempt-table | rotate_session_token: UPDATE sessions | ADR-sanctioned unaudited table (sessions, rate limit, preferences, audit_log itself): allowlist with reason |
| `repositories/webauthn.py:167` | mutation-unaudited | update_sign_count: UPDATE webauthn_credentials | violation: audited domain table |

`recurring_rules.set_next_due`/`set_inactive` are called from services that may wrap them in `mutate`; confirm per call site during remediation (Q-049). `webauthn.update_sign_count` updates a security counter outside audit (ADR-0069 may justify; record the reason in the allowlist). Router-level writes (`planned_batch_undo` UPDATE) are counted in 7.1. `user_preferences` writes are unaudited by design (migration 0005 comment) but Q-049 records the ADR gap.

### 7.3 Reads without a soft-delete / user filter (function-level heuristic)

| Location | Rule | Function: table | Disposition |
|---|---|---|---|
| `repositories/_shared.py:203` | read-no-softdelete | require_owned: accounts | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/_shared.py:209` | read-no-softdelete | require_owned: categories | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/audit.py:36` | read-no-user-filter | list_entries: audit_log | review: lookup by unguessable secret (session token hash / credential id) or audit tail (admin); name it or add the predicate |
| `repositories/audit.py:46` | read-no-user-filter | recent: audit_log | review: lookup by unguessable secret (session token hash / credential id) or audit tail (admin); name it or add the predicate |
| `repositories/budgets.py:116` | read-no-softdelete | set_default: budget_defaults | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/budgets.py:211` | read-no-softdelete | set_recurring: budget_recurring_overrides | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/budgets.py:317` | read-no-softdelete | set_one_off: budget_one_off_overrides | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/planned.py:115` | read-no-softdelete-flag | list_filtered: categories | intentional: function takes `include_deleted`, filter added via f-string/conditional the heuristic missed in `list_filtered` |
| `repositories/planned.py:115` | read-no-softdelete-flag | list_filtered: planned_transactions | intentional: function takes `include_deleted`, filter added via f-string/conditional the heuristic missed in `list_filtered` |
| `repositories/recurring.py:388` | read-no-softdelete | list_overrides: recurring_rules | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/recurring.py:433` | read-no-softdelete | upsert_override: recurring_rules | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/recurring.py:446` | read-no-softdelete | upsert_override: recurring_rules | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/recurring.py:484` | read-no-softdelete | upsert_override: recurring_rules | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/recurring.py:509` | read-no-softdelete | delete_override: recurring_rules | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/sessions.py:239` | read-no-user-filter | touch_session: sessions | review: lookup by unguessable secret (session token hash / credential id) or audit tail (admin); name it or add the predicate |
| `repositories/sessions.py:280` | read-no-user-filter | rotate_session_token: sessions | review: lookup by unguessable secret (session token hash / credential id) or audit tail (admin); name it or add the predicate |
| `repositories/snapshots.py:38` | read-no-softdelete | list_for_account: accounts | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/snapshots.py:51` | read-no-softdelete | create: accounts | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/snapshots.py:63` | read-no-softdelete | create: accounts | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/transactions.py:123` | read-no-softdelete-flag | list_filtered: categories | intentional: function takes `include_deleted`, filter added via f-string/conditional the heuristic missed in `list_filtered` |
| `repositories/transactions.py:123` | read-no-softdelete-flag | list_filtered: transactions | intentional: function takes `include_deleted`, filter added via f-string/conditional the heuristic missed in `list_filtered` |
| `repositories/users.py:147` | read-no-softdelete | owns_accounts: accounts | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/webauthn.py:88` | read-no-softdelete | _get_by_id: webauthn_credentials | review: usually an upsert/ownership probe that must see tombstones; if so, name the intent (`include_deleted=True`) so the guard passes |
| `repositories/webauthn.py:111` | read-no-user-filter | get_by_credential_id: webauthn_credentials | review: lookup by unguessable secret (session token hash / credential id) or audit tail (admin); name it or add the predicate |

Plus the two router SQL reads of `audit_log` without `user_id` (7.1; B-11) and `repositories/audit.py` `list_entries`/`recent` (admin tail). The 22 rows are *candidates*; the guard (NEW G24) turns them into an explicit allowlist with reasons, which is the actual deliverable (today the intent is implicit).

## 8. Principle 7: Clock / time (ADR-0007)

**Definition.** The application obtains "now"/"today" in exactly one module (`clock.py`, to be created by S4 in T-Q15). Services never read the host clock; request handlers take `today` from an injected dependency that applies `display_timezone`.

**Detection.** `p04_p07_effects_clock.py`: every call whose tail is `now`/`utcnow`/`today` on a dotted receiver, and `time.time/monotonic/perf_counter/...` across all of `src/` (so it also catches `dt.date.today()`), plus DB-side clock in SQL strings. `(no-arg)` marks naive host-clock calls.

| Location | Function | Call | Kind |
|---|---|---|---|
| `db/migrate.py:155` | `_backfill_recurring_next_due` | dt.date.today() (no-arg) | **host-clock (naive)** |
| `db/migrate.py:188` | `_backfill_recurring_next_due` | dt.datetime.now(dt.UTC) (tz-arg) | tz-aware |
| `db/migrate.py:189` | `_backfill_recurring_next_due` | dt.datetime.now(dt.UTC) (tz-arg) | tz-aware |
| `db/retention.py:21` | `run` | dt.datetime.now(dt.UTC) (tz-arg) | tz-aware |
| `db/startup_migrate.py:139` | `_utcnow` | dt.datetime.now(dt.UTC) (tz-arg) | tz-aware |
| `repositories/_shared.py:35` | `utc_now_iso` | datetime.now(UTC) (tz-arg) | tz-aware |
| `repositories/recurring.py:147` | `_compute_initial_next_due` | dt.datetime.now(dt.UTC) (tz-arg) | tz-aware |
| `repositories/recurring.py:148` | `_compute_initial_next_due` | dt.datetime.now(dt.UTC) (tz-arg) | tz-aware |
| `repositories/recurring.py:227` | `create_rule` | dt.date.today() (no-arg) | **host-clock (naive)** |
| `repositories/sessions.py:83` | `_now` | datetime.now(UTC) (tz-arg) | tz-aware |
| `repositories/webauthn.py:164` | `update_sign_count` | datetime.now(UTC) (tz-arg) | tz-aware |
| `services/balance.py:210` | `balance_series` | dt.date.today() (no-arg) | **host-clock (naive)** |
| `services/budget.py:69` | `base_amount_converter` | dt.date.today() (no-arg) | **host-clock (naive)** |
| `services/planned.py:86` | `_default_window` | dt.date.today() (no-arg) | **host-clock (naive)** |
| `services/recurring.py:249` | `_build_lookup_stub` | dt.datetime.now(dt.UTC) (tz-arg) | tz-aware |
| `web/auth_cookies.py:68` | `set_session_cookie` | datetime.now(UTC) (tz-arg) | tz-aware |
| `web/auth_cookies.py:140` | `sign_challenge` | time.time() (no-arg) | **host-clock (naive)** |
| `web/auth_cookies.py:184` | `verify_challenge` | time.time() (no-arg) | **host-clock (naive)** |
| `web/deps.py:99` | `reauth_now` | datetime.now(UTC) (tz-arg) | tz-aware |
| `web/routers/accounts.py:46` | `_today` | date.today() (no-arg) | **host-clock (naive)** |
| `web/routers/auth.py:96` | `_rate_limit_now` | datetime.now(UTC) (tz-arg) | tz-aware |
| `web/routers/budget.py:81` | `_year_month` | date.today() (no-arg) | **host-clock (naive)** |
| `web/routers/budget.py:126` | `_render_index` | datetime.now(ZoneInfo(settings.display_timezone)) (tz-arg) | tz-aware |
| `web/routers/budget.py:156` | `yearly_fragment` | datetime.now(ZoneInfo(settings.display_timezone)) (tz-arg) | tz-aware |
| `web/routers/budget.py:183` | `new_override_form` | datetime.now(ZoneInfo(settings.display_timezone)) (tz-arg) | tz-aware |
| `web/routers/forecast.py:48` | `_compute` | date.today() (no-arg) | **host-clock (naive)** |
| `web/routers/health.py:95` | `replication` | datetime.now(UTC) (tz-arg) | tz-aware |
| `web/routers/ledger.py:292` | `_planned_rows` | date.today() (no-arg) | **host-clock (naive)** |
| `web/routers/ledger.py:338` | `_render_table` | date.today() (no-arg) | **host-clock (naive)** |
| `web/routers/ledger.py:433` | `index` | date.today() (no-arg) | **host-clock (naive)** |
| `web/routers/plan.py:76` | `plan` | datetime.now(ZoneInfo(settings.display_timezone)) (tz-arg) | tz-aware |
| `web/routers/plan.py:272` | `plan_analytics` | datetime.now(ZoneInfo(settings.display_timezone)) (tz-arg) | tz-aware |
| `web/routers/planned.py:80` | `planned_batch_promote_due` | date.today() (no-arg) | **host-clock (naive)** |
| `web/routers/planned.py:575` | `export` | datetime.now(UTC) (tz-arg) | tz-aware |
| `web/routers/recurring.py:338` | `create_rule` | dt.date.today() (no-arg) | **host-clock (naive)** |
| `web/routers/recurring.py:353` | `create_rule` | dt.date.today() (no-arg) | **host-clock (naive)** |
| `web/routers/recurring.py:435` | `recurring_batch_promote_due` | dt.date.today() (no-arg) | **host-clock (naive)** |
| `web/routers/recurring.py:580` | `formula_preview` | dt.date.today() (no-arg) | **host-clock (naive)** |
| `web/routers/recurring.py:694` | `update_rule_handler` | dt.date.today() (no-arg) | **host-clock (naive)** |
| `web/routers/today.py:48` | `today` | datetime.now(ZoneInfo(settings.display_timezone)) (tz-arg) | tz-aware |
| `web/routers/today.py:109` | `today_upcoming_fragment` | datetime.now(ZoneInfo(settings.display_timezone)) (tz-arg) | tz-aware |
| `web/routers/today.py:160` | `afford` | datetime.now(ZoneInfo(settings.display_timezone)) (tz-arg) | tz-aware |
| `web/routers/transactions.py:494` | `export` | datetime.now(UTC) (tz-arg) | tz-aware |
| `web/templating.py:192` | `_today_local_factory._today_local` | datetime.now(tz) (tz-arg) | tz-aware |
| `web/today_data.py:123` | `collect_account_rows` | date.today() (no-arg) | **host-clock (naive)** |

Totals: 45 sites (20 naive `date.today()`/`time.time()` host-clock calls, 25 tz-aware). By package: db 5, repositories 6, services 4, web 6, web/routers 24. 16-18 `date.today()` sites are the Q-031 set; the aware ones split into UTC audit timestamps (legitimate, but must come from `clock.utc_now()`), 8 display-timezone `datetime.now(ZoneInfo(settings.display_timezone))` sites in routers, and `time.time()` in `auth_cookies` challenge signing. Beyond Python: 38 `CURRENT_TIMESTAMP`/`datetime('now')` occurrences in repository SQL (DB-side clock; consistent with UTC but unmockable, `inventory/p07-clock-sql.txt`) and 52 in migrations (schema defaults, informational).

## 9. Principle 8: Money (ADR-0008, ADR-0006)

**Definition.** Amounts are integer minor units; conversion between major/minor, parsing, formatting, the exponent table and rounding live in `domain/money.py` (display via the Jinja filters in `web/templating.py`); FX conversion has one converter. No float on money, no `/ 100`, `* 100`, no `round()`/`quantize` outside the canonical helper.

**Detection.** `p08_money.py`: rules `money-scale`, `money-float`, `money-round`, `money-format`, `money-parse`, `fx-def`, `fx-call`, `fx-arith`. Rows inside `domain/money.py`, `domain/fx.py`, `services/fx.py`, `repositories/fx.py`, `web/templating.py` are tagged `:canonical` (not counted). `float-other` rows (chart geometry, timestamps) were reviewed and are not money (55 rows, all `web/charts.py`, `auth_cookies.py`, `retention_task.py`).

| Location | Rule | Detail |
|---|---|---|
| `services/analytics.py:141` | money-round | ROUND_HALF_EVEN |
| `services/balance.py:116` | money-parse | _mean: Decimal(sum(values)) |
| `services/balance.py:117` | money-parse | _mean: Decimal(len(values)) |
| `services/balance.py:118` | money-round | ROUND_HALF_EVEN |
| `services/balance.py:185` | money-round | sparkline_points: round(i * width / denom, 2) |
| `services/balance.py:186` | money-round | sparkline_points: round(height - (v - vmin) / span * height, 2) |
| `services/budget.py:55` | fx-def | def base_amount_converter |
| `services/budget.py:75` | fx-def | def _convert |
| `services/budget.py:80` | fx-call | base_amount_converter._convert: fx_svc.convert_cached(conn, amount_minor, ref, ccy, base) |
| `services/budget.py:88` | fx-def | def base_txn_converter |
| `services/budget.py:106` | fx-def | def _convert |
| `services/budget.py:111` | fx-call | base_txn_converter._convert: fx_svc.convert_cached(conn, txn.amount, txn.operation_date, ccy, base) |
| `services/budget.py:243` | money-round | ROUND_HALF_EVEN |
| `services/budget.py:585` | money-parse | month_summary: Decimal(totals.remaining_minor) |
| `services/budget.py:586` | money-round | ROUND_HALF_EVEN |
| `services/forecast.py:204` | fx-def | def _collect_fx_rates |
| `services/forecast.py:217` | fx-call | _collect_fx_rates: fx_svc.get_rate(conn, http, today, ccy, base_currency) |
| `services/forecast.py:221` | fx-def | def _convert_native_to_base |
| `services/forecast.py:238` | money-parse | _convert_native_to_base: Decimal(amount_native_minor) |
| `services/forecast.py:239` | fx-arith | _convert_native_to_base: major * rate |
| `services/forecast.py:239` | fx-arith | _convert_native_to_base: major * rate * dst_scale |
| `services/forecast.py:240` | money-round | ROUND_HALF_EVEN |
| `services/forecast.py:240` | money-round | _convert_native_to_base: converted.quantize(Decimal('1'), rounding=ROUND_HALF_EVEN) |
| `services/forecast.py:411` | money-parse | _distribute_overlay: Decimal(unaccounted_minor) |
| `services/forecast.py:412` | money-round | ROUND_HALF_EVEN |
| `services/forecast.py:924` | money-float | <module>: field value_major: float |
| `services/forecast.py:956` | money-float | monthly_projection: float literal in point.end_balance_base_minor / 100.0 |
| `services/forecast.py:956` | money-scale | monthly_projection: point.end_balance_base_minor / 100.0 |
| `services/ledger_totals.py:50` | fx-call | day_nets: convert(effect, day, ccy) |
| `services/rate_limit.py:83` | money-round | _retry_after: math.ceil(remaining) |
| `services/recurring_formula.py:40` | money-scale | <module>: Decimal('100') |
| `services/recurring_formula.py:68` | money-round | ROUND_HALF_UP |
| `services/recurring_formula.py:72` | money-format | parse_percent_to_bps: {_BPS_MAX / 100:.2f} |
| `services/recurring_formula.py:72` | money-format | parse_percent_to_bps: {_BPS_MIN / 100:.2f} |
| `services/recurring_formula.py:72` | money-scale | parse_percent_to_bps: _BPS_MAX / 100 |
| `services/recurring_formula.py:72` | money-scale | parse_percent_to_bps: _BPS_MIN / 100 |
| `services/recurring_formula.py:134` | money-parse | _apply_coefficient: Decimal(sum_minor) |
| `services/recurring_formula.py:135` | money-round | ROUND_HALF_UP |
| `services/recurring_formula.py:135` | money-round | _apply_coefficient: dec.quantize(Decimal('1'), rounding=ROUND_HALF_UP) |
| `services/today.py:50` | money-round | ROUND_HALF_EVEN |
| `services/today.py:71` | money-parse | _pace_tag_for: Decimal(baseline_per_day_minor) |
| `services/today.py:72` | money-parse | _pace_tag_for: Decimal(per_day_minor) |
| `web/charts.py:70` | money-round | _nice_axis: math.floor(math.log10(rough_step)) |
| `web/charts.py:71` | money-scale | _nice_axis: 10 ** exponent |
| `web/charts.py:75` | money-round | _nice_axis: math.floor(data_min / step) |
| `web/charts.py:76` | money-round | _nice_axis: math.ceil(data_max / step) |
| `web/charts.py:88` | money-round | _axis_ticks: round(current, 10) |
| `web/charts.py:138` | money-round | _format_label: round(value) |
| `web/charts.py:140` | money-format | _format_label: {int(rounded):,} |
| `web/charts.py:141` | money-format | _format_label: {value:,.2f} |
| `web/routers/budget.py:316` | money-parse | def _parse_decimal |
| `web/routers/budget.py:318` | money-parse | _parse_decimal: Decimal(value) |
| `web/routers/forecast.py:31` | money-scale | const _MINOR_UNITS_PER_MAJOR = 100.0 |
| `web/routers/ledger.py:273` | fx-def | def convert |
| `web/routers/ledger.py:275` | fx-call | _actual_day_nets.convert: fx_service.convert_cached(conn, amount, day, ccy, base_ccy) |
| `web/routers/ledger.py:363` | money-round | _recurring_summary: amt // divisor |
| `web/routers/plan.py:36` | money-scale | const _MINOR_UNITS_PER_MAJOR = 100.0 |
| `web/routers/plan.py:98` | money-round | plan._shift_month: total // _MONTHS_IN_YEAR |
| `web/routers/planned.py:211` | money-parse | _validate_amount: Decimal(amount) |
| `web/routers/recurring.py:232` | money-parse | _resolve_amount_inputs: Decimal(default_amount) |
| `web/routers/recurring.py:401` | money-scale | _formula_prefill: Decimal(100) |
| `web/routers/recurring.py:796` | money-format | new_override_form: {Decimal(rule.default_amount) / Decima...:.2f} |
| `web/routers/recurring.py:796` | money-parse | new_override_form: Decimal(rule.default_amount) |
| `web/routers/recurring.py:796` | money-scale | new_override_form: Decimal(100) |
| `web/routers/recurring.py:846` | money-parse | add_override: Decimal(amount.replace(',', '.')) |
| `web/routers/recurring.py:1043` | money-parse | promote_submit: Decimal(amount) |
| `web/routers/today.py:66` | money-scale | today: 100 * summary.totals.spent_minor |
| `web/routers/today.py:126` | money-parse | def _parse_amount_arg |
| `web/routers/today.py:141` | money-round | _parse_amount_arg: round(major * 100) |
| `web/routers/today.py:141` | money-scale | _parse_amount_arg: major * 100 |
| `web/today_data.py:90` | fx-def | def _convert_minor |
| `web/today_data.py:101` | money-parse | _convert_minor: Decimal(amount_minor) |
| `web/today_data.py:102` | fx-arith | _convert_minor: major * rate |
| `web/today_data.py:102` | fx-arith | _convert_minor: major * rate * dst_scale |
| `web/today_data.py:103` | money-round | ROUND_HALF_EVEN |
| `web/today_data.py:103` | money-round | _convert_minor: converted.quantize(Decimal('1'), rounding=ROUND_HALF_EVEN) |
| `web/today_data.py:127` | fx-call | collect_account_rows: fx_service.get_rate(conn, http, today, ccy, base_ccy) |
| `web/today_data.py:157` | money-round | pace_tag: budgeted * elapsed // days_in_month |

Totals (non-canonical, code): 78 rows: fx-arith 4, fx-call 6, fx-def 8, money-float 2, money-format 5, money-parse 17, money-round 25, money-scale 11. Templates: `/ 100`-style scaling 62, `|float`/`|round` 21, currency literals 14, formatting outside filters 61 (section 13). Reading:
- **FX conversion outside the canonical converter**: `services/budget.py` (2 closures + 2 `fx_svc.convert_cached` call sites), `services/forecast.py` (`_convert_native_to_base` + `_collect_fx_rates` + `get_rate`), `web/today_data.py` (`_convert_minor`, `get_rate`), `web/routers/ledger.py` (`convert` closure), `services/ledger_totals.py` (takes a callable). That is the Q-007 set; 4 hand-written `major * rate * dst_scale` arithmetic copies (2 non-canonical files).
- **Rounding**: 8 `ROUND_HALF_EVEN` uses in services/web (`analytics`, `balance`, `budget` x2, `forecast` x2, `today`, `today_data`), `ROUND_HALF_UP` in `recurring_formula` x2, `round(major * 100)` in `today.py:141`, floor division for money in `ledger._recurring_summary` and `today_data.pace_tag` (Q-076). The remainder are chart geometry (`web/charts.py`, `balance.sparkline_points`) which are not money but live in the same rule bucket; reclassify when G6 is written (scope the rule to monetary names).
- **Float**: `services/forecast.py:924,956` (`value_major: float`, `/ 100.0`) is the only float *money* in Python; the router constants `_MINOR_UNITS_PER_MAJOR = 100.0` (plan, forecast) feed it.
- **Parsing outside `domain.money.parse_amount_str`**: 8 router rows (`budget._parse_decimal`, `planned._validate_amount`, `recurring` x4, `today._parse_amount_arg`) and `services/recurring_formula` (`parse_percent_to_bps`, `build_term`) (A-08/Q-023).
- **Formatting outside the canonical filter**: `recurring.py:796` (`{Decimal/Decimal:.2f}`), `recurring_formula.py:72` (percent message), `charts._format_label` (`{value:,.2f}`).

## 10. Principle 9: Layering and imports

**Contracts checked.** `routers -/-> repositories`, `web -/-> db`, `domain -/-> services|repositories|web|db|adapters`, `repositories -/-> services|web`, `services -/-> web` (the first and fourth sets are the G1 contracts in prevention.md). Extra, reported as `info:`: `services -/-> db`, `web view-models/deps -/-> repositories`. TYPE_CHECKING imports excluded; imports at any nesting depth counted (a function-level import is still an edge).

**Detection.** `p09_p10_p11_imports_size_suppress.py`: AST import resolution (relative imports resolved), contract table, Tarjan SCC over the module graph, and every import inside a function body.

### 10.1 Contract-breaking imports (complete)

| File | Contract | Imports | Lines / target |
|---|---|---|---|
| `web/routers/accounts.py` | routers-not-repositories | 3 | 24, 24, 24 |
| `web/routers/auth.py` | routers-not-repositories | 2 | 37, 38 |
| `web/routers/budget.py` | routers-not-repositories | 2 | 36, 36 |
| `web/routers/categories.py` | routers-not-repositories | 1 | 13 |
| `web/routers/ledger.py` | routers-not-repositories | 5 | 21, 21, 21, 21, 21 |
| `web/routers/plan.py` | routers-not-repositories | 1 | 119 |
| `web/routers/planned.py` | routers-not-repositories | 5 | 19, 19, 19, 123, 124 |
| `web/routers/recurring.py` | routers-not-repositories | 6 | 26, 26, 26, 482, 482, 486 |
| `web/routers/settings.py` | routers-not-repositories | 2 | 25, 25 |
| `web/routers/settings_security.py` | routers-not-repositories | 3 | 19, 19, 20 |
| `web/routers/settings_users.py` | routers-not-repositories | 1 | 32 |
| `web/routers/today.py` | routers-not-repositories | 2 | 18, 18 |
| `web/routers/transactions.py` | routers-not-repositories | 3 | 25, 25, 25 |
| `repositories/recurring.py:31` | repositories-not-services | 1 | repositories.recurring -> services.recurring (top-level) |
| `web/app.py:23` | web-not-db | 1 | web.app -> db.connection (top-level) |
| `web/deps.py:16` | web-not-db | 1 | web.deps -> db.connection (top-level) |
| `web/middleware/auth.py:38` | web-not-db | 1 | web.middleware.auth -> db.connection (top-level) |
| `web/retention_task.py:16` | web-not-db | 1 | web.retention_task -> db.retention (top-level) |
| `web/routers/health.py:53` | web-not-db | 1 | web.routers.health -> db.connection (fn-level) |

- `routers -/-> repositories`: 36 import lines in 13 routers (the structural cause of P5/Q-045). Fix = service layer for CRUD (T-Q2xx epic "services for CRUD").
- `web -/-> db`: `web/app.py`, `web/deps.py`, `web/middleware/auth.py`, `web/retention_task.py`, `web/routers/health.py` (function-level). G1 whitelists `db.connection` for `deps.get_db`; the others need a `db` facade or move (B-15).
- `repositories -/-> services`: `repositories/recurring.py:31` imports `services.recurring.first_due_on_or_after`; the pure date function belongs in `domain/recurring.py`. This is also the SCC below.

### 10.2 Extra-contract rows (info)

| Location | Contract | Edge |
|---|---|---|
| `services/users.py:33` | services-not-db | services.users -> db.connection (top-level) |
| `web/deps.py:18` | web-vm-not-repositories | web.deps -> repositories.sessions (top-level) |
| `web/deps.py:19` | web-vm-not-repositories | web.deps -> repositories.sessions (top-level) |
| `web/today_data.py:20` | web-vm-not-repositories | web.today_data -> repositories.accounts (top-level) |

### 10.3 Import cycle

One strongly connected component (3 modules): `repositories.recurring <-> services.recurring <-> services.recurring_formula` (Q-047; explains ~9 of the PLC0415).

### 10.4 Function-level imports (PLC0415, 37) and late imports (E402, 3)

| File | Count | line target |
|---|---|---|
| `db/migrate.py` | 1 | 223 import json |
| `services/forecast.py` | 1 | 495 services.balance |
| `services/recurring.py` | 12 | 384 repositories.categories, repositories.recurring, repositories.transactions; 389 repositories._shared; 390 services.audit; 391 services._promotion, services._promotion; 408 services.recurring_fo... |
| `services/recurring_formula.py` | 8 | 166 repositories.recurring; 167 services.recurring, services.recurring; 213 repositories.recurring; 336 services.recurring, services.recurring; 392 repositories.recurring; 432 from dataclasses impo... |
| `web/app.py` | 1 | 238 import importlib |
| `web/routers/health.py` | 1 | 53 db.connection |
| `web/routers/plan.py` | 5 | 116 import calendar as _cal; 117 import dataclasses as _dc; 119 repositories.recurring; 120 services.preferences; 233 import calendar as _cal |
| `web/routers/planned.py` | 5 | 70 import json; 123 repositories.transactions; 124 repositories._shared; 151 import json; 184 web.routers.ledger |
| `web/routers/recurring.py` | 4 | 419 import json; 482 repositories.recurring, repositories.transactions; 486 repositories._shared; 511 import json |
| `web/routers/today.py` | 1 | 216 web.routers.recurring, web.routers.recurring |
| `web/routers/transactions.py` | 1 | 195 web.routers.ledger |

By cause (B-12): ~9 break the recurring cycle, ~28 are unnecessary (importing a module that is already import-safe), router-to-router private imports in `recurring.py`/`planned.py`. All 37 carry a `noqa: PLC0415`; zero have a justification beyond the code.

## 11. Principle 10: Signatures and size

**Rules.** Functions <= 50 lines; files <= 800 (400 warn); cyclomatic complexity <= B (radon rank, i.e. < 11); nesting <= 4; PLR0917 (> 5 positional) and PLR0913 (> 5 params; ignored globally today).

**Detection.** `p09_p10_p11_imports_size_suppress.py` (AST line spans; own McCabe approximation; nesting of if/for/while/try/with) and the authoritative radon list from `baseline/radon-cc.txt` (`inventory/p10-radon.txt`, 33 blocks).

### 11.1 Files over 400 / 800 lines

| File | Lines | Level |
|---|---|---|
| `web/routers/recurring.py` | 1115 lines | **> 800: split** |
| `services/forecast.py` | 978 lines | **> 800: split** |
| `web/routers/auth.py` | 760 lines | > 400: warn |
| `services/recurring.py` | 696 lines | > 400: warn |
| `services/budget.py` | 664 lines | > 400: warn |
| `web/charts.py` | 601 lines | > 400: warn |
| `services/recurring_formula.py` | 596 lines | > 400: warn |
| `web/routers/planned.py` | 586 lines | > 400: warn |
| `services/users.py` | 561 lines | > 400: warn |
| `repositories/recurring.py` | 552 lines | > 400: warn |
| `web/routers/accounts.py` | 509 lines | > 400: warn |
| `web/routers/transactions.py` | 507 lines | > 400: warn |
| `web/routers/ledger.py` | 491 lines | > 400: warn |
| `services/auth.py` | 490 lines | > 400: warn |
| `web/routers/budget.py` | 428 lines | > 400: warn |
| `repositories/users.py` | 418 lines | > 400: warn |

### 11.2 Complexity C or worse (radon, 33 blocks) and nesting > 4

| Location | Rank | Function (cc) |
|---|---|---|
| `db/migrate.py:86` | C | _split_sql_statements cc=18 |
| `db/migrate.py:280` | C | apply_migrations cc=11 |
| `db/startup_migrate.py:102` | C | prune_backups cc=12 |
| `repositories/planned.py:68` | C | _append_filter_clauses cc=14 |
| `repositories/transactions.py:69` | C | _append_filter_clauses cc=16 |
| `services/budget.py:253` | C | _committed_by_category cc=12 |
| `services/budget.py:454` | C | month_summary cc=19 |
| `services/budget.py:603` | C | yearly_grid cc=11 |
| `services/forecast.py:530` | C | forecast cc=11 |
| `services/forecast.py:710` | C | _month_flow_sums cc=15 |
| `services/recurring.py:107` | C | generate_occurrences cc=12 |
| `services/recurring.py:356` | C | promote_recurring cc=17 |
| `services/recurring_formula.py:384` | C | validate_formula_sources cc=16 |
| `web/auth_cookies.py:219` | C | safe_next cc=13 |
| `web/charts.py:144` | C | line_area cc=17 |
| `web/charts.py:297` | C | grouped_bars cc=16 |
| `web/middleware/auth.py:145` | C | AuthRequiredMiddleware cc=11 |
| `web/routers/accounts.py:186` | C | create_account cc=11 |
| `web/routers/budget.py:170` | C | new_override_form cc=12 |
| `web/routers/budget.py:235` | C | create_override cc=12 |
| `web/routers/ledger.py:140` | D | _hydrate_recurring_rows cc=29 |
| `web/routers/ledger.py:395` | C | index cc=11 |
| `web/routers/plan.py:68` | E | plan cc=31 |
| `web/routers/planned.py:220` | C | create_planned cc=13 |
| `web/routers/planned.py:338` | C | update_planned cc=11 |
| `web/routers/recurring.py:149` | C | _resolve_dest_account cc=12 |
| `web/routers/recurring.py:269` | C | create_rule cc=16 |
| `web/routers/recurring.py:470` | C | recurring_batch_undo cc=12 |
| `web/routers/recurring.py:633` | C | update_rule_handler cc=18 |
| `web/routers/recurring.py:1016` | C | promote_submit cc=13 |
| `web/routers/settings.py:52` | C | drawer cc=19 |
| `web/routers/transactions.py:238` | C | create_txn cc=16 |
| `web/routers/transactions.py:358` | C | update_txn cc=12 |

Nesting > 4: `repositories/recurring.py:200` _normalise_rule_patch depth 6; `web/routers/plan.py:68` plan depth 5; `web/routers/transactions.py:238` create_txn depth 5.

### 11.3 Functions over 50 lines (41, complete)

| Location | Function | Lines |
|---|---|---|
| `web/routers/plan.py:68` | plan | 184 |
| `services/budget.py:454` | month_summary | 147 |
| `services/recurring.py:356` | promote_recurring | 143 |
| `services/forecast.py:778` | forecast_monthly | 128 |
| `web/routers/recurring.py:269` | create_rule | 119 |
| `web/routers/recurring.py:633` | update_rule_handler | 108 |
| `web/charts.py:144` | line_area | 102 |
| `web/charts.py:297` | grouped_bars | 101 |
| `services/recurring_formula.py:485` | preview | 93 |
| `services/forecast.py:530` | forecast | 89 |
| `web/routers/ledger.py:140` | _hydrate_recurring_rows | 80 |
| `web/routers/transactions.py:238` | create_txn | 80 |
| `db/migrate.py:134` | _backfill_recurring_next_due | 79 |
| `web/routers/transactions.py:358` | update_txn | 77 |
| `db/migrate.py:280` | apply_migrations | 72 |
| `repositories/recurring.py:428` | upsert_override | 71 |
| `web/routers/recurring.py:470` | recurring_batch_undo | 70 |
| `services/reconciliation.py:62` | reconcile | 69 |
| `web/routers/recurring.py:1016` | promote_submit | 69 |
| `services/recurring.py:501` | skip_and_advance | 68 |
| `web/charts.py:519` | sparkline | 67 |
| `web/routers/accounts.py:279` | update_account | 67 |
| `web/routers/planned.py:220` | create_planned | 67 |
| `services/forecast.py:710` | _month_flow_sums | 66 |
| `web/routers/accounts.py:445` | reconcile_submit | 65 |
| `web/routers/planned.py:338` | update_planned | 64 |
| `services/budget.py:253` | _committed_by_category | 63 |
| `web/charts.py:437` | horizontal_bars | 62 |
| `web/routers/accounts.py:186` | create_account | 62 |
| `web/routers/budget.py:170` | new_override_form | 62 |
| `web/routers/planned.py:484` | promote_submit | 61 |
| `web/routers/planned.py:112` | planned_batch_undo | 60 |
| `web/routers/budget.py:235` | create_override | 59 |
| `web/routers/recurring.py:181` | _resolve_amount_inputs | 59 |
| `web/routers/recurring.py:810` | add_override | 58 |
| `services/auth.py:416` | authenticate_passkey_finish | 54 |
| `services/forecast.py:654` | _planned_budget_per_month | 54 |
| `services/recurring_formula.py:191` | _sum_category_in_month | 52 |
| `web/routers/today.py:42` | today | 52 |
| `logging.py:96` | configure | 51 |
| `services/income.py:43` | next_anchor_date | 51 |

### 11.4 Signatures: PLR0917 (positional > 5) and PLR0913 (params > 5)

32 functions exceed 5 positional parameters (32 `noqa: PLR0917` suppressions today); 66 exceed 5 parameters in total (PLR0913 ignored globally; ruff-all baseline: 66). By package: positional>5 services 8, web/routers 24; params>5 repositories 5, services 28, web/routers 33. Complete lists in `inventory/p10-size.txt`. B-08 lists the 8 service signatures with adjacent same-typed parameters (swap risk); the other 24 are route handlers whose arity is dictated by FastAPI `Form()` parameters (candidates for a pydantic form model).

## 12. Principle 11: Suppressions

**Rule (G4).** Every `noqa`, `type: ignore`, `nosec`, `pragma: no cover` carries a reason **on the same line**; bulk codes are ratcheted; blanket forms are banned (`PGH`).

**Detection.** `p09_p10_p11...py` (rule `p11`): every inline suppression with code list, same-line reason, and whether a comment line sits directly above (not accepted as a reason by G4); plus `pyproject.toml` suppressions.

| Kind | Same-line reason | Count |
|---|---|---|
| fmt: skip | NO reason | 1 |
| noqa | NO reason | 82 |
| noqa | reason | 39 |
| nosec | reason | 1 |
| pragma: no cover | NO reason | 6 |
| pragma: no cover | reason | 21 |
| type: ignore | NO reason | 5 |

`noqa` by code: PLC0415 37, PLR0917 32, DTZ011 18, PLR2004 6, PLR0911 6, S105 5, PLR0915 4, N818 4, E402 3, PLR0912 3, PLW0603 2, B008 2, S704 2, S104 1, ARG001 1. Per-file densities and the full list (path:line, code, reason flag, comment-above flag) are in `inventory/p11-suppressions.txt` (168 rows including config).


`pyproject.toml` suppressions (config rows): global ruff ignores `ANN401`, `PLR0913`, `S101`; per-file ignores `S608` (migrate.py, repositories), `B008` (routers); coverage `exclude_lines` containing the substring-matching `\.\.\.` (Q-014, G5); mypy `ignore_missing_imports` for plotly/sqlfluff/djlint/pandas/pyarrow (plotly is no longer a dependency per ADR-0054: stale).

## 13. Principle 12: Logic in templates (counts only; ADR-0107)

ADR-0107 replaces every template and the presentational JS; only counts are recorded. The same rules become the template guard (G9) so that the redesign tree starts at zero. **Rules:** `tpl-scale` (`/ 100`, `* 100`), `tpl-float` (`|float`, `|round`, `|int` on amounts), `tpl-arith` (other arithmetic in an expression), `tpl-set` (`{% set %}` derived values), `tpl-domain-if` (`{% if %}` on direction/kind/status/cadence/currency literals), `tpl-currency-lit`, `tpl-format` (formatting outside shared filters). `p12_templates.py`; per-file counts in `inventory/p12-templates.txt`.

| Rule | Sites |
|---|---|
| tpl-arith | 49 |
| tpl-currency-lit | 14 |
| tpl-domain-if | 15 |
| tpl-float | 21 |
| tpl-format | 61 |
| tpl-scale | 62 |
| tpl-set | 235 |
| **total** | 457 |

By template directory: `partials` 113, `_partials` 93, `plan` 88, `today` 50, `ledger` 46, `settings` 25, `accounts` 16, `budget` 13, `errors` 8, `dev` 3, `recurring` 2. Kept JS: `p12-js-kept.txt` has 0 money or clock rows (`htmx-csrf.js`, `passkeys.js`, `users-admin.js` are clean on that axis); `passkeys.js` clones are in 2.4 (Q-071).

## 14. Principle 13: other principles stated by CLAUDE.md, requirements section 3 and the global rules

Extracted principles beyond P1-P12: **(a)** every query scoped to the acting user, never a literal user id (ADR-0061, CLAUDE.md Q-001 class); **(b)** "never silently swallow errors" and "handle errors explicitly" (common coding-style); **(c)** `assert` is not validation; **(d)** no `print`/debug statements (code-review rule); **(e)** `mypy --strict`, no `Any` (type holes; `ANN401` ignored globally); **(f)** no magic numbers (common coding-style; `PLR2004` suppressed 6x); **(g)** `data/budget.sqlite` is never referenced by code outside config default; **(h)** no TODO debt markers; **(i)** server binds 127.0.0.1 only (v3 deviates by design, ADR-0100; not a violation); **(j)** deep nesting <= 4 (P10); **(k)** no hardcoded values (P1 literals). `p13_other.py` rules: `literal-user-id`, `prod-db-path`, `silent-except`, `broad-except`, `assert-in-src`, `print-call`, `todo-marker`, `any-annotation`, `domain-literal`, `magic-number`, `repeated-literal`.

### 14.1 Literal user ids (complete)

| Location | Detail | Disposition |
|---|---|---|
| `db/seed.py:26` | [db] _seed_demo_accounts: user_id = 1 | demo seeding: pass the seeded user explicitly |
| `services/recurring.py:250` | [services] _build_lookup_stub: RecurringRule(id=0, user_id=0, cadence=cadence, start_da... | `user_id=0` in a lookup stub (not a scoping bug, but a sentinel row built for the formula resolver) |
| `web/routers/budget.py:387` | [web.routers] set_income_anchor: positional preferences_svc.set_income_anchor_category_... | **Q-001**: income-anchor endpoint hard-wired to user 1 |
| `web/routers/budget.py:394` | [web.routers] set_income_anchor: positional preferences_svc.set_income_anchor_category_... | **Q-001**: income-anchor endpoint hard-wired to user 1 |

### 14.2 Swallowed and broad exceptions

| Location | Rule | Detail | Disposition |
|---|---|---|---|
| `db/migrate.py:210` | broad-except | _backfill_recurring_next_due: except Exception | review: narrow or log |
| `db/migrate.py:251` | broad-except | _upgrade_formula_schema_v1_to_v2: except Exception | review: narrow or log |
| `db/migrate.py:332` | broad-except | apply_migrations: except Exception | review: narrow or log |
| `db/retention.py:31` | broad-except | main: except Exception | review: narrow or log |
| `db/startup_migrate.py:183` | broad-except | main: except Exception | review: narrow or log |
| `domain/money.py:229` | silent-except | parse_amount_str: except (InvalidOperation, ValueError): return None | parse helper returning a sentinel: legitimate but DRY (P1 `_parse_*`) |
| `repositories/_shared.py:130` | broad-except | transaction: except Exception | review: narrow or log |
| `services/_passwords.py:65` | silent-except | verify_password: except (ValueError, TypeError, UnicodeEncodeError): return F... | review |
| `services/replication_health.py:51` | silent-except | read_status_text: except FileNotFoundError: return None | review |
| `services/replication_health.py:60` | silent-except | _parse_time: except ValueError: return None | parse helper returning a sentinel: legitimate but DRY (P1 `_parse_*`) |
| `web/app.py:103` | silent-except | _install_sigterm_observer: except ValueError: return | review |
| `web/app.py:124` | silent-except | _close_app_connections: except sqlite3.Error: continue | review |
| `web/app.py:243` | silent-except | _register_routers: except ImportError: continue | **Q-073**: router registration skips a router that fails to import |
| `web/auth_cookies.py:156` | silent-except | _decode_envelope: except (binascii.Error, ValueError): return None | review |
| `web/auth_cookies.py:162` | silent-except | _decode_envelope: except ValueError: return None | review |
| `web/auth_cookies.py:182` | silent-except | verify_challenge: except (KeyError, ValueError, binascii.Error): return None | review |
| `web/retention_task.py:28` | broad-except | run_forever: except Exception | review: narrow or log |
| `web/routers/auth.py:223` | silent-except | _is_ip: except ValueError: return False | review |
| `web/routers/budget.py:319` | silent-except | _parse_decimal: except (InvalidOperation, TypeError, ValueError): return None | parse helper returning a sentinel: legitimate but DRY (P1 `_parse_*`) |
| `web/routers/categories.py:58` | silent-except | _validate_direction: except ValueError: return None | parse helper returning a sentinel: legitimate but DRY (P1 `_parse_*`) |
| `web/routers/health.py:57` | broad-except | ready: except Exception | review: narrow or log |
| `web/routers/health.py:65` | broad-except | ready: except Exception | review: narrow or log |
| `web/routers/ledger.py:49` | silent-except | _parse_date: except ValueError: return None | parse helper returning a sentinel: legitimate but DRY (P1 `_parse_*`) |
| `web/routers/ledger.py:58` | silent-except | _parse_int: except (TypeError, ValueError): return None | parse helper returning a sentinel: legitimate but DRY (P1 `_parse_*`) |
| `web/routers/planned.py:38` | silent-except | _parse_date: except ValueError: return None | parse helper returning a sentinel: legitimate but DRY (P1 `_parse_*`) |
| `web/routers/recurring.py:45` | silent-except | _parse_date: except ValueError: return None | parse helper returning a sentinel: legitimate but DRY (P1 `_parse_*`) |
| `web/routers/recurring.py:54` | silent-except | _parse_int: except (TypeError, ValueError): return None | parse helper returning a sentinel: legitimate but DRY (P1 `_parse_*`) |
| `web/routers/recurring.py:145` | silent-except | _validate_cadence: except ValueError: return None | parse helper returning a sentinel: legitimate but DRY (P1 `_parse_*`) |
| `web/routers/today.py:139` | silent-except | _parse_amount_arg: except (TypeError, ValueError): return None | parse helper returning a sentinel: legitimate but DRY (P1 `_parse_*`) |
| `web/routers/transactions.py:60` | silent-except | _parse_date: except ValueError: return None | parse helper returning a sentinel: legitimate but DRY (P1 `_parse_*`) |
| `web/routers/transactions.py:69` | silent-except | _parse_int: except (TypeError, ValueError): return None | parse helper returning a sentinel: legitimate but DRY (P1 `_parse_*`) |

### 14.3 Other rows (counts; full lists in `inventory/p13-other.txt`)

| Rule | Rows | By package |
|---|---|---|
| assert-in-src | 32 | repositories 15, services 3, web 1, web/routers 13 |
| print-call | 2 | db 2 |
| any-annotation | 80 | domain 5, repositories 13, root 6, services 16, web 4, web/routers 36 |
| magic-number | 20 | services 4, web 12, web/routers 4 |
| prod-db-path | 2 | cli 1, root 1 |
| todo-marker | 0 | - |
| repeated-literal | 30 | db 4, repositories 1, root 1, web 11, web/middleware 1, web/routers 12 |
| domain-literal | 94 | db 2, root 2, services 7, web 4, web/routers 79 |

Notes: `assert-in-src` (32, ruff `S101` globally ignored) are 15 in repositories (row-existence asserts after insert) - raising typed errors is the compliant form. `print-call` (2) are in `db/` CLI-style scripts. `prod-db-path` (2) are the config default and a CLI docstring: compliant. `any-annotation` (80): 36 in routers (FastAPI form helpers), 16 services, 13 repositories; `mypy` Any coverage baseline 96.18%. TODO markers: 0. `magic-number` (20) is the PLR2004 class (thresholds in `web/charts.py` geometry and `today_data.pace_tag`).

## 15. New guards needed (principles with no guard in prevention.md section 2)

All new guards follow prevention.md 2.1: one allowlist file per guard `tests/architecture/allowlists/<guard>.toml` (per `path`, `count`, `finding`, `reason`), ratchet both directions, teaching failure messages, run on every commit (G0), **new files start at zero**. The allowlist of each guard is generated from the corresponding `inventory/*.txt` (rows minus those marked `accept`), which is why the inventory scripts emit rule names identical to the guard rule names.

| Guard | Rule (AST / regex) | Scope | Allowlist = inventory file | Notes |
|---|---|---|---|---|
| **G18 clone ratchet** | `p01_dry.py` body-hash groups (>= 4 statements, >= 8 lines) must not grow; same-name private helpers (`_x`) defined in two modules fail unless one imports the other | `src/budget_planner/**` | `p01-clones-ast`, `p01-same-name` (REAL rows) | pylint duplicate-code and jscpd stay out of lint (prevention.md dropped them); this AST variant is cheap (seconds) and exact-shape only |
| **G19 literal registry** | HTMX event names, header names (`HX-*`), `text/html`, ISO currency codes, `Europe/Warsaw`, `Direction.*`/`Cadence.*` value strings may appear as string literals only in their defining module (`web/htmx.py`, `web/http_headers.py`, `config.py`, `domain/enums.py`) | `web/`, `services/`, `repositories/` | `p13-other` `domain-literal` rows (94) + `repeated-literal` rows | complements G12 (emitter/listener matrix) and S1 |
| **G20 functional-first** | (a) class definitions other than frozen dataclass / NamedTuple / TypedDict / Protocol / Enum / Exception / pydantic DTO; (b) module-level `list`/`dict`/`set` literals or constructors (use tuple/frozenset/`MappingProxyType`); (c) `global`; (d) `lru_cache`/`cache`; (e) in-place mutation of parameters / module state / `setattr` on frozen instances (`p03` rule set) | `src/budget_planner/**` | `p02-functional` + `p03-immutability` rows not marked accept (framework rows keep category `framework` with reason) | local accumulators exempt by rule, so the allowlist stays small |
| **G22 purity** | `domain/`: no import of `sqlite3`, `httpx`, `os`, `logging`, `time`, `random`, the stdlib CSPRNG module, `config`; no call to clock/env/open/print. `services/`: no `httpx`/`urllib.request`/`socket`/`subprocess` import or call, no `get_settings()`, no CSPRNG/`random` calls, no clock call (clock only through an argument), no `logging` unless the operator keeps the logging exception (section 17 Q1). Transitive: no `services/` function may reach network I/O (call-graph rule from `p04`) | `domain/`, `services/`, web view-models | `p04-side-effects` | pairs with G1 import-linter (import-linter cannot see calls) |
| **G23 thin router** | per router function: fails when it has an R, S, T or A signal (repository call, SQL, transaction control, arithmetic) or CC > 8 or > 40 lines; non-route helpers in router modules are limited to an allowlisted set | `web/routers/*.py` | `p05-thin-web` (`logic-in-router` + `helper-in-router`, 154 rows) | G1 (routers not repositories) removes the R signal structurally; G23 catches A/S/D/G; ratchet by function name + signal set so edits keep passing |
| **G24 read filters** | in `repositories/`, a `SELECT` on a soft-delete table needs `deleted_at` or an explicit `include_deleted`; on a user-owned table needs `user_id` unless the function name is on a list of secret-keyed lookups; mutations on audited tables must go through `mutate`/`write_audit` | `repositories/` | `p06-read-filters`, `p06-unaudited-mutations` (with reasons) | extends `test_user_id_filter` (statement-level) with function-level soft-delete and audit checks; tables with `deleted_at`/`user_id` derived from `migrations/*.sql` so new tables are covered automatically |
| **G25 size/complexity ratchet** | ruff `C901` (max-complexity 10), `PLR0915` (too many statements, approximates 50 lines), `PLR0912`, `PLR0913` (enable, with allowlist) and an AST test for files > 800 / functions > 50 lines / nesting > 4 | `src/` | `p10-size`, `p10-radon` | replaces the 4 `PLR09xx` noqa suppressions by a counted allowlist; today only `PLR0917` is enabled |
| **G26 error handling and hygiene** | no `except ...: pass/continue/return <const>` without a log or re-raise unless on the `parse-sentinel` allowlist; no broad `except Exception` outside `web/errors.py`/`db/`; no `assert` in `src` (enable ruff `S101` in src, keep ignoring it in tests); no `print`; no `TODO` without ticket; no `Any` in public signatures (enable `ANN401` with allowlist) | `src/` | `p13-other` rules `silent-except`, `broad-except`, `assert-in-src`, `print-call`, `any-annotation` | `ruff` `S110`, `S112`, `BLE001`, `T201`, `S101`, `ANN401` cover most; the allowlist is per-file counts |
| **G27 money scope extension of G6** | rule set `money-scale`, `money-round`, `money-format`, `money-parse`, `fx-*`, scoped to monetary identifier names to avoid the chart-geometry noise recorded here | `services/`, `web/`, `repositories/` | `p08-money` non-canonical rows (78) | G6 in prevention.md names the concepts; this fixes the detection set and the false-positive reduction (chart geometry, id parsing) |

Existing guards that consume inventory data unchanged: G1 (`p09-layering`: 1 repo->service, 36 router->repo, 5 web->db), G2 (`p06-sql-outside-repos` real rows), G3+S4 (`p07-clock`, 45 rows), G4 (`p11-suppressions`, `p09-lazy-imports`), G7b (`p13-other` `literal-user-id`), G9 (`p12-templates`, new templates start at 0).

## 16. Proposed remediation epics (to be turned into T-Q2xx tasks)

One epic per principle x package. **Pre-P3** = should land before v4 Phase 3 (the `[pre-v4-P3]` remediation; also unblocks the Sourdough redesign, whose routers/view models are kept). Effort S/M/L as in section 1. "Allowlist delta" = rows removed from the guard's allowlist when done (the burn-down unit).

| Epic | Principle x package | Scope | Effort | Before v4 Phase 3? | Allowlist delta / guard |
|---|---|---|---|---|---|
| E01 | DRY / services | Canonical modules S1: `services/fx.to_base` + converter factory, `domain/periods.py`, `domain/transactions.signed_legs`, `services/aggregates.py`, `pending_occurrences`, `expense_category_ids`, `pick_tier`, validators; delete the copies (Track A concepts 1-8, 10, 12) | L | yes | G6/S1 allowlist (~45 copies), G7 xfails |
| E02 | DRY / repositories | Generic CRUD helpers in `repositories/_shared` (find_by_id, find_by_name, list_all, update patch, soft_delete, undelete, list_recently_deleted, row hydration): remove 9 clone groups (36 functions) and 7 repo pylint blocks | M | no (mechanical, behaviour-preserving, large diff); do after E07 | G18 (36 rows) |
| E03 | DRY / web | `web/params.py` (`parse_date`, `parse_int`, amount parse via `domain.money`), `web/htmx.Event` + `invalidate()`, shared `_hydrate_rows`, middleware `_wants_json`/safe-next; passkeys.js ceremony extraction (kept JS) | M | yes (HTMX contract and parsers are Q-023/Q-038) | G19 (94 literals), G18 web rows, A-19 |
| E04 | Functional / web + root | Replace 6 `BaseHTTPMiddleware` classes + `CacheControlMiddleware` + `logging.Filter` subclass with pure ASGI functions (or accept as `framework` allowlist category with ADR note); funnel `request.state`/`response.headers` mutation through 2 helpers | M | no | G20 (framework rows 14 + classes 8) |
| E05 | Functional / data | 13 module constants to `MappingProxyType`/tuples; replace `_TX_DEPTH` with a connection-attached depth (no `id(conn)` global); remove 2 `global`s; replace `lru_cache get_settings` with an app-scoped settings object passed explicitly; fix `Settings._finalise` setattr; drop memo-by-argument in `recurring_formula` | S | yes (small) | G20 (23 rows) |
| E06 | Purity / services (FX) | Remove network I/O from render paths: services take pre-fetched rate maps or an injected `RatePort`; move `httpx.Client` construction out of `forecast.monthly_projection` and `today_data`; scheduled/explicit refresh job (Q-007) | L | yes (Q-007 is High) | G22 (eff-net 5 + reach 5 + 4 web) |
| E07 | Purity / services (clock, entropy, settings, logging) | Single `clock.py` + injected `today`; `TokenSource` port for `secrets`; settings values passed as arguments (3 `get_settings()` reads, 7 `config` imports); decision on logging in services (Q1) | M | yes (clock S4 is T-Q15 scaffold; callers migrate here) | G22, G3 (45 clock rows) |
| E08 | Thin web / services CRUD | Service layer for CRUD (accounts, categories, planned, transactions, recurring, budget, settings, auth): routers stop importing repositories; move validation into services (Q-004, Q-028); order: transactions/planned first (Q-004), recurring last (largest) | L | partly: transactions + planned + recurring before Phase 3 (they carry Q-004/Q-024/Q-028 logic); rest after redesign | G1 (36 import rows), G23 (88 + 66 rows) |
| E09 | Thin web / view models | Move arithmetic/aggregation out of routers: `plan()` (E31) -> service, `today` left-per-day, `ledger._recurring_summary`/`_actual_day_nets`, `budget` router tier reads, `_shift_month`; routers return one view model | L | yes (needed by the redesign's view-model contract and Q-003/Q-010/Q-039) | G23 A/G/D/C rows |
| E10 | Repository discipline | Move 2 service SQL queries (`services/accounts.py`) and the 3 router SQL sites into repositories; `audit_log` reads via repository with `user_id`; classify the 22 read rows (name `include_deleted` or add predicate) and the 3 unaudited mutations; transaction helper for compound mutations (G8) | M | yes (Q-024/Q-025 are Medium-High) | G2 (6 exec rows), G24 (22 + 3), G8 |
| E11 | Money / services + web | Delete float path in forecast + router constants, one rounding helper, complete exponent table, `parse_money_input` in `domain/money`, 8 router parsers replaced, 5 formatting sites on filters | M | yes (Q-011/Q-029/Q-076) | G6/G27 (78 rows) |
| E12 | Layering / imports | Break the recurring cycle (move `first_due_on_or_after` to `domain/recurring`), `web -> db` facade, remove 37 lazy imports (9 cycle-driven vanish with the cycle, 28 become top-level), fix 3 E402 | M | yes (cycle fix is cheap; unblocks E08) | G1, G4 (PLC0415 37 -> 0) |
| E13 | Size / signatures | Split `recurring` router (1115) and `forecast` service (978); decompose 33 radon-C+ functions and 41 functions > 50 lines; pydantic form models for 24 route handlers with > 5 positional parameters; keyword-only for the 8 swap-risk service signatures | L | partly: `plan()` (E) and `recurring.py` with E08/E09; remainder after redesign | G25, G4 (PLR0917 32 -> 0) |
| E14 | Suppressions | Reason on every inline suppression (82 noqa + 6 pragma + 5 type-ignore + 1 fmt without reason), `PGH` on, coverage `exclude_lines` fix (Q-014), stale mypy overrides | S | yes (cheap, G4/G5 land first in T-Q15) | G4 (87 rows) |
| E15 | Hygiene | Narrow/loggers for the 9 broad excepts and review the 22 swallowed ones (13 are parse sentinels covered by E03); replace 32 `assert`s in src with typed errors; remove 2 `print`; `Any` in 80 signatures (typed form helpers) | M | no | G26 (~145 rows) |
| E16 | Templates (redesign) | No remediation of the old tree; the redesign starts at zero for `tpl-*` rules (G9) | n/a | built into T-UR | G9 |

Sequencing: E12 -> E10 -> E08 (services for CRUD needs the cycle gone and SQL in repositories) -> E09 -> E01/E11 (canonical modules once routers are thin) -> E06/E07 (purity needs the converter) ; E04/E05/E14 are independent and can run in parallel with anything; E02/E13/E15 last (mechanical, high diff volume, conflict-prone with the redesign's router edits). Per-epic order inside a package is by Q severity.

## 17. Limits of the detection and open questions

**Limits (be careful when turning rows into allowlists).**
- AST rules are over-approximate on purpose: every table has a disposition column; rows tagged `accept` or `canonical` are excluded from the violation counts, not from the files.
- P3 does not follow aliases; P4's call graph resolves through first-party imports and simple names, so calls through parameters (`converter(...)` closures, injected callables) are not traced (this under-reports FX reach, e.g. `ledger_totals.day_nets(convert=...)`).
- P5 signals are syntactic: `A` fires on any non-string subtraction/multiplication (including `len(x) - 1` index maths); `D` on any comparison touching `.direction/.kind/.cadence/.status` or an enum class. A function flagged only `A`/`C` may be benign; the guard (G23) therefore allowlists by function and signal set.
- P6(c) is function-level, not statement-level; it complements `test_user_id_filter` (statement-level).
- P8 `money-round`/`money-scale` still include chart-geometry and percent arithmetic (e.g. `today.py:66` `100 * spent / budget` is a percentage, not scaling by minor units); G27 scopes by monetary identifier names.
- P10 own CC differs by 0-2 from radon; `p10-radon.txt` (baseline) is authoritative for C+.
- P12 is regex-based over Jinja expressions; counts, not line lists; ADR-0107 supersedes the tree anyway.
- Python only: Terraform, workflows, SQL migrations (52 DB-clock rows recorded, not violations) and tests are out of scope; tests have their own rule set (Track F, R5).

**Questions for the operator.**
1. Logging inside services (17 rows in 7 modules): is `logging.getLogger` a permitted cross-cutting concern, or must services return structured diagnostics and let the web/adapters layer log? Default proposed: permitted via a single `get_logger` facade; G22 then bans only direct `logging` imports that bypass it.
2. Starlette `BaseHTTPMiddleware` and `APIRouter` module singletons: accept as `framework` allowlist category (proposed) or convert to pure ASGI?
3. Pydantic `BaseSettings` mutating itself in `_finalise` (setattr bypass): move derived values to a frozen `Resolved` dataclass built from settings (proposed).
