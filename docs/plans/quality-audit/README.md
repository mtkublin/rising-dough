# Post-v3 Code-Quality Audit

> **When**: after v3 ships (v3 Phase 4 validation complete and prod cut over), **before v4 starts**. The audit is a v4 Phase 0 (T-E00) precondition; decided 2026-11-06.
> **Scope**: the whole repository at one pinned commit: `src/`, `tests/`, templates, static assets, migrations, `terraform/`, CI workflows, `CLAUDE.md`, `.claude/skills/`, `docs/`.
> **Mode**: read-only audit. No production code changes during the audit. Fixes are a separate remediation effort that the audit's output feeds.
> Requirements: [`docs/requirements.md` §8](../../requirements.md#8-post-v3-code-quality-audit-added-2026-11-06).

## Why

The project started with explicit principles: functional-first (ADR-0021), thin web and fat services, repository discipline for soft-delete and audit (ADR-0019, ADR-0022), immutability, and DRY. After v1→v3, with about 22k lines of Python, 110 templates, and many parallel agent work items, there are concrete signs of drift:

- **Duplicated domain logic has already caused bugs.** FX conversion exists in about six places: `services/fx.py`, `services/budget.py`, `services/forecast.py`, `web/today_data.py`, and a nested helper in `web/routers/ledger.py`. T-FIX6 (ADR-0095) and T-JPY were bugs where parallel implementations disagreed.
- **Routers have grown large.** `web/routers/recurring.py` is about 1130 lines, `auth.py` about 760 and `planned.py` about 570. That points to business logic leaking out of services.
- **Lint suppressions hide structural problems.** About 118 `noqa` comments, including 37 × `PLC0415` (imports inside functions, usually a sign of import cycles), 30 × `PLR0917` (too many positional arguments) and 18 × `DTZ011` (`date.today()` without a timezone).
- **Time handling is not centralised.** There are about 45 direct `now()`/`today()` call sites, against ADR-0007 (UTC storage, `Europe/Warsaw` display).
- **SQL appears outside `repositories/`** in about 14 files. Some may be legitimate (migrations, DB bootstrap); the rest are potential soft-delete and audit bypasses.

These numbers are from a quick grep on 2026-11-06. The audit re-measures them at its pinned commit.

v4 (field-level encryption) does a repository sweep and moves aggregates into Python (ADR-0081). Each duplicated aggregate or conversion path would then have to be encrypted and decrypted separately. So the audit runs before v4, and its Critical/High remediation for duplication, repository bypass and scoping gaps lands before v4 Phase 3. See [implementation_plan.md §9](implementation_plan.md#9--sequencing-vs-v4-decided).

## Outputs

| # | Deliverable | Path | Produced in |
|---|---|---|---|
| 1 | **Findings register.** Every issue, vulnerability or bug, each with location(s), description, a single best mitigation (alternatives only when the choice is genuinely open), severity, confidence and effort. | `docs/plans/quality-audit/findings.md` | Phases 1–3 |
| 2 | **Prevention pass.** An audit of `CLAUDE.md`, repo skills, agent briefs, ADRs, plans and the lint/test/CI config against the Critical/High root causes, followed by corrections, so these issue classes do not come back. Runs **after** deliverable 1 is final, not in parallel. | `docs/plans/quality-audit/prevention.md`, plus the edited files | Phase 4 |
| — | Remediation backlog: findings turned into tasks and ADRs. The fixes themselves are executed later. | `docs/plans/quality-audit/tasks.md` (T-Q2xx) | Phase 5 |

Mutation testing (Mutmut) is folded in. A baseline run during the audit adds its surviving mutants to deliverable 1. Committing the tooling (ADR, `pyproject`, `just` recipes) is a prevention control in deliverable 2. Killing the surviving mutants is remediation.

## Contents

- [`implementation_plan.md`](implementation_plan.md): phases, tracks, method, finding schema, severity rubric, guardrails, sequencing.
- [`tasks.md`](tasks.md): task index T-Q01…, with acceptance criteria.
- [`findings.md`](findings.md): the register skeleton. It is filled in during the audit.

## At a glance

| Phase | What | Gate |
|---|---|---|
| 0 — Preconditions | v3 shipped; pin the audit commit; audit worktree; scratch DB | operator go-ahead |
| 1 — Automated baseline | linters in report-only mode, complexity, dead code, clones, import graph, coverage, security scanners, Mutmut spike and baseline | raw reports committed under `baseline/` |
| 2 — Review tracks (parallel, read-only) | A duplication · B layering · C correctness · D security · E frontend · F tests · G dead code and doc drift | each track file complete against its checklist |
| 3 — Verify and consolidate | adversarial verification, dedupe, severity calibration, single best mitigation | `findings.md` final; operator review |
| 4 — Prevention (sequential, after 3) | root-cause classes → controls in CLAUDE.md, skills, docs and automated guards | `prevention.md` signed off; doc/skill edits merged |
| 5 — Remediation backlog | findings → T-Q2xx tasks and ADRs, ordered by severity | backlog reviewed; pre-v4-Phase-3 subset tagged |
