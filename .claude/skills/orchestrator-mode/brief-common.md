## Branch setup (do first)
1. Your worktree may start from `main`, which is NOT the base. Run `git reset --hard <MAIN>` now (no work yet); `git log -1` must show the sha the orchestrator names, or later. Then `git branch -m wi/<MAIN>/<ID>`.
2. Work and commit ONLY inside this worktree. Run `just worktree-init` once.

## Goal source
Read your task entry `<ID>` in `docs/plans/<plan>/tasks.md` and every ADR amendment it names; they are the spec. Failing test first, exact values (amounts, audit row, stored sign, second user's rows absent). Mark the task heading done, add a CHANGELOG line, reference the ADR in the commit.

## Repo rules (MANDATORY; read CLAUDE.md)
- `data/budget.sqlite` is PRODUCTION; never touch it (scratch DB or demo copy only).
- Canonical modules table: search before you write, reuse owners, never import another module's `_private` name; report `Searched/Reused/New helper`.
- No new allowlist entry or suppression (unless your task entry explicitly says so). Delete entries you fix (exact ratchet).
- Fix the cause, never the guard. A change that satisfies a guard by syntax only (call-form tricks, renames, wrappers) is rejected at merge. The fix is a real code change, or a `[[permanent]]` row with a reason and an ADR-0130 amendment.
- Template/CSS/HTMX change: MANDATORY `frontend-visual-audit` skill (the skill itself) on affected routes at 1440/1024/375 incl. Step 3b, plus `docs/audits/<date>-<id>.md`.
- New test assertions use `tests/ui_map` / `db_probe`, never raw markup substrings (no-markup guard).
- After every merge of `<MAIN>` into your branch: `just guards`, `uv run lint-imports`, `uv run ruff check src tests`, `uv run mypy src tests` clean (a clean `git merge` runs no hooks). Merge `<MAIN>` before the final commit; resolve keeping both.
- **Tests = pre-commit hooks only (ADR-0120).** Do NOT run `tests/unit` / `tests/integration` / `tests/contract` / `tests/e2e` suites or post-merge reruns by hand. While developing run only the single test file(s) you are writing (`uv run pytest <file> -q --no-cov -p no:xdist`, no lock needed). The commit hook (testmon-affected, or full suite when it must) is the gate. Full e2e, full suite, visual baselines and mutation run on GitHub (see the skill, "Delegate heavy work to GitHub"). Exception: the frontend-visual-audit skill when templates/CSS change.
- **CPU:** env exports do NOT persist between Bash calls. Prefix every commit inline with `PYTEST_WORKERS=2` and use `-F <file>` messages. Direct pytest calls pass 2 workers; never `auto` (it caused load 70-110 on 8 cores). No `just ci`.
- Commit with a plain command (`PYTEST_WORKERS=2 git commit -F <file>`); the worktree guard refuses a chained `git commit`.
- Hooks run on every commit: never pass the hook-skip flag, never set SKIP. Unique commit-message file names; scratch under the session scratchpad in `<id>/`; never run other agents' scripts.
- Heavy lock (the orchestrator names `<plan>` and the open slots in your brief): simple separate Bash calls: try `mkdir /tmp/<plan>-heavy.lock` (SLOT 1); if it fails and a second slot is open and 5-min load < 2x cores try `mkdir /tmp/<plan>-heavy-2.lock` (SLOT 2); else `until mkdir /tmp/<plan>-heavy.lock 2>/dev/null; do sleep 20; done`. Then job/commit, then `rmdir` the lock you got. ALWAYS release it, also when the job or commit fails, and kill any wait loop you started before you report. Never touch other lock files.
- **Runtime budget:** the item is sized for under ~1 h. If you pass ~45 min or are looping (lock waits, merge conflicts, hook retries), commit what is green and report what remains instead of continuing. Do not gold-plate beyond this brief.
- Commit `<type>(<ID>): ...`. Autonomous; no confirmation questions (prod DB is the only exception).

## Report back
branch + sha; what changed (functions/files); tests added with exact values; allowlist entries deleted/added; audit summary if any; hook results; `Searched/Reused/New helper`; anything left undone.
