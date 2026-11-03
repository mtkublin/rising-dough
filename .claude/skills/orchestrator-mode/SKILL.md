---
name: orchestrator-mode
description: Run a task as a pure orchestrator. The main agent makes NO code or doc changes itself. It only (1) creates or reuses a main work branch, (2) splits the work into conflict-free items and dispatches as many parallel subagents as possible, each in its own git worktree + work-item branch, with a full brief of repo rules, and (3) merges finished item branches back into the main work branch, resolving conflicts by merging the main work branch into the item branch (never rebasing). Use when the user says "orchestrate", "orchestrator mode", "dispatch agents", "parallelize this", or invokes /orchestrator-mode.
---

# Orchestrator Mode

The main agent coordinates and does not implement. Every change to the repo
(code, tests, docs, ADRs, migrations, templates, config) is written by a
subagent in its own worktree. The main agent decomposes, dispatches, merges,
and reports. See [ADR-0066](../../../docs/adr/0066-orchestrator-mode-skill.md).

## 1. Hard rules for the orchestrator

**Allowed:**

- Read-only exploration needed to plan: `Read`, `Grep`, `Glob`, `git log/diff/show/status`,
  `ls`, `cat`. Keep it short. Delegate broad code research to an `Explore` agent.
- Branch management: create or switch to the main work branch.
- Dispatch subagents (`Agent` tool), message them (`SendMessage`), stop them (`TaskStop`).
- Merge item branches into the main work branch, and merge the main work branch
  into item branches when resolving conflicts (§5).
- Edit conflict hunks during a merge. Only the `<<<<<<<`/`>>>>>>>` regions, and only
  to reconcile both sides. Semantic conflicts go back to a subagent (§5).
- Run verification that does not change source: `just ci`, `just test`, `just lint`,
  `just typecheck`.
- Remove merged worktrees and delete merged item branches.
- Update `TaskCreate`/`TaskUpdate` progress tracking.

**Forbidden:**

- `Edit`, `Write`, or `NotebookEdit` on any repo file outside an active merge conflict.
- Changing files through `Bash` (`sed -i`, heredocs, `>`/`>>` redirects, `just format`,
  `ruff --fix`, scripts that write files).
- `git commit` of anything other than a merge commit. No `git rebase`,
  `git cherry-pick`, `git reset --hard`, or force-push on shared branches.
- "Quick fixes" after a merge. If `just ci` fails on the main work branch, dispatch
  a fix agent.
- Pushing, opening PRs, or touching `main` unless the user asks.
- Anything that touches `data/budget.sqlite` (see CLAUDE.md "Databases").

If you notice you are about to write code, stop and dispatch an agent.

## 2. Step 0: main work branch (mandatory)

```sh
git status --short            # must be clean, apart from untracked lock files
git rev-parse --abbrev-ref HEAD
```

- If the current branch is `main` (or the default branch), create a work branch
  before anything else: `git switch -c <slug>`. Use a short task slug, e.g.
  `feat/recurring-stop-date` or `v3-hardening`.
- If you are already on a non-default work branch (e.g. `v3`), reuse it. Do not
  create a nested one.
- If the tree is dirty with changes that are not yours, ask the user before you go on.

Write down `MAIN=<branch>`. Every item branch starts from it and merges back into it.

## 3. Step 1: decompose and plan the waves

1. Read the request plus the relevant parts of `docs/requirements.md`,
   `docs/tasks.md`, `docs/implementation_plan.md`, and the ADRs that cover the area.
2. Split the work into **work items**. Each item has an id (reuse task ids such as
   `T-D17` when they exist), a goal, a done-definition, the **files it owns**, and
   the items it depends on.
3. **Maximize parallelism, minimize conflicts.**
   - Items that own disjoint files run in the same wave.
   - Items that depend on another item's output (a new repo function, schema, macro)
     go in a later wave, or the dependency is carved out as its own small item first.
   - Do not split a change so finely that two agents edit the same function.
4. **Pre-assign shared sequence numbers** so parallel agents never collide:
   - ADR numbers: next free number in `docs/adr/`, one per item that needs an ADR.
   - Migration numbers: next free `migrations/NNNN_*.sql`, one per item that needs a migration.
5. **Known hotspots in this repo.** Assign each one to a single owner per wave,
   or accept small append-only conflicts and resolve them at merge:
   - `docs/tasks.md`, `docs/CHANGELOG.md`, `docs/adr/README.md` (append-only, so conflicts are trivial)
   - `migrations/` (numbering), `pyproject.toml`, `uv.lock`, `justfile`, `.pre-commit-config.yaml`
   - `src/budget_planner/web/templates/base.html`, shared macros/partials, Tailwind input CSS
   - shared fixtures in `tests/conftest.py`
6. Show the user the wave plan as a short table (item, owned files, wave, assigned
   numbers). In auto mode, show it and go on without waiting.

## 4. Step 2: dispatch

Launch **every item in the current wave in one message** (several `Agent` calls),
so they run at the same time.

Per agent:

- `isolation: "worktree"`, so each agent gets its own worktree and branch.
- `subagent_type`: `general-purpose` (or a fitting implementer such as `tdd-guide`).
  Never a read-only type.
- Background execution. Wait for completion notifications. Do not poll and do
  not sleep.
- **Auto mode:** if the session runs in auto mode, subagents inherit it. Do not
  override their permission mode. Tell them explicitly that they run autonomously
  and must not stop to ask for confirmation, except for the prod-DB rule.

### Brief template (fill in every field; the brief is the agent's only context)

```text
You are implementing work item <ID>: <one-line goal>.
Repo: budget_planner (FastAPI + Jinja2 + HTMX + SQLite). You are in your OWN git worktree.

## Branch setup (do first)
1. `git branch -m wi/<MAIN>/<ID>` (rename your worktree branch).
2. Make sure your branch contains the tip of `<MAIN>`:
   `git merge-base --is-ancestor <MAIN> HEAD || git merge --no-edit <MAIN>`
   Merge only. Never rebase.
3. Work and commit ONLY inside this worktree. Never cd into or edit the main checkout.

## Goal / done-definition
<what must be true when finished; acceptance criteria; requirement / task ids>

## Context
<relevant ADRs, files, functions, prior decisions, what was already ruled out>

## Ownership
- You own: <files/dirs>. Change only these, plus the doc files listed below.
- Do NOT touch: <files owned by parallel agents>. If you need a change there, stop and
  say so in your report instead of making it.
- Pre-assigned numbers: ADR-<NNNN> / migration <NNNN>. Use exactly these.

## Repo rules (MANDATORY; full text in CLAUDE.md, read it first)
- Docs first: update docs/requirements.md / docs/tasks.md / write the ADR before code,
  in the same branch.
- `data/budget.sqlite` is PRODUCTION. Never open, migrate, seed, reset, or query it. For any
  DB work use `--db=/tmp/<id>.sqlite` or `data/demo.sqlite`. `just migrate`, `just seed`,
  `just db-reset`, and the CSV import default to prod. Always pass a scratch `--db`.
- Functional-first; frozen dataclasses; thin routers, fat services; repositories own SQL;
  soft delete + audit log through the repository helpers; amounts are positive minor units.
- Server binds 127.0.0.1 only. No secrets committed.
- Template/CSS/HTMX changes: run the `frontend-visual-audit` skill on the affected routes at
  1440 / 1024 / 375 before you finish.
- `just ci` must be green (coverage gate 90%) before your final commit.
- Handoff checklist: mark the task `✅` in docs/tasks.md, add a dated line to docs/CHANGELOG.md,
  reference the ADR(s) in the commit.
- Commit format: `<type>(<ID>): <description>` (conventional commits).
- You run autonomously (auto mode). Do not stop to ask for confirmation. Prod-DB access is the
  only thing that needs the user.

## Report back (final message)
- branch name + final commit sha
- files changed (short list)
- `just ci` result (pass/fail + coverage); frontend audit summary if applicable
- anything left undone, assumptions you made, or changes you needed in files you do not own
```

## 5. Step 3: merge back

Merge each item as soon as it finishes. Do not wait for the whole wave, because
early merges keep later conflicts small.

1. Check the report: `just ci` green, docs updated, scope respected
   (`git diff --stat <MAIN>...wi/<MAIN>/<ID>`). If something is missing, `SendMessage`
   the same agent to finish it (it keeps its context). Do not fix it yourself.
2. In the main checkout, on `<MAIN>`:

   ```sh
   git merge --no-ff wi/<MAIN>/<ID> -m "merge(<ID>): <summary>"
   ```

3. **If it conflicts:** run `git merge --abort`, then resolve on the item branch by
   merging `<MAIN>` **into** it. Do not rebase. A merge resolves each conflict once;
   a rebase replays every commit and can conflict repeatedly.

   ```sh
   git -C <item-worktree> merge --no-edit <MAIN>
   ```

   - Trivial conflicts (append-only docs, import lists, adjacent independent hunks):
     resolve the hunks yourself in the item worktree, `git add`, `git commit --no-edit`.
   - Semantic conflicts (both sides changed the same logic, or the result needs new
     code): `SendMessage` the owning agent: "Merge `<MAIN>` into your branch and resolve
     the conflicts, then rerun `just ci`." If that agent has exited, dispatch a fresh
     agent into that worktree with the conflict context.
   - After resolving, rerun `just ci` in the item worktree (or have the agent do it),
     then repeat step 2. The merge into `<MAIN>` is now clean.
4. After each merge, run `just ci` on `<MAIN>`. If it fails, dispatch a fix agent. Do not
   fix it yourself.
5. **Prune at once:**

   ```sh
   git worktree remove -f -f <item-worktree>
   git branch -D wi/<MAIN>/<ID>
   ```

   `git worktree list` and `git branch` must show only in-flight items.
6. Once a wave's blockers are merged, dispatch the next wave from the updated `<MAIN>`.

## 6. Finish

- All items merged, `just ci` green on `<MAIN>`, no stray worktrees or branches.
- Report to the user: items done (id, merge sha), CI result, frontend audit summaries
  from agents, deferred or blocked items, follow-ups.
- Do not push or open a PR unless asked.
