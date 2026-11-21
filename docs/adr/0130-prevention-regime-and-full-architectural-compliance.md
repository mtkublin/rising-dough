# ADR-0130: Prevention Regime and Full Architectural Compliance

- **Status**: Accepted
- **Date**: 2026-11-20
- **Amends**: [ADR-0120](0120-pre-commit-is-the-local-gate.md) (CI additionally runs the pre-commit hooks), [ADR-0007](0007-timezone-handling.md) (how "today" and "now" are obtained), [ADR-0021](0021-functional-style-no-gratuitous-oop.md) (purity is defined and enforced), [ADR-0022](0022-repository-layer-soft-delete-audit-discipline.md) (the deferred static-analysis rule for SQL outside repositories becomes a guard), [ADR-0066](0066-orchestrator-mode-skill.md) (search-before-write, shared-helper carve-out, merge-step duplication check)
- **Relates to**: [ADR-0120](0120-pre-commit-is-the-local-gate.md) (CI and pre-commit parity), [ADR-0097](0097-per-batch-ci-policy-and-fast-precommit-pytest.md), [ADR-0108](0108-faster-ci-parallel-tests-and-change-based-inner-loop.md), [ADR-0099](0099-release-and-environment-policy.md), [ADR-0107](0107-sourdough-redesign-from-designer-handoff.md), [ADR-0131](0131-mutation-testing-policy.md)
- **Inputs**: `docs/plans/quality-audit/findings.md` (frozen 2026-11-20, 80 Q-ids), `docs/plans/quality-audit/prevention.md` (gap analysis and control design G0 to G17, S1 to S4, R1 to R8), `docs/plans/quality-audit/compliance-inventory.md` (complete inventory of principle violations)

## Context

- The post-v3 audit found 80 issues. Their root causes are systemic: no registry of "where does concept X live" (so the fifth FX converter was written), principles stated only in prose (so nothing failed when they were broken), guards that run only when testmon selects them, and a CI that does not run everything pre-commit runs. See prevention.md §0.
- On 2026-11-20 the operator froze the findings (T-Q12) and added a directive: the plan must also converge the architecture to **full compliance** with the assumed principles (DRY, functional paradigm, no side effects and the rest). The target is **no violations at all**, not only the ones that caused bugs, and the development rules must be tightened so the codebase does not drift again.
- Prose rules failed here. Rules that fail a build do not. Each rule below therefore has an automated check where one is feasible.

## Decision

### 1. Zero-violation policy

1. Every principle stated in `CLAUDE.md` and `docs/requirements.md` §3 gets an automated guard where feasible: layering, repository-only SQL, DRY through canonical modules, functional style and purity, single clock, money rules, soft delete and audit, user scoping, no template logic, suppression hygiene, transaction boundaries.
2. Each guard's **allowlist starts as the complete inventory of current violations** (`compliance-inventory.md`, not only the audit's Q-ids) and **must reach zero**. The remediation backlog (T-Q2xx) is extended to burn every allowlist down; a guard is finished only when its allowlist file is empty.
3. **No new allowlist entry without an ADR amendment** (an amendment to this ADR naming the entry and the reason). A permanent exception (for example the PRAGMA statements in `db/connection.py`) is classified `permanent` with a reason in the allowlist and recorded in an amendment.
4. Guards that cannot be made reliable (heuristics such as compound-mutation detection, G8) are marked low confidence in their failure message, still run, and are reviewed at each burn-down wave.

### 2. Allowlist ratchet

- One TOML file per guard at `tests/architecture/allowlists/<guard>.toml`: sorted, one entry per `path` with an exact `count`, a `finding` field (Q-id or inventory id) and, for permanent entries, a `reason`.
- The test fails on **more** violations than allowed (new violation) **and on fewer** (the allowlist must shrink when a violation is fixed). Both directions are enforced so the allowlist always equals the truth.
- Counts per file, not line numbers, so unrelated edits do not break them. A new file has no allowance: new code starts at zero. This includes the ADR-0107 redesign templates, which start strict on template guards (accepted by default).
- A shared helper `tests/architecture/_ratchet.py` implements the comparison. Each guard has its own file (merge-conflict control; the files are orchestrator hotspots and each burn-down wave assigns one owner per file).
- **Failure messages teach**: each names the rule, the canonical module and the Q-id or ADR, so the rule is found at the point of action.
- Guards run on every commit. First the testmon hypothesis is measured (edit one scanned `src` file, run `just test-fast`, see whether the guard is selected). An always-on `architecture-guards` pre-commit hook is added **only if the experiment shows a gap** and only within the local time budget of §8; otherwise the guards run in CI only (accepted by default).

### 3. Canonical-modules registry

- `tests/architecture/canonical_modules.toml` is the machine-readable registry: concept, module, symbol, status (`exists` or `target`), finding, search terms, banned-copy name patterns. `CLAUDE.md` carries a table generated from it ("Canonical modules").
- Rows include FX conversion, money format/parse/exponent/minor-major, periods and month windows, recurring occurrence expansion, direction to sign, net worth, rounding, and the clock. `target` rows are labelled "not yet extracted: do not add a new copy; call the nearest listed function and note it in the report".
- Guard G6 bans, outside the canonical module: function names matching a row's banned-copy patterns, arithmetic `/ 100`, `* 100` and `Decimal("100")` on money, `round(` and `quantize` outside the rounding helper, and amount parsing outside `parse_amount_str`.
- G7 adds differential invariants (one shared multi-currency seed) landed as strict xfails that cite open Q-ids; a fix must remove the marker.

### 4. Clock module

- New `src/budget_planner/clock.py` with `utc_now()`, `today_local(settings)` and an injectable override (`ContextVar`) for tests. T-Q15 adds it as a **scaffold with no caller changed**; caller migration is Q-031's remediation.
- Ruff `flake8-tidy-imports.banned-api` (TID251) bans `datetime.date.today`, `datetime.datetime.now`, `datetime.datetime.utcnow` and `time.time` everywhere except `clock.py`. The allowlist is `per-file-ignores` (one entry per current offending file, commented `# Q-031`), not per-line `noqa`. Alias resolution (`import datetime as dt`) is verified on a fixture.
- Amends ADR-0007: UTC timestamps and the local "today" are obtained only through `clock`. ADR-0007's storage rules are unchanged.

### 5. Import contracts, layering and purity

- import-linter contracts in pre-commit and `just lint`: `domain` imports none of `services`, `repositories`, `db`, `web`; `services` not `web`; `repositories` not `services` or `web`; `web.routers` not `repositories`; `web` not `db` except the `db.connection` dependency-injection point. `allow_indirect_imports = true`; `ignore_imports` is the allowlist, one line per direct import, commented with the finding.
- G2: no SQL string outside `repositories/` and `db/migrate.py` (amends ADR-0022: this replaces its deferred static-analysis rule). G7b: no literal user id. G8: a service function calling two or more repository mutators runs in one `db_transaction`.
- **Pure layers (definition, amends ADR-0021).** `domain/` and the pure-function modules of `services/` perform no I/O, read no clock, environment or randomness, touch no global mutable state, and mutate no argument. Effects (database, clock, filesystem, network) live at the edges: repositories, `clock`, adapters, routers. Services may call repositories but take the clock and settings as inputs rather than reading them ambiently. The purity guard checks `domain/` for forbidden imports and calls, and `services/` for ambient reads and argument mutation; remaining sites are allowlisted from the inventory and burned to zero. **Amendment (operator, 2026-11-20): services may use `logging`; that is not a purity violation.**

### 6. Suppression hygiene

- Every `# noqa`, `# type: ignore`, `# nosec` and `# pragma: no cover` in `src/` carries a reason on the same line. Ruff `PGH` is enabled and `RUF100` kept. Per-code ceilings ratchet down (`PLC0415`, `PLR0917`; `DTZ011` goes to zero through the clock module). **No new suppression without a reason and, where a guard exists, without an ADR amendment.**

### 7. Tightened development rules

Written into `CLAUDE.md`, the orchestrator skill and the brief template by T-Q15 (operator-reviewed edits):

- **Search before write.** Read the Canonical modules table for the concept, run the table's search terms against the tree, and report `Searched: <queries>; Reused: <symbols>; New helper: <name> (why none fits, registered: yes/no)`. This complements the user-level "search first" rule, which is external-only.
- **Canonical-module reuse.** Call the canonical function; a `target` row is never copied, only called or noted.
- **Handoff checks.** The handoff checklist gains: reused helper or registered the new one; ADRs touched by the change re-read and still true; allowlist entries for fixed violations deleted; no new suppression or allowlist entry without a reason and amendment; new dependency justified.
- **Orchestrator.** When two or more items need a helper that does not exist, it is carved out as an earlier-wave item with a single owner. The merge step (ADR-0066) runs a mechanical duplication check (`scripts/ci/new_defs.py <MAIN>`, report-only) over definitions added by the item branches and forwards near matches.
- **Rules enforced by tests table** in `CLAUDE.md`: rule, guard file, what the error says.
- User-level `~/.claude/rules` are not edited (accepted by default).

### 8. CI and pre-commit parity

- **Operator decision (2026-11-20, revised): CI must have parity with pre-commit.** GitHub CI runs `pre-commit run --all-files` with `SKIP=pytest-fast`. CI keeps running the full pytest suite with coverage itself, so every other hook (ruff, ruff format, mypy, sqlfluff, djlint, stylelint, bandit, detect-secrets, the Tailwind staleness check, import-linter, the hygiene hooks) runs in CI exactly as locally.
- This **amends ADR-0120**: pre-commit stays the local gate and the full suite still runs only in PR CI, but CI additionally runs the same hooks. The audit (G-05) found that CI lacked ruff format, bandit, detect-secrets and the Tailwind check; parity by construction closes that gap with no allowlist.
- A small parity guard (G16), `tests/architecture/test_ci_precommit_parity.py`, remains. It asserts only that `ci.yml` keeps invoking `pre-commit run --all-files` (with `SKIP=pytest-fast`) and that the tool versions pinned in `.pre-commit-config.yaml` (ruff, mypy, sqlfluff, djlint, bandit) equal the versions in `uv.lock` (closes G-06 drift: sqlfluff 3.1.1 vs 4.4.0, djlint v1.35.2 vs 1.47.0, bandit 1.7.10 vs 1.9.4, Q-044).
- **Parity is on the CI side only.** Local pre-commit performance must **not** regress (ADR-0108, ADR-0120 speed work). No new slow local hooks. Any new local hook (import-linter, architecture guards) must be fast and is subject to a measured budget: T-Q15 measures local `pre-commit run` wall time before and after on a docs-only and a src-only change and must show no meaningful regression; otherwise that guard runs in CI only. ADR-0130 amends ADR-0120 only to add the CI-side hook run.
- CI time grows by the added hooks; it is to be measured, not assumed.

### 9. Operator-run checks

- **GitHub settings check (G17b)**: `scripts/ci/check_github_settings.py` reads environment reviewers, branch policies, branch protection and allowed-actions pinning through `gh api`. It is an **operator-run script**: no scheduled workflow and no new token. The declared expectation lives in `ci_environments.toml`, checked repo-side by `tests/architecture/test_workflow_secrets.py` (G17a). A new environment or secret needs an entry there and an operator go (ADR-0099 unchanged).
- **Prod-DB tripwire (G10)**: `tests/conftest.py` sets `BUDGET_ENV=test` unconditionally and an autouse session fixture makes `get_connection` raise when the resolved path equals `<repo>/data/budget.sqlite`; an architecture test forbids `budget.sqlite` references in `tests/` outside an allowlist of text assertions. The src-level guard is Q-060's remediation.

### 10. Other decisions

- ADR numbers 0105 and 0121 are duplicated; they are **grandfathered** (allowlisted in the ADR-index guard, not renumbered). The ADR index guard (G14) and guidance-path guard (G15) are added.
- The coverage-config guard (G5) allowlists the current `exclude_lines` value (Q-014); the fix is remediation.
- Mutation testing is governed by [ADR-0131](0131-mutation-testing-policy.md).
- **Amendment (T-Q16 dry run, 2026-11-20): registry statuses are `exists` / `exists-migrating` / `target` (an `exists` row needs zero banned copies; target rows carry `interim` and `migration_task`), and guard G30 `private_imports` (`test_private_imports.py`, `allowlists/private_imports.toml`) bans cross-module use of `_private` names, and guard G31 (`test_frontend_audit_record.py`) requires a `docs/audits/` record for template or CSS changes.**
- Operator decisions accepted by default (no objection recorded): always-on guards hook only if the testmon experiment shows a gap; grandfather 0105 and 0121; TOML exact-ratchet format; ADR-0107 redesign starts strict; user-level rules untouched.

## Consequences

- **Positive**: principles become failing tests; drift is caught at the commit; allowlists are an exact, shrinking inventory of debt; search-before-write gives agents a concrete module to find.
- **Costs**: a large burn-down backlog (the full inventory, not only the 80 Q-ids); remediation PRs each edit an allowlist file (merge hotspots, mitigated by one file per guard and single owners per wave); guards add commit time (to be measured, not assumed); heuristic guards can false-positive and need reasoned permanent entries.
- **Risk**: an allowlist entry added to silence a guard defeats the policy. Mitigation: a new entry needs an ADR amendment, and the both-directions ratchet shows every change in review.

## Alternatives considered

- Prose rules only: rejected, they already failed.
- A parity test with an allowlist instead of running pre-commit in CI: considered when the operator first declined pre-commit in CI, superseded by the revised decision (Decision 8).
- `pylint duplicate-code`: dropped, 19 boilerplate hits and none of the semantic duplicates.
- Report-only guards: rejected, the ratchet gives the same green CI while making regressions fail.
- A cyclomatic-complexity gate: deferred; the ADR-0107 redesign rewrites most routers.

## Amendment 2026-11-21 (ADR-0134 number held by another branch)

- **Exemption.** `tests/architecture/test_adr_index.py` gains the constant `TEMPORARY_GAPS = {134}` next to `GRANDFATHERED_GAPS` (G14, Q-051). It is temporary, unlike the 0044 gap.
- **Why.** ADR-0134 was written on `feat/ui-test-harness` (commit abbdc34) by another session and is not on `remediation/quality`. ADR-0135 (T-Q277) was numbered after it to avoid a collision, which leaves a transient gap on this branch. The ADR file must not be copied across branches. Every other gap still fails the guard.
- **Removal trigger.** When ADR-0134 reaches `main` and `main` is merged into `remediation/quality`, delete the constant. The guard reports `stale-gap-exemption` as soon as an `0134-*.md` file exists, so the exemption cannot outlive its reason and that failure is the reminder.
