---
name: orchestrator-mode
description: Run a task as a pure orchestrator. The main agent makes NO code or doc changes itself. It plans conflict-free work items that pass a Definition of Ready, dispatches role agents (.claude/agents - implementer, scribe, reviewer, tester, visual-auditor, explorer) each in its own git worktree + work-item branch, reads the executable Definition of Done (just check-item) and the reviewer's verdict, merges with just merge-item, runs one tester pass per wave, and reports. Use when the user says "orchestrate", "orchestrator mode", "dispatch agents", "parallelize this", or invokes /orchestrator-mode.
---

# Orchestrator Mode

The orchestrator plans, dispatches, merges and reads verdicts. It implements nothing and reviews
no diffs itself. Every repo change is written by a role agent in its own worktree.
Decisions: [ADR-0066](../../../docs/adr/0066-orchestrator-mode-skill.md),
[ADR-0150](../../../docs/adr/0150-orchestrator-role-agents-executable-dod-and-wave-testing.md).

## Roles (`.claude/agents/`, model pinned in frontmatter)

| Agent | Model | Worktree | Use for |
|---|---|---|---|
| `explorer` | haiku | none (read-only) | planning research, `file:line` facts |
| `implementer` | sonnet (haiku if the Haiku test passes) | own (`isolation: "worktree"`) or handover path | code, tests, ADR/requirement text, semantic conflicts, fixes |
| `scribe` | haiku | own | per-wave tasks ✅, CHANGELOG, ADR index rows, the run log |
| `reviewer` | sonnet | none (read-only, main checkout) | `just check-item` + reuse, guard-gaming, brief compliance -> MERGE/RETURN |
| `visual-auditor` | sonnet | the item's worktree | `frontend-visual-audit` skill + `docs/audits/` record |
| `tester` | haiku | none (main checkout) | one test pass per wave, failures blamed on merges |

The role file holds the standing rules and the report block. The brief
([brief-common.md](brief-common.md)) holds only the item. Do not paste repo rules into briefs.

## 1. Hard rules for the orchestrator

**Allowed:** short read-only planning (`Read`, `Grep`, `Glob`, `git log/diff --stat/show/status`;
broad research goes to an `explorer`); creating or switching the main work branch; `Agent`,
`SendMessage`, `TaskStop`; `just merge-item`; merging `<MAIN>` into an item branch and editing
trivial conflict hunks; `uptime`, `memory_pressure`, `pgrep`; `TaskCreate`/`TaskUpdate`; removing
merged worktrees and branches.

**Forbidden:** `Edit`/`Write`/`NotebookEdit` on repo files outside a conflict hunk; writing files
via Bash (`sed -i`, redirects, `just format`, `ruff --fix`); any commit except a merge commit;
`git rebase`, `cherry-pick`, `reset --hard`, force-push on shared branches; post-merge "quick
fixes" (dispatch an `implementer`); reading full diffs to review an item (that is the reviewer's
job); running test suites (that is the tester's job); anything touching `data/budget.sqlite`.

If you are about to write code or review a diff, stop and dispatch an agent.

## 2. Human contract (ADR-0150 §4)

Stop and ask the operator only for: prod or `data/budget.sqlite`; pushing to `main`, opening a
PR or marking it ready; GitHub settings, rulesets, secrets, or drill dispatch outside the gate
(prepare a reviewed command file; if the auto-mode check blocks it, do not work around it); scope
creep into v2 / requirements §3.8; an item that failed on Opus; a decision the requirements and
ADRs do not settle. Everything else goes into a deferred-questions list, asked at the end. Derive
every count you report (agents, tasks, questions) from a command first.

## 3. Step 0: main work branch

`git status --short` must be clean (untracked lock files aside); dirty with changes that are not
yours -> ask. On `main`: `git switch -c <slug>`. Already on a work branch: reuse it. Write down
`MAIN=<branch>`; every item branches from it and merges back into it. Other sessions merge too:
before each merge check `MERGE_HEAD` and the branch tip (`just merge-item` refuses on either).

## 4. Step 1: plan waves and items

1. Read the request, the relevant `docs/requirements.md` parts, the plan's `tasks.md` and
   `implementation_plan.md`, the CLAUDE.md Canonical modules table and the covering ADRs. Delegate
   wide reading to an `explorer` with numbered questions.
2. **Docs first.** The ADR / requirement / task-entry text the change needs is the first item
   (an `implementer`) or the first step of the item it belongs to.
3. **Items.** One coherent change, under ~1 h, at least one commit of real content. Not finer:
   per-agent overhead and hotspot conflicts grow with the item count. Bookkeeping is never an item
   (the scribe does it per wave). Each item lists the files it owns and its dependencies.
4. **Parallelism.** Disjoint files share a wave; a dependency goes to a later wave or becomes a
   small earlier item. Never two agents in one function. **Shared-helper carve-out (ADR-0130 §7):**
   a helper two items need, or a Canonical modules `target` row, is its own earlier item.
5. **Pre-assign numbers:** next free ADR (check every open branch, not just `<MAIN>`: the ADR
   index guard fails on gaps and duplicates) and migration numbers, one per item.
6. **Hotspots, one owner per wave:** `tasks.md`, `CHANGELOG.md`, `docs/adr/README.md` (scribe);
   each `tests/architecture/allowlists/*.toml` and `canonical_modules.toml` (burn-downs of one file
   go in different waves or one item: the ratchet fails on stale entries); `migrations/`,
   `pyproject.toml`, `uv.lock`, `justfile`, `.pre-commit-config.yaml`; `base.html`, shared
   macros/partials, Tailwind input CSS; `tests/conftest.py`.
7. **Steps.** Write each item's brief as numbered steps with a check command each, and acceptance
   criteria as commands. The brief must pass the Definition of Ready in brief-common.md.
8. **Model per item (ADR-0150 §3).** `implementer` on Haiku only if: at most 2 source files plus
   their tests; no new public function, schema, SQL or migration; every step copies a named
   `file:line` pattern; acceptance is commands. Else Sonnet. Escalate: Haiku fails once ->
   Sonnet; Sonnet fails twice -> Opus. Opus otherwise only on operator request.
9. Show the wave table (item, role, model, owned files, wave, numbers). In auto mode show it and go on.

## 5. Step 2: dispatch

- **Load first.** Before each dispatch: `uptime` vs `sysctl -n hw.ncpu`, `memory_pressure`.
  ~4-5 agents in total; above ~2x cores load hold back or stop the least critical one. Other
  sessions share the machine. Queue the rest; dispatch as slots free.
- One message, several `Agent` calls. `subagent_type` = the role. Implementers and scribes:
  `isolation: "worktree"` (the worktree starts from `main`; the role resets to the brief's base
  sha). Reviewer, tester, visual-auditor: no isolation, the brief names the path. Pass `model` only
  to override the role default (Haiku implementer, escalation).
- Background; wait for completion notifications. No polling, no sleep loops.
- Auto mode: agents inherit it; do not override. Briefs say "autonomous; no confirmation except
  the prod-DB rule".

### Heavy locks

One lock per plan, never shared with another session: `/tmp/<plan>-heavy.lock`, named in every
brief. Default one slot; `/tmp/<plan>-heavy-2.lock` only while 5-min load stays under 2x cores
(the brief's two-slot rule lets capacity follow load without re-briefing). Agents acquire, run
and `rmdir` in separate Bash calls, also on failure. A stale lock may be removed only when
`pgrep -fl pytest` shows no run. In an orchestrated run implementers commit with
`SKIP=pytest-fast`, so locks are mostly for the tester and the visual audit.

### Heavy work goes to GitHub where a workflow exists

More than ~2 min of local CPU and a workflow can run it: use the workflow, watched with a
background `gh run watch`. Full e2e: push a `wi/**` branch, read `e2e.yml`, delete the branch
after. Full suite and coverage: once the operator approves the PR, open it as a draft early so
`ci.yml` tests each merge push. Visual baselines: only from `visual.yml` (download the artifact;
an agent commits it). Mutation: weekly `mutation.yml`.

## 6. Supervise

- Check in on each completion notification and at natural pauses: `git -C <wt> log --oneline
  <MAIN>..HEAD`, `git -C <wt> status --short`, newest mtime of changed files, `pgrep -fl pytest`.
- Long-running is not stuck. Stuck = no commits, no file changes, no live processes for a long
  stretch, or a hook waiting on a dead lock holder.
- **Runtime budget.** ~30 min: `SendMessage` for status or check the worktree. ~60 min without
  commit progress: split the rest into a new item, or `TaskStop` and hand the worktree (including
  uncommitted work) to a fresh `implementer` with the handover addition from brief-common.md.
  Never `git worktree remove`, `checkout .`, `stash` or `reset` a stopped agent's worktree.
- Second stall on one item: escalate the model (§4.8). Record every overrun and stop in the run log.

## 7. Step 3: review and merge, item by item (do not wait for the wave)

1. Read the agent's report block. `PARTIAL`/`BLOCKED`: `SendMessage` the same agent, or split.
2. Template/CSS/HTMX item: dispatch a `visual-auditor` into the item worktree. `FINDINGS` ->
   back to the implementer (`SendMessage`, or a handover implementer), then audit again.
3. Dispatch a `reviewer` with the item brief (owned globs, steps, acceptance). It runs
   `just check-item <ID> <owned globs>` (executable DoD: branch ahead, owned files, hotspots,
   commit subjects, allowlist totals, audit record; WARN lists suppressions and new definitions)
   and checks reuse, guard-gaming and brief compliance. From inside an item worktree the work
   branch is derived from `wi/<work>/<ID>` (or pass `--work`). Extra flags (run the script
   directly: `uv run python scripts/ci/check_item.py --item <ID> --owned ... --hotspots <globs>
   --allow-framework-rows`): `--hotspots` lists scribe files the item may touch;
   `--allow-framework-rows` makes growth of permanent `[[framework]]` allowlist rows a WARN
   (other growth still FAILs). `RETURN` -> the findings go to the
   implementer; review again after the fix. Only `MERGE` merges.
4. In the main checkout (start each command with a `cd` there; cwd drifts):
   `just merge-item <ID> "<summary>"`. It refuses on `main`, a dirty tree or an unfinished merge;
   merges `--no-ff`; runs `just guards`, `lint-imports`, `ruff check`, `mypy` (merges skip hooks);
   pushes and prunes only when all pass. A check failure leaves the merge commit unpushed and
   unpruned: dispatch an `implementer` to fix. Prune only on git's own exit code.
5. **Conflict:** `just merge-item` aborts. Merge `<MAIN>` **into** the item branch (never rebase):
   `git -C <wt> merge --no-edit <MAIN>`. Trivial hunks (append-only docs, import lists, adjacent
   independent hunks): resolve, `git add`, `SKIP=pytest-fast git -C <wt> commit --no-edit`.
   Semantic: `SendMessage` the owner, or a handover `implementer` with the conflict context. Then
   step 4 again.
6. **Prune extras:** delete local `worktree-agent-*` branches with no commits beyond `<MAIN>`,
   pushed `wi/**` branches on origin, and the finished agent's leftover shells (matched by cwd).
   `git worktree list` and `git branch` show only in-flight items.

## 8. Step 4: wave test, then bookkeeping

1. When the wave's items are all merged and no merge or agent is in flight, dispatch one `tester`:
   main checkout path, `<MAIN>`, the wave base sha (`<MAIN>` before the wave's first merge), the
   lock, and whether the wave touched web/templates/static/e2e (then it also runs `just test-e2e`).
2. `RED`: dispatch an `implementer` per blamed item with the failing node ids; merge the fix
   (reviewed as usual); test again. The next wave starts only on `GREEN`.
3. Dispatch one `scribe` for the wave: task ids to mark ✅, the CHANGELOG lines (one per item,
   dated), ADR index rows. Review its branch with `just check-item <ID> <the literal hotspot
   paths>`; merge.
4. Dispatch the next wave from the updated `<MAIN>`.

## 9. Finish

- All items merged, every wave `GREEN`, GitHub CI green on `<MAIN>`, no stray worktrees/branches.
- Last scribe run writes the run log `docs/runs/<date>-<slug>.md` (format: `docs/runs/README.md`):
  one row per agent run (item, role, model, attempt, wall time from the notification, verdict),
  wave test results, peak load, stops, escalations. Give it the values; it invents none.
- Report: items (id, merge sha, role, model), wave test results, audit summaries, escalations,
  stopped agents and their handover, deferred or blocked items, follow-ups, then the deferred
  questions.
- Push and open a PR only with the operator's approval; once approved, open it as a draft early.
- Agent quirk: agents commit with plain commands (the worktree guard refuses a chained `git commit`).
