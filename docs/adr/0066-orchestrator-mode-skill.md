# ADR-0066: Orchestrator Mode Skill for Parallel Multi-Agent Work

- **Status**: Accepted
- **Date**: 2026-11-03
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

## Consequences

- Orchestrated sessions are reproducible and rule-compliant by construction; every change is attributable to one item branch.
- Small fixes cost a subagent round-trip instead of a direct edit — accepted for traceability.
- Merge-based conflict resolution leaves merge commits on item branches; history is non-linear but faster to reconcile.
- Subagent cost drops substantially; briefs must be more precise to compensate for weaker models.
