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
- Remove merged worktrees and delete merged item branches (§5, `just merge-item`).
- Update `TaskCreate`/`TaskUpdate` progress tracking.

**Forbidden:**

- `Edit`, `Write`, or `NotebookEdit` on any repo file outside an active merge conflict.
- Changing files through `Bash` (`sed -i`, heredocs, `>`/`>>` redirects, `just format`,
  `ruff --fix`, scripts that write files).
- `git commit` of anything other than a merge commit. No `git rebase`,
  `git cherry-pick`, `git reset --hard`, or force-push on shared branches.
- "Quick fixes" after a merge. If CI fails on the main work branch, dispatch
  a fix agent.
- Pushing, opening PRs, or touching `main` without the user's approval (§6). Once approved,
  push and open the (draft) PR early.
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
  shared mkdir lock (see "Heavy locks"). Keep ~4-5 agents running in total.
- **Size items so one agent finishes in under ~1 h** (operator 2026-11-22: "a subagent running
  for 1h is too much"; some ran 3-6 h). Split large items into waves or carve-outs at planning
  time (§3), and put the budget in the brief.
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
  - Haiku suits docs-only and mechanical items.
- Background execution. Wait for completion notifications. Do not poll and do
  not sleep.
- **Auto mode:** if the session runs in auto mode, subagents inherit it. Do not
  override their permission mode. Tell them explicitly that they run autonomously
  and must not stop to ask for confirmation, except for the prod-DB rule.

### Brief template (the brief is the agent's only context)

The task brief is two parts: the shared [brief-common.md](brief-common.md) (branch setup,
repo rules, testing, CPU, locks, runtime budget, report format; paste it verbatim and fill
`<MAIN>`, `<ID>`, `<plan>`) plus the item-specific part below. Add the lock name
(`/tmp/<plan>-heavy.lock`), the open slots, and the base sha the agent's `git log -1` must show.

```text
You are implementing work item <ID>: <one-line goal>.
Repo: budget_planner (FastAPI + Jinja2 + HTMX + SQLite). You are in your OWN git worktree.

## Goal / done-definition
<what must be true when finished; acceptance criteria; requirement / task ids>

## Context
<relevant ADRs, files, functions, prior decisions, what was already ruled out>

## Ownership
- You own: <files/dirs>. Change only these, plus the doc files listed below.
- Do NOT touch: <files owned by parallel agents>. If you need a change there, stop and
  say so in your report instead of making it.
- Pre-assigned numbers: ADR-<NNNN> / migration <NNNN>. Use exactly these.

<contents of brief-common.md>
```

**Testing in the brief** (full text in the common file): item agents test only via the commit
hooks (ADR-0120). No manual unit/integration/contract/e2e suites and no post-merge reruns.
While developing, run only the file being written: `uv run pytest <file> -q --no-cov -p no:xdist`.
Every commit is prefixed `PYTEST_WORKERS=2` (plain `-n auto` caused load 70-110 on 8 cores).
The `frontend-visual-audit` skill is still required for template/CSS changes.

### Heavy locks

Heavy jobs (full suite in a hook, `just ci`, Mutmut, e2e, the visual audit) take a mkdir lock.
The orchestrator picks one lock name per plan, `/tmp/<plan>-heavy.lock`, and states it in
EVERY brief. A name is never shared with another session or plan. The default is one slot. The
orchestrator may open a second slot, `/tmp/<plan>-heavy-2.lock`, only while the 5-minute load
average stays below 2x `sysctl -n hw.ncpu`, and stops granting it when load rises. Agents take
the lock in separate Bash calls (the worktree sandbox refuses a combined lock + git command):
acquire, commit, `rmdir` the lock. They release it also when the job or commit fails. The
orchestrator frees a stale slot only when `pgrep -fl pytest` shows no test run.

### Delegate heavy work to GitHub where feasible

The laptop is shared by parallel agents, so anything heavy runs on GitHub runners when a
workflow exists. Rule of thumb: if a run takes more than ~2 min of CPU locally and a workflow
can run it, use the workflow. Watch it with a background `gh run watch`, not by polling.

- **Full e2e:** push a `wi/**` branch, read the `e2e.yml` run (`gh run watch`), delete the
  branch on origin after.
- **Full suite and coverage:** once the user has approved opening a PR, open it (draft) early,
  so `ci.yml` runs on every merge push. A clean `git merge` runs no pre-commit hooks, so this is
  what tests merged combinations.
- **Visual baselines:** generated only by `visual.yml` in the pinned container. Download the
  `visual-baselines` artifact; an agent commits it. Never generate them locally.
- **Mutation:** the weekly `mutation.yml`.

Pushing and opening a PR still need the user's approval (§6); once approved, do it early.

## 4b. Supervise running agents

- Check in periodically, not by sleeping or polling in a loop: on each completion
  notification and at natural pauses. For each in-flight item, look at
  `git -C <worktree> log --oneline <MAIN>..HEAD`, `git -C <worktree> status --short`,
  the newest mtime of the changed files, and `pgrep -fl pytest` / `ps` for its processes.
- Long-running is not stuck. Treat an agent as stuck only with evidence: no new commits,
  no file changes and no live processes for a long stretch, or a hook/test process hung
  (e.g. waiting on a lock held by a dead process). A stale `/tmp/<plan>-heavy.lock` may be removed by the orchestrator only when
  `pgrep -fl pytest` shows no test run.
- Stuck agent: stop it (`TaskStop`), but never drop its work. Keep the worktree and
  branch, including uncommitted changes. Do not `git worktree remove`, `git checkout .`,
  `git stash` or `git reset`.
- **Runtime budget.** Check in on every agent at ~30 min: `SendMessage` asking for status and
  blockers, or look at its worktree's git log and the processes in its cwd. At ~60 min with no
  commit progress, act: split the remainder into a new item, or stop the agent and hand its
  worktree, including uncommitted work, to a fresh agent with a tighter brief. Typical causes:
  waiting on a heavy lock, CPU contention, repeated merge-conflict loops, hand-running suites,
  gold-plating beyond the brief. Record every overrun in the final report.
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
   **Reject guard-gaming.** A fix that satisfies a guard syntactically without removing the
   cause goes back to the agent (example: the `lru_cache(fn)` call form to dodge the
   hidden-cache scan). The fix is a real code change, or a `[[permanent]]` row with a reason
   and an ADR-0130 amendment.
2. In the main checkout, on `<MAIN>` (start every orchestrator command with a `cd` to the
   main checkout; the shell cwd drifts into worktrees):

   ```sh
   just merge-item <ID> "<summary>"
   ```

   The recipe (`scripts/ci/merge_item.sh`, T-Q304) refuses on `main`, a dirty tree or an
   unfinished merge, merges `wi/<MAIN>/<ID>` with `--no-ff` and the message
   `merge(<ID>): <summary>`, then, because a merge skips the hooks, runs `just guards`,
   `uv run lint-imports`, `uv run ruff check src tests` and `uv run mypy src tests`. Only when
   all return 0 does it push `<MAIN>` and prune (step 5). On a check failure it stops with the
   merge commit in place, unpushed and unpruned: dispatch a fix agent. On a conflict it aborts
   the merge and exits non-zero (step 3). Prune only on git's return code, never on piped output.

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
   The hook excludes `tests/e2e` (ADR-0120 amendment 2026-11-22). After each wave you may
   run `just test-e2e` yourself with NO agents active. No local run is needed before a PR:
   `e2e.yml` runs on every PR to `main` and is a required check (ADR-0120 amendment
   2026-11-22, T-Q297). If it fails, dispatch fix agents; repeat until green. Item agents run hooks only plus special cases
   (frontend-visual-audit, a migration rehearsal); one that truly needs the full e2e pushes
   its `wi/**` branch and reads the `e2e.yml` run.
   If CI fails, dispatch a fix agent. Do not fix it yourself.
5. **Prune at once** (`just merge-item` does the git part after a green gate):

   ```sh
   git worktree remove -f -f <item-worktree>
   git branch -D wi/<MAIN>/<ID>
   ```

   Extras: delete local `worktree-agent-*` branches with zero commits not in `<MAIN>`
   (`git rev-list --count <MAIN>..<b>`; failed worktree creation leaves them); delete pushed
   `wi/**` branches on origin; kill the finished agent's leftover shells, matched by cwd
   containing its worktree name (the script does not kill processes).

   `git worktree list` and `git branch` must show only in-flight items.
6. Once a wave's blockers are merged, dispatch the next wave from the updated `<MAIN>`.

## 6. Finish

- All items merged, GitHub CI green on `<MAIN>`, no stray worktrees or branches.
- Report to the user: items done (id, merge sha, model used), CI result, frontend audit summaries
  from agents, deferred or blocked items, follow-ups.
- Report any agents stopped as stuck, and how their work was handed over (§4b).
- Push and open a PR only with the user's approval; once approved, push and open the draft PR
  early so `ci.yml` runs on every merge push (see "Delegate heavy work to GitHub").
- **GitHub settings are operator steps.** Rulesets, environments and secrets: prepare a
  reviewed input/command file and list it for the operator. If the auto-mode safety check blocks
  it, do not retry or work around it.
- **Questions and counts.** Collect operator questions in a deferred-questions file and ask at
  the end unless one blocks. Before telling the user any count (agents running, tasks left, open
  questions), derive it from a command.
- **Agent quirks.** Agents commit with plain commands (the worktree guard refuses a chained
  `git commit`).
