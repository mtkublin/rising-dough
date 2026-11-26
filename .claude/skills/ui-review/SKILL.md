---
name: ui-review
description: Review the UI a branch changes before it merges (ADR-0155): dispatches the ui-reviewer agent, which checks the change against the design system, the established base UI and the designer's handoff (whichever exist) plus an aesthetics and UX rubric, and records PASS, RETURN or ESCALATE in the frontend audit record (guard G33). Mandatory for every UI-facing change. Use when the operator says "UI review", "review the UI", "check the design", or invokes /ui-review [branch].
---

# UI review

Every UI-facing change (templates, CSS, static JS, user-visible copy, layout, HTMX swaps) gets a UI review before merge (CLAUDE.md "Design gate", [ADR-0155](../../../docs/adr/0155-ui-reviewer-layered-design-references.md)). This skill runs it from the main session; in an orchestrated run the orchestrator dispatches the agent itself (`orchestrator-mode` Step 3).

## Steps

1. **Branch.** The argument, else the current branch. Find its worktree (`git worktree list`); the branch must be checked out somewhere, with a clean tree and its work committed. Never review `main`.
2. **Quick check first:** `just check-ui` in that worktree. Report the `FAIL` lines now; the agent will return them too, so fixing them first saves a round.
3. **Brief.** Collect:
   - worktree path, branch, `git rev-parse HEAD`, base ref (`origin/main`, or the work branch in a run);
   - the routes and states the change touches: from the templates and routers in `git diff --name-only <base>...HEAD` (say "find them" if unsure);
   - the design reference, if the task, PR or a `Design-Ref:` commit trailer names one;
   - the branch's audit record (`docs/audits/<date>-<slug>.md`), if any.
4. **Dispatch** the `ui-reviewer` agent (`.claude/agents/ui-reviewer.md`) with that brief, in the background. Do not review it yourself in parallel; the point is a separate pair of eyes.
5. **Relay** its report block:
   - `PASS`: the record is committed; G33 is satisfied.
   - `RETURN`: list the findings; they go back to whoever made the change, then run `/ui-review` again.
   - `ESCALATE`: put each question to the operator. "New design without /designer" means: run `/designer` for it, or the operator accepts it as is; record the operator's answer in the PR, then re-run `/ui-review` (the reviewer records `PASS` only once nothing is open).
