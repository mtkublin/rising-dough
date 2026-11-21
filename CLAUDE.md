# Budget Planner — Claude Guide

Local-first personal budget planning and fortune tracking web app. Single user, multi-account, multi-currency.

## Change policy — docs come first (MANDATORY)

**Any change to this project must go through the documentation first.** No exceptions.

Before touching code (or docs that drive code):

1. **Requirement change** → update `docs/requirements.md` first. If scope-affecting, also update the active plan's `docs/plans/<plan>/tasks.md` and `implementation_plan.md`.
2. **Architectural / design decision** → write a new ADR under `docs/adr/` (next sequential number), update `docs/adr/README.md`, and reference it from the affected requirement or task. Supersede, don't delete, prior ADRs.
3. **New task or re-scoped task** → edit `docs/plans/<plan>/tasks.md` first; link to the ADR(s) it depends on.
4. **Stack / tooling change** → ADR first, then `docs/requirements.md` section 3, then code.
5. **Scope creep into Phase 6 / v2 items** → requires an ADR explicitly flipping it into v1.

Only after the relevant docs are updated and committed (or staged in the same PR) may the code change land. A code change without a matching doc update is treated as incomplete.

## Where to look

| Need | Path |
|------|------|
| Full requirements | `docs/requirements.md` |
| Task breakdown | `docs/plans/<plan>/tasks.md` |
| Phased implementation plan + handoff rules | `docs/plans/<plan>/implementation_plan.md` |
| Prevention regime (guards, allowlists, zero-violation policy) | [ADR-0130](docs/adr/0130-prevention-regime-and-full-architectural-compliance.md), `docs/requirements.md` §3.3 |
| Decisions (and *why*) | `docs/adr/README.md` |

Always read the relevant ADR before changing an area it covers.

## Stack

- Python 3.12, FastAPI, Jinja2, HTMX, Tailwind (local build, `just css`), server-rendered SVG charts (no CDN, no Plotly, no SPA framework: ADR-0123).
- SQLite only in v1 (DuckDB deferred).
- `uv` for deps, `just` for recipes.
- Pre-commit: `ruff`, `ruff-format`, `mypy --strict`, `import-linter`, `pytest` (testmon-selected), `sqlfluff`, `djlint`, `stylelint`, `bandit`, `detect-secrets`. CI runs the same hooks (`SKIP=pytest-fast`) plus the full suite (ADR-0130 §8).

## Canonical modules (reuse, never re-implement)

One module owns each concept. **Before you write a helper:** (1) find the concept below; (2) run the row's search terms over `src/` (`rg -n "def .*(convert|month|period|today|sign|parse)"` style); (3) call or extend the owner. Report `Searched: <queries>; Reused: <symbols>; New helper: <name> (why none fits; registered: yes/no)`. A new shared concept is registered in `tests/architecture/canonical_modules.toml` (this table must cover every row; `test_canonical_modules.py` checks it) in the same change.

| Concept | Owner | Status | Interim (target rows) |
|---|---|---|---|
| FX conversion and rate lookup | `services/fx.py` `converter_for` -> `FxConverter.to_base` (cache-only, ADR-0139) | exists | - |
| Money format, parse, exponent, minor and major units | `domain/money.py` (`parse_amount_str`, `format_money`, `to_minor_units`, `minor_to_major`); one rounding helper (T-Q229) | exists (Q-011, T-Q216) | - |
| Periods and month windows | `domain/periods.py` `month_bounds` | exists (Q-003) | - |
| Recurring occurrence expansion | `services/recurring.pending_occurrences` | **target** (Q-002) | `services/recurring.generate_occurrences` |
| Direction to sign | `domain/transactions.signed_legs` (`services/balance.py` today) | **target** (Q-036) | `services/ledger_totals.signed_effect` |
| Net worth and fortune | `services/fortune.compute_fortune` | exists (Q-009) | - |
| Sum by category in base currency | `services/aggregates.sum_by_category` | **target** (Q-008) | none - extract via T-Q227 |
| Ledger, recurring and planned totals | `services/ledger_totals.py` `day_nets` | exists-migrating (T-Q209) | - |
| Clock (UTC now, local today) | `budget_planner.clock`: `utc_now()`, `today_local(settings)`, `utc_now_iso()`; routers use `web.deps.get_today` / `today_for(request)` (ADR-0140) | exists (Q-031) | - |
| Request parameter parsing | `web/params.py` `parse_date`, `parse_int` | **target** (Q-023) | none - extract via T-Q233 |
| HTMX events and toast payloads | `web/htmx.py` `trigger` | exists-migrating (T-Q236) | - |
| Transit validation | `services/transactions.validate_transit_shape` | exists (Q-004) | - |
| Balance as of a date | `services/balance.as_of_today` | **target** (Q-032) | none - extract via T-Q227 |
| Category selection (expense category ids) | `services/categories.expense_category_ids` | **target** (Q-030) | none - extract via T-Q227 |
| Budget tier resolution | `services/budget.pick_tier` | **target** (Q-075) | `services/budget.resolve_budget` |
| Template view-model values (left per day, percentages) | `web/view_models.py` `left_per_day` | **target** (Q-039) | none - extract via T-Q237 |

**Target** rows are not yet extracted. Either call the row's **Interim** copy (public, named in the table), or, when it says "none", do the extraction as the registered migration task (`migration_task` in the registry), migrating **all** copies in the same change. Never import another module's private `_name` (G30, `test_private_imports.py`). Never create the canonical module without migrating the copies: a row may be `exists` only at zero copies, otherwise `exists-migrating` (`test_canonical_modules.py`). `allowlists/banned_patterns.toml` (G6) bans copies of a row's banned names outside its module.

## Code conventions

Rules are enforced by `tests/architecture/` and lint; a failing guard names the rule and the canonical module. Guard ids (`G<n>`): `docs/plans/quality-audit/prevention.md` §2. Run `just guards` before committing. Full text: [ADR-0130](docs/adr/0130-prevention-regime-and-full-architectural-compliance.md), `docs/requirements.md` §3.3.

| Rule | Enforced by |
|---|---|
| **Pure layers.** `domain/` and pure services do no I/O, read no clock/env/randomness, hold no global mutable state, mutate no argument. Services may call repositories and `logging`; network only through an injected port; clock and settings come in as arguments. Web view-models do no network. Effects live at the edges (repositories, `clock`, adapters, routers). | `test_purity.py` + `allowlists/purity.toml` (G22), import-linter `[tool.importlinter]` (ADR-0021, ADR-0130 §5) |
| **Thin web.** Routers parse, call one service, return a view model. No SQL, no repository import, no arithmetic on money/dates in routers or templates. | import-linter, `test_thin_router.py` + `thin_router.toml`, `test_template_logic.py` + `template_logic.toml` (G9) |
| **Repository-only SQL**, user-scoped (never a literal user id), soft delete + audit via repository helpers; a service calling 2+ mutators uses one `db_transaction`. | `test_no_sql_outside_repositories.py` + `sql_sites.toml` (G2), `test_user_id_filter.py`, `test_literal_user_id.py` + `literal_user_id.toml` (G7b); one-transaction rule G8 not yet a guard (ADR-0019, ADR-0022) |
| **Single clock.** `budget_planner.clock` only; never `date.today()`, `datetime.now()`, `datetime.utcnow()`, `time.time()`. | ruff TID251 banned-api in `pyproject.toml` (only `clock.py`, scripts and tests exempt, G3) (ADR-0007, ADR-0140) |
| **Money.** Positive integer minor units, direction from `category.direction` (reconciliation is the only signed exception). Format/parse/round only via `domain.money`; no `/ 100`, `* 100`, `float`, `Decimal("100")` on money. Convert only via the FX owner; account owns currency, aggregates use `base_currency` (PLN) with cached historical rates. | `test_banned_patterns.py` + `banned_patterns.toml` (G6), `test_money_scope.py` + `money_scope.toml` (G27) (ADR-0006, ADR-0008) |
| **Immutable by default.** Frozen dataclasses, no classes beyond DTOs/Protocols, no module-level mutable state. | `test_functional_first.py` + `functional_first.toml` (G20), `test_purity.py` (ADR-0021) |
| **Suppressions.** Every `noqa` / `type: ignore` / `nosec` / `pragma: no cover` carries a reason on the same line. | ruff `PGH`, `test_suppressions.py` + `suppressions.toml` (G4) |
| **Allowlists only shrink.** `tests/architecture/allowlists/*.toml` and `per-file-ignores` are the debt inventory. No new entry (or suppression) without an ADR-0130 amendment naming it and the reason. Fixed a violation: delete its entry in the same commit. | `tests/architecture/_ratchet.py` (fails in both directions) |
| **Tests assert values.** Exact amounts, the audit row and stored sign, and that a second user's rows are absent; HTTP tests assert body or DB state, not only status. | review, mutation score (ADR-0131) |

Timestamps are UTC in the DB, transaction dates are naive `DATE`, display timezone defaults to `Europe/Warsaw` (ADR-0007).

## Developer commands

```sh
just install      # uv sync + install pre-commit hooks
just dev          # run FastAPI with hot reload on 127.0.0.1:8000
just test         # pytest with coverage, xdist (PYTEST_WORKERS, default auto); fails under 90%
just lint         # ruff + sqlfluff + djlint
just format       # ruff format + ruff --fix
just typecheck    # mypy --strict
just ci           # everything CI runs (full suite + coverage; optional locally, PR CI runs it)
just lint-changed main   # pre-commit over files changed since merge-base (inner loop)
just test-changed main   # testmon-selected tests; full suite on non-Python changes (inner loop)
just worktree-init       # seed a new worktree's .testmondata from the main checkout
just test-fast    # testmon-selected tests (what the pre-commit hook runs)
just guards       # tests/architecture/ + import-linter only (fast, run before every commit)
just mutate       # Mutmut on domain + services (slow, background; ADR-0131); mutate-report, mutate-clean
just demo-build   # rebuild data/demo.sqlite from prod (read-only on prod)
just set-password # set a user's password on an explicit --db=<path> (no default DB)
just dev-demo     # run the app on the anonymized data/demo.sqlite
just db-reset     # recreate the dev DB
just migrate      # apply pending migrations
just seed         # seed default categories + demo accounts
```

The pre-commit hooks are the local gate and `*-changed` run the same selection on demand; the full gate is PR CI (ADR-0120). `PYTEST_WORKERS=2` for parallel orchestrator item agents; `0` runs serially.

## Multi-agent work

For work split across parallel subagents, use the `orchestrator-mode` skill (`.claude/skills/orchestrator-mode/SKILL.md`, ADR-0066): main agent orchestrates only, each work item runs in its own worktree + branch, conflicts are resolved by merging the main work branch into the item branch (no rebase).

## Frontend validation (MANDATORY)

Any change that touches templates (`src/budget_planner/web/templates/**`), CSS (`src/budget_planner/web/static/*.css`), responsive breakpoints, or HTMX swap targets **must** be verified with the `frontend-visual-audit` skill before the task is marked done.

- Skill location: `.claude/skills/frontend-visual-audit/SKILL.md`.
- Primary tool for all frontend validation. Do **not** rely on reading templates + CSS alone to confirm layout, overflow, responsive behavior, or HTMX render correctness.
- Minimum sweep: run against the routes affected by the change at desktop (1440) + tablet (1024) + mobile (375) viewports.
- Treat non-zero `horizontalScroll`, `overflowingElements`, `duplicateIds`, `consoleErrors`, or `requestFailures` as blocking signals.
- Also run Step 3b (behaviour contract and template logic): no arithmetic/`float` in templates, rendered numbers equal the service value, every failing save shows a visible error.
- Reference the audit result (routes checked + findings summary) in the handoff / PR description, and commit it as `docs/audits/<date>-<slug>.md` (skill Step 6; guard G31 `test_frontend_audit_record.py` fails a templates/CSS change without it).

Agents working on frontend tasks must invoke this skill rather than inferring visual correctness from code.

The toolchain the skill validates against (local Tailwind build, `stylelint`, Jinja partials, Playwright visual regression) is defined in [ADR-0027](docs/adr/0027-frontend-toolchain-hardening.md).

## Releases & environments (MANDATORY)

Policy: [ADR-0099](docs/adr/0099-release-and-environment-policy.md).

- Prod is released **only** by GitHub Actions from `main` (ci, build, terraform apply prod with approval, deploy prod, smoke). Never run `terraform apply`/`destroy` against prod, and never build or push images for prod from a laptop or another branch.
- Drill deploys go through the drill pipeline, `workflow_dispatch` only (no push/PR trigger): `mode=gate` (default; the PR merge gate, posts the `drill-gate` commit status, always torn down) or `mode=explore` (`ttl_minutes`, default 60). Every PR to `main` needs a passing `drill-gate` on its head SHA (ADR-0099, T-D98; auto-satisfied for non-deploy PRs, ADR-0121). Agent-driven local drill work only with explicit user go.
- All drill workflows share the `drill` concurrency group (queued, not cancelled).
- Allowed non-GitHub exceptions: bootstrap stack (`terraform/bootstrap`, ADR-0096), logged break-glass runbook, one-time prod DB seed (explicit in-session user go).
- Enforcement is by credentials: prod-write keys live only in the GitHub `prod` environment (ADR-0100); keep none in `terraform/.env`.
- GitHub environment, branch-policy and secret settings are checked repo-side by `tests/architecture/test_workflow_secrets.py` (declared in `ci_environments.toml`) and by the operator-run `scripts/check_github_settings.py` (G17b). Never widen an environment's branch policy or add a secret to an environment without a `ci_environments.toml` entry and an operator go.
- Releases are one approved `terraform apply` that sets the image ref in instance metadata; the host agent converges ([ADR-0111](docs/adr/0111-terraform-declared-host-state.md)). There is no SSH deploy path; do not add one.

## Rules & scope

- **Scope guard**: `docs/requirements.md` section 3.8 lists what is **out of scope** for v1. Do not add v2 features without first writing a new ADR and updating `docs/requirements.md`.
- **Server binds to `127.0.0.1` only** in v1. No LAN or public exposure.
- **No secrets committed.** `detect-secrets` is in the pre-commit stack.
- **Timestamps are UTC in DB**, dates on transactions are naive `DATE`, display timezone defaults to `Europe/Warsaw`. See ADR-0007.
- **`data/budget.sqlite` = prod. Hands off.** No agent writes, migrations, resets, seeds, or ad-hoc SQL against it without explicit in-session user confirmation. For any DB experiment use `just dev --db=<path>` with a scratch file (e.g. `/tmp/scratch.sqlite`) or `just dev-demo`. See the "Databases" section below.

## Databases

### `data/budget.sqlite` is production — HANDS OFF (MANDATORY)

`data/budget.sqlite` holds the only canonical user data. Treat it exactly like a production DB — the same way you would treat a live customer database at a job.

- **No agent — human-driven or autonomous — may drop, truncate, migrate, reset, seed, re-import, schema-alter, or hand-edit `data/budget.sqlite` without explicit, in-session user confirmation.** This covers "harmless" fixes, "quick" cleanups, inserting test rows, column renames, ad-hoc SQL, and anything that opens the file in write mode. Ask first, every time. A prior approval does not carry over to a new task.
- **Never target it from tests, reproductions, scratch work, or exploratory debugging.** If you need a DB to try something out, spin up a disposable one and point the app at it via `--db=<path>`:

  ```sh
  just dev --db=/tmp/scratch.sqlite        # throwaway for ad-hoc work / repros
  just dev --db=data/demo.sqlite           # anonymized demo (safe to abuse)
  just dev-demo                            # same, shorthand
  ```

  The pytest suite already uses isolated temp DBs — do not bypass that by hard-coding `data/budget.sqlite` anywhere in test code, fixtures, or scripts.
- Commands that default to the prod DB and are therefore **destructive-by-default**: `just db-reset`, `just migrate`, `just seed`, and the CSV import script. Never run them against the default path from inside a task unless the user has explicitly said "run it against prod" in the current session. When in doubt, pass `--db=<path>` to a scratch file.
- The `--db=<path>` flag on `just dev` sets `BUDGET_DATABASE_URL=sqlite:///<path>`; app code is unchanged. Use it as the standard escape hatch for any DB experiment.
- The demo anonymizer (`just demo-build`, script `build_demo_db.py` under data/scripts) only runs when the source basename ends with `budget.sqlite` as a tripwire against accidental swaps — do not weaken or remove that check.

### Files at a glance

| File | Role | Policy | - |
|------|------|--------|
| `data/budget.sqlite` | **Prod** (local, canonical user data). Gitignored. | **Hands off.** See rule above. No writes without explicit user confirmation in the current session. | - |
| `data/demo.sqlite` | Demo DB — anonymized, scaled copy of prod for feature walkthroughs. Tracked in git. | Rebuild with `just demo-build` (reads prod, writes demo; prod is untouched). Safe to nuke and regenerate. | - |
| `/tmp/*.sqlite` or any path via `--db=` | Scratch / testing. | Default target for any agent-driven DB experiment. Create, abuse, delete freely. | - |

## Handoff checklist (for subsequent agents)

Before marking a task done:

1. **Docs updated first** (see "Change policy" above). `docs/requirements.md`, the active plan's `tasks.md`, and/or a new ADR reflect the change *before* code lands. ADRs the change touches are re-read and still true (status or amendment updated).
2. **Reuse check.** Searched the Canonical modules table and the tree before writing a helper; reused the canonical function, or registered the new one in `canonical_modules.toml` (why none fit is in the report).
3. Code + tests committed with the pre-commit hooks green: they lint, type-check and run the tests affected by the change across the whole suite (the full suite for migrations, SQL, dependencies, `conftest.py` and other non-Python changes). No local full `just ci` is required, single-agent or orchestrator; the full suite with the 90% coverage gate runs in PR CI and the gate drill's `ci / just ci` job ([ADR-0120](docs/adr/0120-pre-commit-is-the-local-gate.md)). Before opening or updating a PR whose changes touched e2e-relevant code, run `uv run pytest tests/e2e -q --no-cov` locally (GitHub runners have no Playwright browser; [ADR-0097](docs/adr/0097-per-batch-ci-policy-and-fast-precommit-pytest.md) amendment 2026-11-18). **No writes to `data/budget.sqlite`** during the task (prod DB — see "Databases"); any DB work ran against `--db=<scratch path>` or `data/demo.sqlite`.
4. **Architecture guards green; allowlist counts only went down.** Entries for violations you fixed are deleted; no new allowlist entry or suppression without a reason and an ADR-0130 amendment; any new dependency is justified in the commit.
5. **Frontend-touching tasks**: `frontend-visual-audit` skill run against the affected routes at desktop/tablet/mobile viewports; findings resolved or triaged (see "Frontend validation" above).
6. The task line in `docs/plans/<plan>/tasks.md` prefixed with `✅`.
7. Relevant ADR(s) referenced in the commit; a new ADR added if the task introduced an architectural decision not already recorded.
8. Append a dated line to `docs/CHANGELOG.md` (create on first use).
9. Conventional-commits message referencing the task id: e.g. `feat(T-021): derive account balance`.
