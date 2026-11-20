# T-Q15c review summary

> For operator review before merge. Implements `prevention.md` §3 steps 9 to 12 and ADR-0130 §7. Gap-analysis rows are from `prevention.md` §1.2 ("CLAUDE.md", "orchestrator-mode", "frontend-visual-audit", "plan handoff rules"); rule ids R1 to R8, S1 from §2.

## Per file

### `CLAUDE.md` (net +38 lines, 141 to about 179)

| Change | Why (gap-analysis row) |
|---|---|
| Stale paths: `docs/tasks.md`, `docs/implementation_plan.md` replaced by `docs/plans/<plan>/...` in Change policy, Where to look, Handoff | CLAUDE.md row "Stale" (G-08, Q-053) |
| Stack line: Tailwind local build, server-rendered SVG, no CDN/Plotly/SPA (ADR-0027, ADR-0123); pre-commit list adds import-linter, stylelint and CI parity | CLAUDE.md row "Stale" |
| Where to look: row pointing at ADR-0130 / requirements §3.3 | missing (e): agents could not tell what is enforced |
| New section **Canonical modules**: concept to owner table, `target` rows labelled "not yet extracted: do not add a new copy", 3-step search rule, report line, registration in `tests/architecture/canonical_modules.toml` | CLAUDE.md missing (a) "no module registry"; S1, R1; Q-002, Q-003, Q-007 to Q-010, Q-036 |
| **Code conventions** rewritten as a rule | enforced-by table: pure-layer definition (domain pure; services no network or clock except injected, `logging` allowed; view models no network), thin web, repository-only SQL and user scoping, single clock, money, immutability, suppressions with reasons, "allowlists only shrink", assertion rule | Missing (b) clock, (c) SQL/user id/template logic/suppressions, (e) advice vs guard; R3, R4, R5; ADR-0130 §1, §4 to §6 |
| Commands: `test-fast`, `guards`, `mutate*`, `demo-build`, `set-password` | CLAUDE.md row "Stale" (commands list) |
| Frontend validation: pointer to the skill's new Step 3b | R6; Q-037, Q-039 |
| Handoff checklist: reuse check, ADRs re-read, "guards green, allowlist counts only went down, no new entry or suppression without amendment, new dependency justified" | missing (d); R2 |

Not touched: prod-DB, Releases and environments, Multi-agent sections (prevention step 9e, R8 G17 pointer, is left to T-Q15 when G17 exists).

### `.claude/skills/orchestrator-mode/SKILL.md`

- Step 1: reads the Canonical modules table; stale `docs/tasks.md` paths fixed. Shared-helper carve-out (two items needing a missing helper: earlier-wave single owner). Hotspots gain `allowlists/*.toml` and `canonical_modules.toml`, one owner per file per wave. Gap (a), (b), (e), (f); R1; ADR-0130 §2, §7.
- Brief template: repo-rules lines for clock, money, user id, templates, suppressions; "Search before you write" block; "No new allowlist entry"; handoff line with ADRs re-read; CPU-budget rules. Gap (a); R1, R2.
- Report-back: `Searched / Reused / New helper` and allowlist entries deleted. Gap (d).
- Merge step 1: checks the report line, allowlist direction, and a **duplication check** (`scripts/ci/new_defs.py <MAIN>` if present, else grep of added `def` lines) with `SendMessage` back to the agent. Gap (c). Falls back to a manual grep because the script is optional in the plan.
- CPU rules learned this session: `PYTEST_WORKERS=2`, one heavy job at a time, shared `mkdir` lock (`/tmp/qa-audit-heavy.lock`), release on failure, retry the load-sensitive e2e test.

### `.claude/skills/frontend-visual-audit/SKILL.md`

- Scope sentence: logic is out of scope **except** printed numbers and the HTMX contract (the skill said "do not use for logic" while CLAUDE.md made it the sole proof). Gap "wrongly scoped"; R6; Q-037, Q-039, Q-070.
- New **Step 3b** checklist with evidence per item: swap targets, forced 404/409/500 visible errors, no arithmetic or `float` in templates, money by currency, rendered number equals service value, duplicate ids and event listeners after swap, scratch DB only. Two new rows in the findings table.
- Stale gotchas replaced: CDN CSS cache (now stale Tailwind build, `just css`), Plotly (now server SVG), `networkidle` (script switched to `domcontentloaded` plus `waitForSelector`).

### Active plan handoff templates (step 12)

- `docs/plans/v4/implementation_plan.md` Handoff shape: Reuse check line and ADRs re-read / no new allowlist line.
- `docs/plans/gamification/README.md`, `docs/plans/ui-redesign/README.md` (no separate handoff template; Guardrails list instead): one Reuse-check guardrail each; ui-redesign adds "new templates start at zero".
- v1 to v3 untouched (closed). `ci-speed` and `ui-test-harness` not touched (no handoff section).

### Bookkeeping

`docs/CHANGELOG.md` one line; `docs/plans/quality-audit/tasks.md` T-Q15 bullet "T-Q15c guidance drafted, pending operator review".

## Update after T-Q15a/b/d merged

- Canonical modules table now has all 16 registry rows with the registry's concept names verbatim (`test_claude_md_table_covers_registry` un-skipped and green); clock row is `exists` (`utc_now()`, `today_local(settings)`).
- The rule table cites real test files and allowlists under `tests/architecture/` (guard ids in parentheses); Releases section gains the G17 pointer (`test_workflow_secrets.py`, `ci_environments.toml`, operator-run `scripts/check_github_settings.py`).
- G15: `guidance_paths.toml` is now empty (11 entries burned to zero). Two last stale references were reworded without a backticked path: the `data/scripts/build_demo_db.py` anonymizer (the file is gitignore-exempt but untracked in worktrees) and the not-yet-existing `new_defs.py` helper in the orchestrator skill.
- ADR-0130 §5 carries the one-line amendment that services may use `logging`.
- `just guards` (tests/architecture, 96 tests) green.

## Points to check

1. The one-transaction rule (G8) has no guard yet; the rule table says so. Add its test name when it lands.
2. `scripts/ci/new_defs.py` does not exist; the orchestrator merge check falls back to a grep. Decide whether to build it.
3. The CPU lock path `/tmp/qa-audit-heavy.lock` is named after this audit; rename if it should be general.
4. `data/scripts/build_demo_db.py` is gitignore-exempt but untracked in this repo state; confirm whether it should be committed.
5. `~/.claude/rules` (user level) remains untouched (ADR-0130 §7).
