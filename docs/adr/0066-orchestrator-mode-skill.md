# ADR-0066: Orchestrator Mode Skill for Parallel Multi-Agent Work

- **Status**: Accepted
- **Date**: 2026-11-03
- **Amended by**: ADR-0097 (verification policy: scoped checks per item, one full `just ci` per merge batch); [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md) (2026-11-20: search-before-write, shared-helper carve-out, merge-step duplication check); [ADR-0150](0150-orchestrator-role-agents-executable-dod-and-wave-testing.md) (2026-11-24: role agents, executable DoD, one test run per wave)
- **Related**: ADR-0027 (frontend toolchain / `frontend-visual-audit` skill)

## Context

Larger work (e.g. the v3 hardening bundle) has been run by a main agent dispatching subagents into git worktrees and merging their branches. Done ad hoc, this drifted: the main agent sometimes patched code itself after merges, subagents were missing repo rules (prod-DB hands-off, docs-first), parallel agents collided on ADR/migration numbers, rebases replayed conflicts repeatedly, and merged worktrees/branches piled up.

## Decision

Add a repo skill, `.claude/skills/orchestrator-mode/SKILL.md`, that codifies the workflow:

1. The main agent is **orchestrator only**: no code/doc edits, no non-merge commits. Its only write actions are creating/reusing the main work branch, dispatching subagents, merging item branches, and resolving merge-conflict hunks.
2. A **main work branch** is mandatory: created at start unless the session is already on a non-default work branch.
3. Work is split into **waves of conflict-free items** to maximize parallelism; shared sequence numbers (ADR, migration) are pre-assigned by the orchestrator.
4. Each subagent runs in its **own worktree + `wi/<main>/<id>` branch**, inherits auto mode when the session is in auto mode, and receives a brief containing the repo rules from `CLAUDE.md`.
5. Conflicts are resolved by **merging the main work branch into the item branch**, never rebasing; then the item merges cleanly with `--no-ff`.
6. Merged worktrees and branches are pruned immediately.

## Amendment (2026-11-03): cheaper subagent models

Subagents are dispatched with an explicit, cheaper `model` than the orchestrator's: `sonnet` by default, `haiku` for small mechanical or read-only items. `opus` is used only on user request or after two `sonnet` failures on the same item. The orchestrator keeps the strong model, because decomposition, briefs, and merges are where reasoning quality matters most; implementation tokens dominate cost.

## Amendment (2026-11-22): ways of working from the remediation run

- Heavy runs (full e2e, full suite and coverage, visual baselines, mutation) go to GitHub workflows where one exists; item agents test only via the commit hooks, and the draft PR is opened early (once the user approves) so `ci.yml` tests merged combinations.
- Agents are sized to under ~1 h: the orchestrator checks in at ~30 min and splits the item or hands the worktree to a fresh agent at ~60 min without commit progress; overruns go in the final report.
- Merge review rejects guard-gaming: a syntactic dodge goes back to the agent. Merges skip hooks, so `just merge-item` (T-Q304) runs guards, lint-imports, ruff and mypy before the push and prunes only on success.
- The brief is a shared `brief-common.md` plus the item-specific part (T-Q303).

## Amendment (2026-11-24): role agents, executable DoD, wave testing (ADR-0150)

- Subagents are role definitions in `.claude/agents/` (`explorer`, `implementer`, `scribe`, `reviewer`, `tester`, `visual-auditor`). The model is pinned in frontmatter: Haiku for explorer, scribe and tester; Sonnet for the rest. An `implementer` item goes to Haiku when it passes the Haiku test of ADR-0150 §3. The 2026-11-03 model rule is replaced by the escalation ladder there: Haiku fails once, retry on Sonnet; Sonnet fails twice, try Opus.
- The orchestrator no longer reviews diffs. Per item it reads `scripts/ci/check_item.py` and the `reviewer` verdict. Doc bookkeeping (tasks marks, CHANGELOG, ADR index, run log) is one `scribe` run per wave.
- Briefs meet a Definition of Ready and are numbered steps with command checks. Reports end in a fixed block (ADR-0150 §4).
- Orchestrated item agents commit with `SKIP=pytest-fast`; one `tester` per wave runs the tests (ADR-0150 §5, amends ADR-0120 for orchestrated runs).

## Consequences

- Orchestrated sessions are reproducible and rule-compliant by construction; every change is attributable to one item branch.
- Small fixes cost a subagent round-trip instead of a direct edit — accepted for traceability.
- Merge-based conflict resolution leaves merge commits on item branches; history is non-linear but faster to reconcile.
- Subagent cost drops substantially; briefs must be more precise to compensate for weaker models.
