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
- Run verification that does not change source: `just test`, `just lint`,
  `just typecheck`. No local full `just ci` per batch (ADR-0097 amendment, 2026-11-18).
- Remove merged worktrees and delete merged item branches.
- Update `TaskCreate`/`TaskUpdate` progress tracking.

**Forbidden:**

- `Edit`, `Write`, or `NotebookEdit` on any repo file outside an active merge conflict.
- Changing files through `Bash` (`sed -i`, heredocs, `>`/`>>` redirects, `just format`,
  `ruff --fix`, scripts that write files).
- `git commit` of anything other than a merge commit. No `git rebase`,
  `git cherry-pick`, `git reset --hard`, or force-push on shared branches.
- "Quick fixes" after a merge. If CI fails on the main work branch, dispatch
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

1. Read the request plus the relevant parts of `docs/requirements.md`, the active plan's
   `docs/plans/<plan>/tasks.md` and `implementation_plan.md`, the CLAUDE.md "Canonical modules"
   table, and the ADRs that cover the area.
2. Split the work into **work items**. Each item has an id (reuse task ids such as
   `T-D17` when they exist), a goal, a done-definition, the **files it owns**, and
   the items it depends on.
3. **Maximize parallelism, minimize conflicts.**
   - Items that own disjoint files run in the same wave.
   - Items that depend on another item's output (a new repo function, schema, macro)
     go in a later wave, or the dependency is carved out as its own small item first.
   - Do not split a change so finely that two agents edit the same function.
   - **Shared-helper carve-out (ADR-0130 §7).** When two or more items need a helper that
     does not exist yet (a month window, a converter, a parser), carve it out as its own
     earlier-wave item with a single owner; later items import it. Two items that each own
     a helper for the same concept is the duplication this rule exists to stop. Check the
     Canonical modules table first: a `target` row means the helper is still to be extracted.
4. **Pre-assign shared sequence numbers** so parallel agents never collide:
   - ADR numbers: next free number in `docs/adr/`, one per item that needs an ADR.
   - Migration numbers: next free `migrations/NNNN_*.sql`, one per item that needs a migration.
5. **Known hotspots in this repo.** Assign each one to a single owner per wave,
   or accept small append-only conflicts and resolve them at merge:
   - `docs/plans/<plan>/tasks.md`, `docs/CHANGELOG.md`, `docs/adr/README.md` (append-only, so conflicts are trivial)
   - `tests/architecture/allowlists/*.toml` (one file per guard) and `tests/architecture/canonical_modules.toml`: **one owner per file per wave**. Burn-down items that delete entries from the same allowlist go in different waves or are merged into one item. The ratchet fails on stale entries, so a lost deletion breaks CI.
   - `migrations/` (numbering), `pyproject.toml`, `uv.lock`, `justfile`, `.pre-commit-config.yaml`
   - `src/budget_planner/web/templates/base.html`, shared macros/partials, Tailwind input CSS
   - shared fixtures in `tests/conftest.py`
6. Show the user the wave plan as a short table (item, owned files, wave, assigned
   numbers). In auto mode, show it and go on without waiting.

## 4. Step 2: dispatch

Launch the wave's items in one message (several `Agent` calls) so they can run at
the same time. Size the number of concurrent agents to **live machine load**, not to
the plan's item count. Other sessions share this machine.

- Before each dispatch, check `uptime` (load average vs `sysctl -n hw.ncpu`) and
  `memory_pressure`.
- Cap heavy jobs (full suite, Mutmut, e2e, Playwright) at ~1 at a time, using the
  shared mkdir lock. Keep ~4-5 agents running in total.
- If load is above ~2x cores, hold back or stop the least critical agent.
- Queue the remaining items and dispatch them as slots free up.

Per agent:

- `isolation: "worktree"`, so each agent gets its own worktree and branch.
- `subagent_type`: `general-purpose` (or a fitting implementer such as `tdd-guide`).
  Never a read-only type.
- **`model`: always set it explicitly to a cheaper model than the orchestrator's.**
  Agents otherwise inherit the orchestrator's (expensive) model.
  - `model: "sonnet"` is the default for every implementation, fix, and conflict-resolution agent.
  - `model: "haiku"` for small mechanical items: renames, doc-only or changelog edits,
    config tweaks, test-only additions that follow an existing pattern, and read-only
    `Explore` research.
  - Use `opus` only when the user asks for it, or after a `sonnet` agent has failed the
    same item twice. Mention every escalation in the final report.
  - Cheaper models need tighter briefs: name exact files, functions, and acceptance checks.
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
- Docs first: update docs/requirements.md / docs/plans/<plan>/tasks.md / write the ADR before code,
  in the same branch.
- `data/budget.sqlite` is PRODUCTION. Never open, migrate, seed, reset, or query it. For any
  DB work use `--db=/tmp/<id>.sqlite` or `data/demo.sqlite`. `just migrate`, `just seed`,
  `just db-reset`, and the CSV import default to prod. Always pass a scratch `--db`.
- Functional-first; frozen dataclasses; thin routers, fat services; repositories own SQL;
  soft delete + audit log through the repository helpers; amounts are positive minor units.
  Clock only via `budget_planner.clock`; money only via `domain.money`; never a literal user id;
  no arithmetic or `float` in templates; every `noqa` / `type: ignore` carries a reason.
  Pure layers do no I/O (CLAUDE.md "Code conventions").
- **Search before you write.** (1) Read CLAUDE.md "Canonical modules" for your concept.
  (2) Run that row's search terms over `src/` (`rg -n "def .*(convert|month|period|today|sign|parse)"`
  style). (3) Call or extend the canonical function; a `target` row is never copied: call its public `Interim` copy, or do its registered extraction task
  migrating ALL copies in one change; never import another module's `_private` name. A new shared helper is registered in `tests/architecture/canonical_modules.toml`
  (you own that file only if listed above; otherwise name the row in your report).
- **No new allowlist entry or suppression** without a reason and an ADR-0130 amendment. Delete
  allowlist entries for violations you fix. Architecture guards (`just guards`) must be green.
- Server binds 127.0.0.1 only. No secrets committed.
- Template/CSS/HTMX changes: run the `frontend-visual-audit` skill on the affected routes at
  1440 / 1024 / 375 before you finish.
- Run `just worktree-init` once at the start (seeds testmon data from the main checkout).
- Your checks are the pre-commit hooks (ADR-0120): on every commit they lint, run
  `mypy --strict` and run the tests affected by your change across the whole suite
  (testmon; the full suite when you touch a migration, SQL, dependency, `conftest.py` or
  other non-Python file). `just lint-changed <MAIN>` / `just test-changed <MAIN>` run the
  same selection before a commit (arguments are positional). Run terraform checks by hand
  if you touched Terraform. Do NOT run full `just ci`; PR CI runs the full suite. Never use `--no-verify`. If the pre-commit
  pytest hook stalls because other agents are running pytest, wait until no other pytest is
  running (`pgrep -fl pytest`), then retry.
- `export PYTEST_WORKERS=2` before running tests or committing: `just test` and the pre-commit
  pytest hook run xdist with that many workers, so parallel agents don't each take every core
  (ADR-0108 §1).
- Handoff checklist: commit hooks green, ADRs you touched re-read and still true, mark the task `✅`
  in `docs/plans/<plan>/tasks.md`, add a dated line to docs/CHANGELOG.md, reference the ADR(s) in the commit.
- **CPU budget (shared machine, parallel agents).** `export PYTEST_WORKERS=2`. Run at most one heavy
  job (full suite, Mutmut, e2e, `just ci`) at a time per slot; take the lock and always release it.
  The orchestrator picks one lock name per effort and session, `/tmp/<effort>-heavy.lock`
  (e.g. `/tmp/remediation-heavy.lock`), and states it in EVERY brief. A lock name must never be
  shared with another session or effort. If load allows, the orchestrator may open a second slot,
  `/tmp/<effort>-heavy-2.lock`, and says so in the brief. It opens the second slot only while the
  5-minute load average stays below 2x the core count (`sysctl -n hw.ncpu`), and closes it again
  (stops granting it in briefs) when load rises above that; the default is one slot. With two slots
  open the acquire loop tries both:
  `while :; do mkdir /tmp/<effort>-heavy.lock 2>/dev/null && { echo SLOT=/tmp/<effort>-heavy.lock; break; }; mkdir /tmp/<effort>-heavy-2.lock 2>/dev/null && { echo SLOT=/tmp/<effort>-heavy-2.lock; break; }; sleep 20; done`
  (drop the second `mkdir` when only one slot is open) and prints the slot it took.
  The worktree sandbox refuses a combined lock + git Bash command, so use THREE separate Bash
  calls: (1) acquire (the loop above), (2) `PYTEST_WORKERS=2 git commit ...`, (3) `rmdir <the SLOT
  path printed in (1)>`. Always release (3), also when the commit fails. Commits that run the
  full suite in the hook count as heavy. If a known load-sensitive e2e test (e.g.
  `tests/e2e/test_ledger_filters.py`) fails, release the lock, wait, and retry; do not skip hooks.
- Commit format: `<type>(<ID>): <description>` (conventional commits).
- You run autonomously (auto mode). Do not stop to ask for confirmation. Prod-DB access is the
  only thing that needs the user.

## Report back (final message)
- branch name + final commit sha
- files changed (short list)
- commit hook results (affected tests run, pass/fail) and any manual checks (terraform); frontend audit summary if applicable
- `Searched: <queries>; Reused: <symbols>; New helper: <name> (why none fits; registered in canonical_modules.toml: yes/no)`
- allowlist entries deleted (file, path, count) and confirmation that none were added
- anything left undone, assumptions you made, or changes you needed in files you do not own
```

## 4b. Supervise running agents

- Check in periodically, not by sleeping or polling in a loop: on each completion
  notification and at natural pauses. For each in-flight item, look at
  `git -C <worktree> log --oneline <MAIN>..HEAD`, `git -C <worktree> status --short`,
  the newest mtime of the changed files, and `pgrep -fl pytest` / `ps` for its processes.
- Long-running is not stuck. Treat an agent as stuck only with evidence: no new commits,
  no file changes and no live processes for a long stretch, or a hook/test process hung
  (e.g. waiting on a lock held by a dead process). A stale `/tmp/*-heavy.lock` whose
  owner is gone may be removed by the orchestrator.
- Stuck agent: stop it (`TaskStop`), but never drop its work. Keep the worktree and
  branch, including uncommitted changes. Do not `git worktree remove`, `git checkout .`,
  `git stash` or `git reset`.
- Hand over: dispatch a fresh agent into that same worktree. Tell it the path and branch,
  and that it must `cd` there and must not create a new worktree. The brief is the original
  brief plus a summary of what is done (`git log`, `git diff --stat`, `git status`) and
  what remains.
- A second stall on the same item: escalate per the model rules in §4 and mention it in
  the final report.

## 5. Step 3: merge back

Merge each item as soon as it finishes. Do not wait for the whole wave, because
early merges keep later conflicts small.

1. Check the report: commit hooks green, docs updated, scope respected
   (`git diff --stat <MAIN>...wi/<MAIN>/<ID>`), the `Searched/Reused/New helper` line is
   present, and allowlist counts only went down. If something is missing, `SendMessage`
   the same agent to finish it (it keeps its context). Do not fix it yourself.
   **Frontend audit check.** Refuse to merge a branch that touches templates, CSS or HTMX swap targets unless the report includes the `frontend-visual-audit` result (routes x 1440/1024/375 and the five diagnostics) and the branch adds `docs/audits/<date>-<slug>.md`; `SendMessage` the agent to run the skill (ad-hoc Playwright does not count).
   **Duplication check (ADR-0130 §7).** List the definitions the branch adds and look for
   near matches of canonical ones: run the report-only `new_defs.py <MAIN>` helper (under scripts/ci) if it exists,
   else list added definitions with `git diff <MAIN>...wi/<MAIN>/<ID> -U0 -- 'src/*.py'`
   filtered to lines starting `+def ` or `+async def `, then `rg` each new name and its concept
   words against `src/`. Anything resembling a Canonical modules row (convert, month/period,
   sign, parse, today, totals) goes back to the agent via `SendMessage` to reuse the owner
   before the merge.
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
     the conflicts and commit (the hooks rerun the affected tests)." If that agent has exited, dispatch a fresh
     agent into that worktree with the conflict context.
   - Resolving commits run the pre-commit hooks (affected tests included); then repeat
     step 2. The merge into `<MAIN>` is now clean.
4. No local full `just ci` per batch or per PR (ADR-0120, ADR-0097 amendment 2026-11-18):
   each item's commits already ran the affected tests in the pre-commit hook, and GitHub
   `ci.yml` on the PR plus the gate drill's `just ci` job run the full suite. You may still
   run `just ci` on `<MAIN>` when a batch looks risky (several items touching the same area).
   Before opening or updating a PR, if the batch touched e2e-relevant code, run
   `uv run pytest tests/e2e -q --no-cov` locally (GitHub runners have no Playwright browser).
   If CI fails, dispatch a fix agent. Do not fix it yourself.
5. **Prune at once:**

   ```sh
   git worktree remove -f -f <item-worktree>
   git branch -D wi/<MAIN>/<ID>
   ```

   `git worktree list` and `git branch` must show only in-flight items.
6. Once a wave's blockers are merged, dispatch the next wave from the updated `<MAIN>`.

## 6. Finish

- All items merged, GitHub CI green on `<MAIN>`, no stray worktrees or branches.
- Report to the user: items done (id, merge sha, model used), CI result, frontend audit summaries
  from agents, deferred or blocked items, follow-ups.
- Report any agents stopped as stuck, and how their work was handed over (§4b).
- Do not push or open a PR unless asked.
