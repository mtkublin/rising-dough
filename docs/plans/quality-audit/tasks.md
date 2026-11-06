# Post-v3 Code-Quality Audit — Tasks

> Flat index. The method for each task is in [implementation_plan.md](implementation_plan.md).
> Legend: `[P]` parallel-safe within its phase, `[S]` sequential, `→ T-Qxx` depends on upstream task.
> Acceptance = output file complete against its checklist + the guardrails in implementation_plan §11 respected + `✅` prefix added here.
> **Not started.** Blocked until v3 ships. Must complete before v4 starts (v4 T-E00 gate).

---

## Phase 0 — Preconditions

### T-Q01 [S] Pin the audit commit and set up the environment
- Blocked on v3 shipping (v3 Phase 4 ✅, prod cut over).
- `AUDIT_SHA` recorded; worktree and branch `audit/quality`; scratch DB `/tmp/audit.sqlite` copied from `data/demo.sqlite`.
- `findings.md` header filled in: SHA, date, tool versions, LOC per package.
- `just ci` green at `AUDIT_SHA`. If it is red, log the failure as Q-000.

## Phase 1 — Automated baseline → T-Q01

### T-Q02 [P] Static tool baseline
- Every tool in implementation_plan §2 has been run in report-only mode, with raw output in `baseline/<tool>.txt` and summaries in `baseline/README.md`.
- No dependency or config changes committed (tools run through `uv run --with`).

### T-Q03a [P] Mutmut spike
- `domain` only, unit tests, `--no-cov`. Record mutant count, wall time, kill / survive / timeout counts and fixture breakage.
- Prod-DB safety check passed.
- Go / no-go decision recorded in `baseline/README.md`.

### T-Q03b [S] Mutmut baseline and triage → T-Q03a (if go)
- `domain` and `services` baseline score per package in `baseline/mutmut.txt`.
- Survivors sorted into real gap (→ track F finding), equivalent (→ `baseline/mutmut-equivalent.md`) or low value (→ exclusion proposal).

## Phase 2 — Review tracks → T-Q02, T-Q03b

Each task writes only `tracks/<file>.md` and contains a coverage statement, findings in the §4 schema, and a questions list.

### T-Q04 [P] Track A — duplicated domain logic → `tracks/A-duplication.md`
- Concept map for every concept in plan §3 Track A, plus any new concept found, with implementations, behavioural differences and canonical home.
- Differential-invariant candidates listed; each one executed on the scratch DB.

### T-Q05 [P] Track B — layering and architecture → `tracks/B-layering.md`
- Every SQL site outside `repositories/`, every `PLC0415` and `PLR0917` suppression, and every file over 800 lines has been classified.

### T-Q06 [P] Track C — correctness risks → `tracks/C-correctness.md`
- Every clock call site and every broad `except` / fallback in money paths has been classified. Query counts per route recorded.

### T-Q07 [P] Track D — security → `tracks/D-security.md`
- Done by the security-reviewer agent. Route-by-route authz/IDOR table. CSRF, CSP, headers, XSS and SQLi checks done. Scanner results triaged.

### T-Q08 [P] Track E — frontend → `tracks/E-frontend.md`
- HTMX emitter/listener matrix; template-logic list; duplicate partials and macros; token violations. Any runtime claim backed by a `frontend-visual-audit` run (1440 / 1024 / 375).

### T-Q09 [P] Track F — tests → `tracks/F-tests.md`
- Mutmut real gaps carried in. Over-mocking, weak assertions, fixture duplication, flakiness (randomised order run) and coverage gaps listed. Prod-DB path grep clean, or flagged as a finding.

### T-Q10 [P] Track G — dead code and doc drift → `tracks/G-drift.md`
- Vulture results checked by hand. Every Accepted ADR checked against the code (still true / drifted / should be superseded). Pre-commit vs `just ci` vs CI parity table.

## Phase 3 — Verify and consolidate → T-Q04…T-Q10

### T-Q11 [S] Adversarial verification and consolidation
- Every Critical and High finding, plus at least 20% of Mediums, independently re-verified. Dismissed findings listed with reasons.
- Duplicates merged; severities calibrated; one best mitigation per finding; summary and histograms written.

### T-Q12 [S] Operator review → T-Q11
- The operator has accepted, adjusted or dismissed every Critical and High finding. `findings.md` frozen. **Deliverable 1 done.**

## Phase 4 — Prevention (sequential, only after T-Q12)

### T-Q13 [S] Audit of the guidance surface → `prevention.md` §1
- Every artefact in plan §7.1 reviewed against the root-cause classes that have Critical or High findings (always including `duplicate-logic`).

### T-Q14 [S] Control design → `prevention.md` §2 → T-Q13
- Prevention matrix: class → findings → control → artefact → verification. Strongest feasible control chosen for each class.

### T-Q15 [S] Apply controls → T-Q14
- Docs first: prevention ADR(s) (next free numbers; the mutation-testing ADR is **not** 0095), requirements §3.3 / §3 tooling, then CLAUDE.md, skills and briefs.
- Guards in allowlist mode with CI green. Mutmut setup committed (`pyproject`, `just mutate*`, `.gitignore`, fixture fixes). Nightly job decided.
- CLAUDE.md and skill edits reviewed by the operator.

### T-Q16 [S] Prevention dry run → T-Q15
- A fresh agent working on a synthetic duplication-prone task uses the canonical module, or the guard trips. Result recorded. `just ci` green. **Deliverable 2 done.**

## Phase 5 — Remediation backlog → T-Q12 (may overlap T-Q13…T-Q16)

### T-Q17 [S] Write the remediation backlog
- Accepted findings turned into `T-Q2xx` tasks in this file, ordered Critical → High → allowlist burn-down → Medium → Low. Each task lists its finding ids, ADRs, acceptance criteria and the allowlist entries it removes.
- Tasks that must be ✅ before v4 Phase 3 are tagged `[pre-v4-P3]`: Critical/High `duplicate-logic`, `repo-bypass` and `scoping-gap` (implementation_plan §9).

---

## Remediation (T-Q2xx)

_Filled in by T-Q17._
