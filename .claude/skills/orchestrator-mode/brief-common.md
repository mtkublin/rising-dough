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
