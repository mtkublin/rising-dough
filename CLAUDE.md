# Budget Planner — Claude Guide

Local-first personal budget planning and fortune tracking web app. Single user, multi-account, multi-currency.

## Change policy — docs come first (MANDATORY)

**Any change to this project must go through the documentation first.** No exceptions.

Before touching code (or docs that drive code):

1. **Requirement change** → update `docs/requirements.md` first. If scope-affecting, also update `docs/tasks.md` and `docs/implementation_plan.md`.
2. **Architectural / design decision** → write a new ADR under `docs/adr/` (next sequential number), update `docs/adr/README.md`, and reference it from the affected requirement or task. Supersede, don't delete, prior ADRs.
3. **New task or re-scoped task** → edit `docs/tasks.md` first; link to the ADR(s) it depends on.
4. **Stack / tooling change** → ADR first, then `docs/requirements.md` section 3, then code.
5. **Scope creep into Phase 6 / v2 items** → requires an ADR explicitly flipping it into v1.

Only after the relevant docs are updated and committed (or staged in the same PR) may the code change land. A code change without a matching doc update is treated as incomplete.

## Where to look

| Need | Path |
|------|------|
| Full requirements | `docs/requirements.md` |
| Task breakdown | `docs/tasks.md` |
| Phased implementation plan + handoff rules | `docs/implementation_plan.md` |
| Decisions (and *why*) | `docs/adr/README.md` |

Always read the relevant ADR before changing an area it covers.

## Stack

- Python 3.12, FastAPI, Jinja2, HTMX, Tailwind (CDN), Plotly.
- SQLite only in v1 (DuckDB deferred).
- `uv` for deps, `just` for recipes.
- Pre-commit: `ruff`, `ruff-format`, `mypy --strict`, `pytest`, `sqlfluff`, `djlint`, `bandit`, `detect-secrets`.

## Code conventions

- **Functional-first.** Modules of pure functions. Dataclasses `frozen=True` for data; no classes beyond that unless they are DTOs or Protocols. See ADR-0021.
- **Thin web, fat services.** Routers call services; services call repositories; repositories call SQL. No business logic in routers.
- **Soft delete + audit log** for every mutable table. Use the repository helpers; never bypass them. See ADR-0019.
- **Amounts** stored as positive integer minor units; direction derived from `category.direction`. Reconciliation (direction=`adjustment`) is the only signed-amount exception. See ADR-0008.
- **Multi-currency**: account owns currency, transactions inherit. Aggregates convert to `base_currency` (default PLN) using historical FX rates cached locally. See ADR-0006.
- **Immutable by default.** Build new values; do not mutate.

## Developer commands

```sh
just install      # uv sync + install pre-commit hooks
just dev          # run FastAPI with hot reload on 127.0.0.1:8000
just test         # pytest with coverage; fails under 90%
just lint         # ruff + sqlfluff + djlint
just format       # ruff format + ruff --fix
just typecheck    # mypy --strict
just ci           # everything CI runs
just db-reset     # recreate the dev DB
just migrate      # apply pending migrations
just seed         # seed default categories + demo accounts
```

## Frontend validation (MANDATORY)

Any change that touches templates (`src/budget_planner/web/templates/**`), CSS (`src/budget_planner/web/static/*.css`), responsive breakpoints, or HTMX swap targets **must** be verified with the `frontend-visual-audit` skill before the task is marked done.

- Skill location: `.claude/skills/frontend-visual-audit/SKILL.md`.
- Primary tool for all frontend validation. Do **not** rely on reading templates + CSS alone to confirm layout, overflow, responsive behavior, or HTMX render correctness.
- Minimum sweep: run against the routes affected by the change at desktop (1440) + tablet (1024) + mobile (375) viewports.
- Treat non-zero `horizontalScroll`, `overflowingElements`, `duplicateIds`, `consoleErrors`, or `requestFailures` as blocking signals.
- Reference the audit result (routes checked + findings summary) in the handoff / PR description.

Agents working on frontend tasks must invoke this skill rather than inferring visual correctness from code.

The toolchain the skill validates against (local Tailwind build, `stylelint`, Jinja partials, Playwright visual regression) is defined in [ADR-0027](docs/adr/0027-frontend-toolchain-hardening.md).

## Rules & scope

- **Scope guard**: `docs/requirements.md` section 3.8 lists what is **out of scope** for v1. Do not add v2 features without first writing a new ADR and updating `docs/requirements.md`.
- **Server binds to `127.0.0.1` only** in v1. No LAN or public exposure.
- **No secrets committed.** `detect-secrets` is in the pre-commit stack.
- **Timestamps are UTC in DB**, dates on transactions are naive `DATE`, display timezone defaults to `Europe/Warsaw`. See ADR-0007.
- **`data/budget.sqlite` = prod. Hands off.** No agent writes, migrations, resets, seeds, or ad-hoc SQL against it without explicit in-session user confirmation. For any DB experiment use `just dev --db=<path>` with a scratch file (e.g. `/tmp/scratch.sqlite`) or `just dev-demo`. See "Databases" section above.

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
- The anonymizer at `data/scripts/build_demo_db.py` only runs when the source basename ends with `budget.sqlite` as a tripwire against accidental swaps — do not weaken or remove that check.

### Files at a glance

| File | Role | Policy |
|------|------|--------|
| `data/budget.sqlite` | **Prod** (local, canonical user data). Gitignored. | **Hands off.** See rule above. No writes without explicit user confirmation in the current session. |
| `data/demo.sqlite` | Demo DB — anonymized, scaled copy of prod for feature walkthroughs. Tracked in git. | Rebuild with `just demo-build` (reads prod, writes demo; prod is untouched). Safe to nuke and regenerate. |
| `/tmp/*.sqlite` or any path via `--db=` | Scratch / testing. | Default target for any agent-driven DB experiment. Create, abuse, delete freely. |

## Handoff checklist (for subsequent agents)

Before marking a task done:

1. **Docs updated first** (see "Change policy" above). `docs/requirements.md`, `docs/tasks.md`, and/or a new ADR reflect the change *before* code lands.
2. Code + tests committed; `just ci` green. **No writes to `data/budget.sqlite`** during the task (prod DB — see "Databases"); any DB work ran against `--db=<scratch path>` or `data/demo.sqlite`.
3. **Frontend-touching tasks**: `frontend-visual-audit` skill run against the affected routes at desktop/tablet/mobile viewports; findings resolved or triaged (see "Frontend validation" above).
4. `docs/tasks.md` task line prefixed with `✅`.
5. Relevant ADR(s) referenced in the commit; a new ADR added if the task introduced an architectural decision not already recorded.
6. Append a dated line to `docs/CHANGELOG.md` (create on first use).
7. Conventional-commits message referencing the task id: e.g. `feat(T-021): derive account balance`.
