# Post-v3 Code-Quality Audit — Implementation Plan

See [README.md](README.md) for motivation and deliverables. This file covers **how** the audit runs.

---

## 0 · Guiding principles

1. **Read-only first.** Phases 1–3 change no production code, tests or config on the work branch. The only exceptions are the audit's own files under `docs/plans/quality-audit/`. Experiments (tool runs, Mutmut, repro tests) run in the audit worktree and are committed only as reports.
2. **Pinned commit.** Every finding cites `path:line` at the audit commit `AUDIT_SHA`, which is recorded in `findings.md`. Line numbers are only valid at that SHA.
3. **Evidence over opinion.** A finding needs either a reproduction (a failing test, a request or a script output) or a precise code citation that shows the defect. "Looks wrong" belongs in a track's *questions* list, not in the register.
4. **One best mitigation.** Each finding names the single recommended fix. Alternatives are listed only when the trade-off is genuinely open and needs a decision from the operator.
5. **Root cause tags.** Every finding carries a root-cause class (§5). Phase 4 works on classes, not on individual findings.
6. **Prod DB is hands off** (CLAUDE.md "Databases"). Any repro uses `--db=/tmp/<scratch>.sqlite` or `data/demo.sqlite`. No tool, fixture or script may resolve to `data/budget.sqlite`.
7. **Docs-first still applies to the outputs.** Prevention edits (Phase 4) and remediation tasks (Phase 5) go through the CLAUDE.md change policy: ADR → requirements → tasks → code.

---

## 1 · Phase 0 — Preconditions (T-Q01)

- v3 has shipped: v3 Phase 4 validation tasks are ✅ and prod has been cut over.
- Freeze `AUDIT_SHA` as the tip of the shipped branch. Create the audit worktree and branch `audit/quality` from it. Phases 1–3 work on that branch only.
- Record in `findings.md`: `AUDIT_SHA`, date, Python and tool versions, and LOC / file counts per package (`domain`, `services`, `repositories`, `web/routers`, `web/templates`, `web/static`, `db`, `adapters`, `cli`).
- Build a scratch DB: `just dev --db=/tmp/audit.sqlite`, seeded from `data/demo.sqlite` (copy the file; never point at prod).
- Confirm with `just ci` that the suite is green at `AUDIT_SHA`. A red baseline is itself finding Q-000.

---

## 2 · Phase 1 — Automated baseline (T-Q02, T-Q03)

The tools run in report-only mode. Nothing is added to the gates yet; adding gates is a Phase 4 decision. Install extra tools ad hoc in the audit worktree (`uv run --with <tool>`) and do **not** commit dependency changes. Raw output goes to `docs/plans/quality-audit/baseline/<tool>.txt`. Each tool gets a one-paragraph summary in `baseline/README.md`.

| Signal | Tool / command | Feeds track |
|---|---|---|
| Suppression inventory | `grep -rn 'noqa\|type: ignore\|pragma: no cover\|nosec'` grouped by code and file | B, C |
| Extended lint, report-only | `ruff check --select ALL --statistics` (counts by rule, compared with the configured set) | B, C |
| Cyclomatic complexity / maintainability index | `radon cc -s -a src`, `radon mi src`, `xenon --max-absolute B` (report only) | B |
| File / function size | functions > 50 lines, files > 400 / 800 lines (common/coding-style) | B |
| Python clones | `pylint --disable=all --enable=duplicate-code --min-similarity-lines=6 src` | A |
| Template / CSS / JS clones | `jscpd --min-lines 8 src/budget_planner/web/{templates,static}` | E |
| Dead code | `vulture src --min-confidence 60` plus a whitelist pass; unused templates (template names never referenced from `render`/`include`/`import`); unused CSS classes (stylelint plus a grep cross-check) | G |
| Import graph and cycles | `pydeps --show-cycles` or `import-linter` dry-run contracts (routers ↛ repositories, web ↛ db, domain ↛ services) | B |
| SQL locations | grep for `execute(`, `executemany(`, `text(`, literal `SELECT|INSERT|UPDATE|DELETE` outside `repositories/` and `db/migrate.py` | B |
| Clock call sites | grep for `datetime.now`, `date.today`, `utcnow`, `time.time` | C |
| Coverage by module | `pytest --cov --cov-report=term-missing`, sorted by module. Flag modules < 85% even though the global coverage is ≥ 90%. | F |
| Type holes | `mypy --strict --warn-unreachable` with `Any` reporting (`--any-exprs-report`) | C |
| Security scanners | `bandit -r src -ll`, `pip-audit`, `detect-secrets scan --all-files`, `semgrep --config p/python --config p/owasp-top-ten` (report only) | D |
| Infra lint | `tflint`, `checkov -d terraform` (report only) | D |
| Mutation testing | see §2.1 | F |

### 2.1 Mutation testing baseline (folds in the Mutmut plan)

This is the original Mutmut plan's Phase 0 (spike) and Phase 3 (first run plus triage), run as audit work. The plan's Phase 1 (docs) and Phase 2 (committed setup) move to Phase 4 of this audit as a prevention control. Its Phase 4 (nightly) becomes a Phase 4 decision.

**Spike (T-Q03a, about 1 h, nothing committed except the report)**
- Install `mutmut` v3 in the audit worktree only: `uv run --with mutmut`.
- Run it on `src/budget_planner/domain` with `tests/unit` and `--no-cov`. Check first that `-m unit` actually selects the unit tests: `unit` is declared as "default", but confirm with `pytest -m unit --collect-only -q` whether it is applied automatically.
- Record: mutant count, wall time, kill / survive / timeout counts, and any test breakage caused by the copied `mutants/` directory (absolute paths, fixtures).
- **Safety check:** confirm no fixture can resolve to `data/budget.sqlite` from the mutated copy.
- **Decision point:** if runtime is reasonable (domain under about 15 min) and the survivors look useful, run the baseline below. If not, evaluate Cosmic Ray once, or drop mutation testing and record why in `baseline/README.md`.

**Baseline run and triage (T-Q03b)**
- Scope: `domain` and `services` (repositories deferred; `web`, `db` and `cli` excluded).
- Record the baseline score per package in `baseline/mutmut.txt`.
- Sort the survivors into three groups:
  - **Real gap:** becomes a finding in the register, track F, root cause `weak-assertion`. Mitigation: write a test that kills the mutant (TDD: fails on the mutant, passes on the original).
  - **Equivalent mutant:** listed in `baseline/mutmut-equivalent.md` with a reason. Pragmas are added only at remediation time.
  - **Low value** (log or error message strings, `__repr__`): becomes a config exclusion proposal for Phase 4.
- Priority areas, where survivors are at least High severity: minor-unit amounts, the sign from `category.direction`, the reconciliation/adjustment path (signed amounts, ADR-0008), FX conversion and historical rate lookup, balance derivation, budget tier resolution, recurring occurrence generation.

| Risk | Mitigation |
|---|---|
| Slow runs (integration tests take about 3 min) | Unit tests only in the first scope; Mutmut caches results between runs |
| Too many equivalent-mutant false alarms | Equivalent list plus exclusions; track the score instead of gating on it |
| The `mutants/` copy breaks path-based fixtures | Found in the spike; the fix becomes a Phase 4 setup item |
| Effort creeps into chasing 100% | Target score set in the Phase 4 ADR (for example ≥ 80% on `domain`) |

---

## 3 · Phase 2 — Review tracks (T-Q04 … T-Q10)

Seven tracks run in parallel. They are read-only and dispatched with the `orchestrator-mode` skill (ADR-0066). Each track agent gets its own worktree and writes **only** `docs/plans/quality-audit/tracks/<track>.md`, so merges cannot conflict. Each track file contains:

1. **Coverage statement**: which files and modules were read, and which checklist items were applied. If something was skipped, the file says so.
2. **Findings** in the §4 schema, with track-local ids (`A-01`, `B-01` …).
3. **Questions**: suspicions without enough evidence, for Phase 3 to confirm or drop.

The agent brief for every track includes: this plan, CLAUDE.md, the ADRs listed for the track, the Phase 1 baseline reports, `AUDIT_SHA`, and the prod-DB rule.

### Track A — Duplicated domain logic (T-Q04) · highest priority

**Method: build a concept map.** For each domain concept, list every place that computes it, then diff the implementations against each other. Disagreements between them (rounding, rate date, sign, inclusive versus exclusive ranges, soft-delete filtering, user scoping) are the bugs.

| Concept | Canonical (expected) home | Where to hunt for copies |
|---|---|---|
| FX conversion and rate lookup (rate date, fallback on missing rate, rounding) | `services/fx.py`, `adapters/fx` | `services/budget.py`, `services/forecast.py`, `services/analytics.py`, `services/fortune.py`, `web/today_data.py`, `web/routers/ledger.py`, `web/charts.py` |
| Minor units: parse, format, currency exponent | `domain/money.py` | routers (`_parse_amount_arg` and similar), Jinja filters and macros, `charts.py`, export adapters |
| Signed amount from `category.direction` (transit, adjustment) | `domain` (ADR-0008) | services, SQL `CASE` expressions, templates |
| Account balance and fortune | `services/balance.py` / `fortune.py` | `ledger_totals.py`, `analytics.py`, `today.py`, repository SQL sums |
| Period and month ranges, "today", "left per day" | *none yet, a candidate* | `today.py`, `budget.py`, `income.py`, `upcoming.py`, `forecast.py`, `analytics.py` |
| Budget tier resolution (default / recurring / one-off) | `services/budget.py` | yearly grid, today, analytics |
| Recurring occurrence expansion, `next_due`, overrides | `services/recurring.py` | `forecast.py`, `upcoming.py`, `account_planned.py`, `recurring_formula.py`, `db/migrate.py` hook |
| Aggregates (mean, totals per category / month) | *none, a candidate* | `_mean_minor` appears in both `budget.py` and `analytics.py` |
| User scoping (`user_id` filters, ADR-0061) | `repositories/_shared.py` | every repository and any SQL outside it |
| Validation (amount > 0, direction allowed, cross-currency transit) | `services/_promotion.py` and others | routers, services |
| HTMX trigger names (`*-stale`) and swap targets | *none, a candidate* | routers (string literals), templates |

**Deliverables:**
- `tracks/A-duplication.md`, including the concept map as a table: concept → implementations (`path:line`) → behavioural differences → recommended canonical home.
- A list of **differential test candidates**: invariants that must hold across implementations, for example "budget spent for category C in month M equals the ledger total for C in M equals the analytics value for C in M, all in base currency". Each candidate that fails when run on the scratch DB becomes a Confirmed finding.

ADRs: 0006, 0008, 0021, 0038, 0045, 0095.

### Track B — Layering and architecture (T-Q05)

- **Thin web, fat services:** business logic in routers (branching on domain state, arithmetic, aggregation, DB calls). Start with the largest routers.
- **Repository discipline (ADR-0019, ADR-0022):** every mutation goes through repository helpers that set `deleted_at` and write `audit_log`. Every read filters soft-deleted rows. Check each SQL site outside `repositories/` from the Phase 1 grep.
- **Import cycles:** examine each `PLC0415` suppression. Is it a real cycle, a deliberate lazy import, or unnecessary?
- **Functional-first (ADR-0021):** stateful classes, module-level mutable state, mutation of inputs (`list.append` on parameters, dict updates on shared objects), frozen dataclasses that are not frozen.
- **Signatures:** each `PLR0917` suppression. Is there a risk of swapped arguments of the same type (several `int` ids or amounts in a row)? Mitigation: keyword-only arguments or a frozen params dataclass.
- **Size and complexity:** files over 800 lines, functions over 50 lines, nesting deeper than 4 (from the Phase 1 radon data).
- **Transactions:** compound mutations wrapped in a single `db_transaction`. Audit-free helpers (`set_next_due` and similar) only called from inside an audited orchestrator.

ADRs: 0019, 0021, 0022, 0061, 0066.

### Track C — Correctness risks (T-Q06)

- **Time (ADR-0007):** classify every clock call site as either (a) a UTC timestamp for the DB or (b) a "today" in the display timezone. Look for the midnight-UTC versus midnight-Warsaw window, `date.today()` on a UTC host, and tests that cannot freeze time. Expected mitigation: a single injected clock module.
- **Silent failures:** broad `except`, `except: pass`, fallback-to-zero or fallback-to-rate-1, `dict.get(..., 0)` on money, `or 0`, empty results when a lookup is missing. In money code these become wrong numbers rather than errors.
- **Arithmetic:** float leaking into money (`float(`, `/` on minor units without explicit rounding), rounding mode consistency (`ROUND_HALF_EVEN` versus `HALF_UP`), integer division of negative adjustments, currency exponent (T-JPY class).
- **Boundaries:** end-of-month clamp, Feb-29, inclusive/exclusive date ranges, empty months, first and last day of period, accounts with no transactions, closed or soft-deleted accounts or categories still referenced.
- **Concurrency:** SQLite write contention under the multi-user deployment, retention task versus requests, read-modify-write without a transaction.
- **Performance:** N+1 queries per page (count queries per route on the scratch DB with the demo data), unbounded queries, missing indexes for user-scoped filters.

ADRs: 0006, 0007, 0008, 0015, 0038.

### Track D — Security (T-Q07)

The security-reviewer agent handles this track, following CLAUDE.md, the web security rules and requirements §6.7.

- AuthN/AuthZ: every route behind `AuthRequiredMiddleware` unless it is on the explicit allowlist. Cross-user access, meaning an IDOR on every `/{id}` route: does it filter by `user_id`? The `tests/architecture/test_user_id_filter*.py` coverage is a starting point, not proof. Admin-only routes guarded (ADR-0073).
- Sessions and passkeys (ADR-0067): fixation, rotation on login and privilege change, logout invalidation, challenge reuse, rate limiting on `/auth/*`.
- CSRF on every state-changing request, including HTMX posts. CSP and security headers on every response. `Cache-Control: no-store` (ADR-0078).
- Input validation at the boundary: form parsing, `Decimal` parsing, date parsing, enum coercion; 422 versus 500 behaviour.
- XSS: `|safe`, `Markup`, autoescape off, `hx-vals` / `hx-on` containing user data, Plotly titles or labels built from user text.
- SQL injection: any string-built SQL, including dynamic `ORDER BY` / `IN (...)`.
- Secrets and logging: redaction coverage (ADR-0078), nothing secret in errors, `detect-secrets` baseline drift.
- Supply chain and infra: the `pip-audit` results, pinned versions, GitHub Actions pinned by SHA, Terraform and cloud-init (ufw, Tailscale, ADR-0094), and Litestream encryption.

ADRs: 0033, 0061, 0067, 0073, 0078, 0094.

### Track E — Frontend (T-Q08)

- **Logic in templates:** arithmetic, sign flips, currency formatting outside the `money` filter or `amount` macro, conditionals on domain state that belong in a view model.
- **Duplicate partials and macros:** near-identical forms, rows and slide-overs (from the jscpd output). The same widget implemented twice (combobox, numeric input, amount display).
- **Design tokens:** hex literals, ad-hoc spacing, duplicated CSS rules, dead CSS (ADR-0027 toolchain).
- **HTMX contracts:** trigger names emitted by routers versus listened to in templates, with a matrix of emitters and listeners. Swap targets that do not exist, and duplicate ids.
- **JS:** duplicated listeners, `htmx:afterSwap` re-wiring copies, globals.
- **Runtime confirmation:** where a static finding needs proof (overflow, duplicate ids, console errors), run the `frontend-visual-audit` skill on the scratch DB at 1440 / 1024 / 375 and cite the result.

ADRs: 0027, 0030, 0031.

### Track F — Tests (T-Q09)

- The mutation-testing survivors from §2.1 (the main input for this track).
- **Over-mocking:** tests that patch the unit under test, or mock a collaborator so thoroughly that the assertion is meaningless.
- **Missing cross-implementation tests:** the Track A differential candidates that have no test.
- **Weak assertions:** `assert result` / `is not None` on money values, status-code-only HTTP tests, snapshot tests nobody reviews.
- **Fixture duplication** across `conftest.py` files. Test helpers that re-implement production logic, which would also hide divergence.
- **Flakiness:** sleeps, time-dependent tests without a frozen clock, order dependence (one run with `pytest -p randomly`).
- **Gaps:** modules under 85% coverage from Phase 1, untested error branches in money paths, and E2E coverage of the critical flows (add transaction, reconcile, promote recurring, set budget, login/passkey).
- **Prod-DB safety:** grep tests, fixtures and scripts for any path that can resolve to `data/budget.sqlite`.

### Track G — Dead code and doc drift (T-Q10)

- **Dead code:** vulture survivors after manual check, unused routes, templates, macros, CSS, JS, migrations helpers, and leftover v1/v2 shims or re-exports (for example the compatibility re-exports in `services/planned`).
- **Doc drift:** for each ADR that is still Accepted, check that the code still behaves as it says, and flag ADRs that should be marked superseded. Also: CHANGELOG versus `tasks.md` ✅ status; `requirements.md` versus implemented behaviour; `CLAUDE.md` commands versus the `justfile` (for example the documented `just dev --db=` flag). ADR number collisions (the original Mutmut plan named ADR-0095, which is already taken).
- **Config drift:** pre-commit hooks versus `just ci` versus GitHub Actions. Are the same checks run with the same versions?

---

## 4 · Finding schema

Every finding in the track files and in `findings.md` uses this record. The register table in `findings.md` holds the first seven columns. The full record goes in a detail section below the table.

| Field | Content |
|---|---|
| **ID** | `Q-###` (assigned in Phase 3; track-local ids kept as an alias) |
| **Title** | One line stating the defect, not the fix |
| **Severity** | Critical / High / Medium / Low (§5) |
| **Confidence** | Confirmed (reproduced, or proven by a failing test or script) / Probable (precise code citation, no repro) |
| **Track / root cause** | Track letter and root-cause class (§5.2) |
| **Location(s)** | `path:line` at `AUDIT_SHA`, every occurrence (for duplication: every copy) |
| **Description** | What is wrong and why, referencing the violated ADR or rule |
| **Evidence** | Repro steps, test name, command and output, or diff of the divergent implementations |
| **Impact** | What the user or operator would see: a wrong number, a leak, a crash, slower change |
| **Mitigation** | The **single best** fix, concrete enough to become a task: target module and function, approach |
| **Alternatives** | Only if the choice is genuinely open, with a one-line trade-off each |
| **Effort** | S (< ½ day) / M (≤ 2 days) / L (> 2 days) |
| **Related** | ADRs, tasks, other finding ids (duplicates / same root cause) |

---

## 5 · Severity rubric and root-cause classes

### 5.1 Severity

| Level | Definition for this app | Examples |
|---|---|---|
| **Critical** | Wrong money shown or persisted today; data loss or corruption; cross-user data exposure; auth bypass; prod DB reachable from tooling | Budget total disagrees with ledger total for real data; IDOR on `/transactions/{id}`; soft-delete bypass that resurrects deleted rows in totals |
| **High** | A latent wrong-number risk (divergent duplicate implementations that agree only by coincidence); a security weakness without a known exploit path; audit-log or soft-delete bypass on a path not yet exercised; a surviving mutant in a priority money area | Two FX converters with different missing-rate fallbacks; a missing CSRF check on an idempotent-looking POST |
| **Medium** | A maintainability problem with a plausible future bug path | Router with business logic; import cycle; long positional signature; 30-line logic block in a template |
| **Low** | Style, naming, minor dead code, cosmetic doc drift | Unused helper; stale ADR link |

A **Critical** finding found during the audit is reported to the operator immediately and does not wait for Phase 3. If it is a security issue, follow the common/security.md response protocol.

### 5.2 Root-cause classes (used by Phase 4)

`duplicate-logic` · `layer-leak` · `repo-bypass` · `scoping-gap` · `clock` · `silent-fallback` · `money-arith` · `weak-assertion` · `missing-invariant-test` · `import-cycle` · `wide-signature` · `oversized-module` · `template-logic` · `htmx-contract` · `dead-code` · `doc-drift` · `config-drift` · `security-control` · `dependency`

New classes may be added in Phase 3 if they are documented in `findings.md`.

---

## 6 · Phase 3 — Verify and consolidate (T-Q11, T-Q12)

1. **Merge tracks:** gather all track findings into `findings.md`.
2. **Adversarial verification (T-Q11):** an independent agent re-checks each Critical and High finding (and a sample of at least 20% of Mediums) *without* seeing the original reasoning, only the claim and the locations. The verdict is Confirmed, Probable or Rejected. Rejected findings move to a "Dismissed" appendix with the reason. Where it is cheap, Confirmed means a repro test on the scratch DB, committed under `docs/plans/quality-audit/repro/` and not in `tests/` (it moves into `tests/` during remediation).
3. **Dedupe:** merge findings that share a root cause and location. For duplication, one finding per concept, listing every copy.
4. **Calibrate:** one pass over all severities against §5.1 so every track uses the same scale.
5. **Mitigation pass:** check that each mitigation is a single concrete fix, that it fits the existing ADRs (or names the ADR it would need), and that mitigations of related findings do not conflict. For example, each FX finding should point to the same canonical converter.
6. **Summary** at the top of `findings.md`: counts by severity × track, top 10 by risk, and the root-cause histogram.
7. **Operator review (T-Q12):** the operator walks through the Critical and High findings and accepts, adjusts severity, or dismisses. `findings.md` is then frozen as **Deliverable 1**.

---

## 7 · Phase 4 — Prevention (T-Q13 … T-Q16) · sequential, starts only after Phase 3 is frozen

**Goal:** for every root-cause class with at least one Critical or High finding (and `duplicate-logic` in any case), make sure the class cannot easily come back. The question is "why did agents and the human write this, and why did review not catch it?"

### 7.1 Audit the guidance surface (T-Q13)

Review each artefact against the root-cause classes and record the gaps in `prevention.md`:

| Artefact | What to check |
|---|---|
| `CLAUDE.md` | Does it state the rule (canonical modules, clock, SQL only in repositories, no logic in routers or templates)? Is the rule findable at the point of action, or buried? Are there contradictions or stale commands? |
| `.claude/skills/orchestrator-mode/SKILL.md` | Does the subagent brief force a *search-before-write* step ("find the existing implementation of X before adding one")? Does it list canonical modules? Does the merge step include a duplication check? Parallel items are the main source of duplicates. |
| `.claude/skills/frontend-visual-audit/SKILL.md` | Does it cover the HTMX contract and template-logic checks, or only layout? |
| `docs/requirements.md` §3.3 Code Style | Does it mention DRY, canonical modules, the clock and the layering rules? |
| ADR-0021 / 0022 / 0007 / 0006 | Do they state enforcement mechanisms, or only intent? Do any need amending or superseding? |
| `docs/plans/*/implementation_plan.md` handoff rules | Does the handoff checklist ask "did you reuse the existing helper?" |
| `pyproject.toml` (ruff, mypy, coverage), `.pre-commit-config.yaml`, `justfile`, CI workflows | Which classes could be caught automatically but are not? Which suppressions are too easy to add? |
| `tests/architecture/` | Which invariants are already enforced (user-id filter, Terraform inputs)? Which are missing? |
| User-level rules in `~/.claude/rules/` | Out of the repo's control. Note conflicts only (for example, the generic rules recommending agent types this repo does not use). |

### 7.2 Design controls (T-Q14)

For each class, choose the **strongest feasible** control, in this order: automated guard > structural (a canonical module plus a deprecation of the copies) > written rule in the brief or skill > written rule in CLAUDE.md. Each control is recorded in a **prevention matrix** in `prevention.md`: class → findings → control(s) → artefact(s) changed → how it is verified.

Expected controls, to be confirmed against the actual findings:

- **`duplicate-logic`:**
  - a "Canonical modules" table in CLAUDE.md (concept → module → function), maintained as part of the handoff checklist;
  - a mandatory search-before-write step in the orchestrator brief;
  - differential invariant tests under `tests/architecture/` or `tests/integration/invariants/`;
  - optionally, a `pylint duplicate-code` check in `just lint` (report-only at first).
- **`layer-leak` / `repo-bypass`:**
  - `import-linter` contracts in pre-commit (routers ↛ repositories, web ↛ `db.connection` SQL, domain ↛ services);
  - an architecture test that fails on SQL keywords outside `repositories/` and `db/migrate.py`.
- **`clock`:**
  - a single `budget_planner.clock` module (`utc_now()`, `today_local()`);
  - ruff `flake8-tidy-imports` banned-api, or `DTZ` rules without per-line suppressions, so direct `date.today()` and `datetime.now()` are rejected outside that module.
- **`wide-signature` / `import-cycle`:** remove the bulk suppressions; new `noqa` for these codes requires a reason comment (an architecture test can check that each `noqa` carries a `-- reason`).
- **`weak-assertion` / `missing-invariant-test`:** commit the Mutmut setup. This is Phase 1 and Phase 2 of the original Mutmut plan:
  - an ADR (next free number, **not** 0095, which is taken) covering:
    - why Mutmut over Cosmic Ray and pytest-gremlins;
    - scope: `domain` and `services`;
    - not a gate: run manually or nightly, with a score to track;
    - how equivalent mutants are handled;
    - a target score;
  - `docs/requirements.md` §3 tooling list;
  - `uv add --dev mutmut`;
  - a `[tool.mutmut]` section in `pyproject.toml`: `paths_to_mutate`, pytest args `-m unit --no-cov -p no:cacheprovider`, exclusions;
  - `just mutate` / `mutate-report` / `mutate-clean`;
  - `.gitignore` entries for `mutants/` and the cache;
  - fixes for path-dependent fixtures found in the spike.
  - Nightly GitHub Actions job (fails only if the score drops more than X points below baseline): decide here, adopt if the spike runtime allows. Extending to `repositories` with integration tests: deferred.
- **`template-logic` / `htmx-contract`:** a test that parses templates and routers, builds the emitter/listener matrix, and fails on orphans; the visual-audit skill gains a template-logic checklist.
- **`doc-drift`:** the handoff checklist step "ADRs touched by this change re-read and still true"; an ADR-number collision check (an architecture test asserts unique ADR numbers).

### 7.3 Apply (T-Q15)

- Docs-first: one ADR for the prevention regime (canonical modules, clock, import contracts, and the mutation-testing policy, unless that gets its own ADR), then the requirements §3.3 update, then the CLAUDE.md, skill and brief edits.
- Automated guards land in **report-only or allowlist mode**. Each one starts with an allowlist that exactly matches the current findings, so CI stays green. Remediation tasks shrink the allowlist to zero, and new violations fail immediately.
- Edits to `CLAUDE.md` and `.claude/skills/**` are reviewed by the operator before merge, because they change how every future agent works.

### 7.4 Verify (T-Q16)

- **Dry run:** give a fresh agent a small synthetic task that would previously have produced a duplicate, for example "show spent-in-base-currency on a new widget". Check that it finds and uses the canonical module, and that the guards trip if it does not. Record the result in `prevention.md`.
- `just ci` is green with the guards in place.

**Deliverable 2** = `prevention.md` (gap analysis, prevention matrix, dry-run result) plus the merged doc, skill and config edits.

---

## 8 · Phase 5 — Remediation backlog (T-Q17)

- Each accepted finding, or each cluster of findings with the same root cause and the same fix, becomes a task `T-Q2xx` in `tasks.md`, linking the finding ids, ADR(s) and acceptance criteria. Critical and High findings get their own task; Mediums and Lows may be batched per module.
- Order: Critical → High money and security → guards' allowlist burn-down → Medium → Low.
- Each task must state the allowlist entries it removes (§7.3), so progress shows up in CI.
- Execution happens later: one task at a time or in orchestrator mode, following the normal handoff checklist. Remediation is not part of this audit.

---

## 9 · Sequencing vs v4 (decided)

v4 Phase 3 sweeps every repository for field encryption and moves aggregates into Python (ADR-0081). Each duplicated aggregate or conversion path would be ported separately, which multiplies the T-FIX6 class of bug inside code that is harder to inspect (encrypted columns).

**Decision (operator, 2026-11-06): the audit runs after v3 ships and before v4 starts.**

- **The whole audit (T-Q01…T-Q17) is a v4 Phase 0 precondition.** It is a T-E00 gate item in `docs/plans/v4/`.
- **Critical and High remediation** of the `duplicate-logic`, `repo-bypass` and `scoping-gap` classes must also be ✅ before v4 Phase 3 (field encryption) starts.
- **Other remediation** can run alongside v4 Phases 1–2, or after v4.

---

## 10 · Execution model and budget

- Phase 1: one agent (tools), plus one agent for the Mutmut spike and baseline.
- Phase 2: seven track agents in parallel (orchestrator mode, one worktree each, each writing only its track file).
- Phase 3: one or two verification agents plus the orchestrator consolidating.
- Phase 4: sequential. One agent for gap analysis and design, then subagents per artefact edit.
- Expected wall-clock time: Phase 1 about ½ day, Phase 2 about 1 day, Phase 3 about ½–1 day plus the operator review, Phase 4 about 1–2 days.

## 11 · Guardrails

- No edits to `src/`, `tests/`, config or CI on the audit branch during Phases 1–3. Track agents that find themselves "just fixing" something must stop and record a finding instead.
- No `data/budget.sqlite` access of any kind. A tool that defaults to it (`just migrate`, `just seed`, the CSV import) is never run without `--db=<scratch>`.
- No dependency changes committed during Phases 1–3. Tools run through `uv run --with`.
- Worktree hygiene: prune each track worktree and branch as soon as it is merged into `audit/quality`.
- Before every merge into the shared branch, check `MERGE_HEAD` and the branch tip, because other sessions merge too.
