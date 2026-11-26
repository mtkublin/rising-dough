# Item brief template (ADR-0150 §3, §4)

The role's standing rules live in its agent file (`.claude/agents/<role>.md`): branch setup,
repo rules, testing, CPU, locks, runtime budget, the report block. The brief carries only what
is specific to the item. Fill every `<...>`. A brief with an empty field fails the Definition of
Ready: do not dispatch it; finish planning or send an `explorer` first.

## Definition of Ready (all must hold before dispatch)

- [ ] Goal in one line, and the task id(s) it implements.
- [ ] Owned files (exact paths or narrow globs) and the files it must not touch.
- [ ] Pre-assigned ADR / migration numbers, or `none`.
- [ ] Numbered steps, each naming its file and function and a check command with the expected result.
- [ ] Acceptance criteria written as commands (single test files or node ids, `rg` expectations,
      `just check-item`). No suites, no `tests/e2e` directory, no `just test*`: the guard denies
      them to the implementer and the reviewer. E2e evidence is the `e2e.yml` run on the pushed
      item branch.
- [ ] Estimate in minutes (at most 60). A frontend item: one page, or at most two dialogs.
- [ ] Frontend item: the audit expectations (routes, the failing save per form and its visible
      error, states to seed), so the implementer builds to what the auditor checks.
- [ ] Base sha, `<MAIN>`, heavy-lock name, role and model (Haiku test passed, if Haiku).
- [ ] Hotspot files (`tasks.md`, `CHANGELOG.md`, ADR index) left to the scribe unless listed as owned.
- [ ] Implementer briefs: the pre-push checklist below is in the brief, in full or by reference.
- [ ] Reviewer briefs: name the CI run to read (`gh run list --branch wi/<MAIN>/<ID>`, the run on the
      item's sha) and the e2e job in it. Reviewers cannot run tests here (the guard), so CI is their evidence.

## Pre-push checklist (every implementer brief)

Source: the ui-sourdough run, where CI found these after merges ([ADR-0150 amendment 2026-11-26](../../../docs/adr/0150-orchestrator-role-agents-executable-dod-and-wave-testing.md), §1). Run each step in the item worktree before the final push; report the results in `STEPS`.

- [ ] `uv run ruff check src tests` and `uv run ruff format --check src tests` pass (CI failed on import order and format after merges).
- [ ] `npm ci --ignore-scripts` first, then `SKIP=pytest-fast uv run pre-commit run --all-files`. No hook is skipped except `pytest-fast`; `--no-verify` is banned.
- [ ] `just guards`, `uv run lint-imports` and `uv run mypy` pass.
- [ ] Routes changed: `uv run python -m tests.contract.routes_md` and commit the regenerated `tests/contract/routes.md`.
- [ ] Routes or controls changed: update `tests/e2e/crawl_inventory.json` and the classification in `tests/e2e/test_crawl.py` (`NOT_PAGES`) for the new routes.
- [ ] No real-clock expectations: four CI jobs run the suite under shifted frozen clocks. Use the clock pattern the nearby tests use (`rg -n "frozen|clock" tests/<area>`), and seed dates inside the window the test checks.
- [ ] Strings you change: `grep` `tests/` (e2e, `ui_map`, visual) for the old text and update every hit. A 422 that now renders differently: tests assert the rendered field error, not the raw field key.
- [ ] Single test files only (`uv run pytest tests/<path>.py -p no:xdist`). No directory runs, no suites, no `just test*`, no `2>&1`, pipes or `&&` chains before pytest (the guard reads them as directory runs).
- [ ] Push the `wi/<MAIN>/<ID>` branch. `e2e.yml` runs on the push; the reviewer reads that run on your sha. Do not wait for it in the foreground.
- [ ] Never push with a hook skipped. If a hook fails, fix the cause and commit again.

## Template

```text
Role: <implementer | scribe | visual-auditor | tester | reviewer | explorer>. Your agent file has the standing rules; follow it.
Item <ID>: <one-line goal>. Task(s): <T-...> in docs/plans/<plan>/tasks.md.
MAIN=<work branch>  BASE=<sha>  LOCK=/tmp/<plan>-heavy.lock (second slot /tmp/<plan>-heavy-2.lock only while 5-min load < 2x cores)
Branch name: wi/<MAIN>/<ID>. Worktree: <your isolation worktree | existing path for handover/audit/review>.
Autonomous run: never stop for confirmation except the prod-DB rule.

Spec: <ADR(s) and sections; requirement ids; what was already ruled out>

Owns: <paths/globs>
Must not touch: <paths owned by parallel items, hotspots>
Numbers: ADR-<NNNN> | migration <NNNN> | none

Estimate: <minutes, at most 60>

Steps (do in order; run each check, report its result):
1. <file>::<function>: <change>. Pattern to copy: <path:line>. Check: `<command>` -> <expected>
2. ...

Acceptance (all must pass; the reviewer reruns the single non-e2e files and `rg` checks):
- `<command>` -> <expected>
- e2e: the `e2e.yml` run on the pushed `wi/<MAIN>/<ID>` sha -> success | none (no e2e impact)
- `just check-item <ID> <owned globs>` -> rc=0

Local e2e files you may run (at most 4 runs in total, under the lock): <tests/e2e/test_x.py | none>
Audit expectations (frontend items): <routes; per form the failing save and its visible error; states to seed | none>

Out of scope: <what not to do>
```

## Handover addition (stuck agent or semantic conflict)

```text
Handover: cd <worktree path>; branch wi/<MAIN>/<ID>. Do not create a worktree, reset, stash or checkout.
Done so far: <git log --oneline MAIN..HEAD>; <git diff --stat>; <git status --short>
Remains: <steps n..m> | Conflict: merge MAIN into the branch and resolve <files>, keeping both intents: <what each side wanted>
```
