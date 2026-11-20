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

## Points to check

1. The Canonical modules table lists 11 rows (prevention S1 says 15, its list has ~14 concepts); I merged "request-param parsing, HTMX events" and left out transit validation, balance as-of, category selection, template view-model values (each `target`). Add them when `canonical_modules.toml` lands, since the table must equal the toml (drift guard).
2. `just guards` and `just mutate*` are listed but depend on T-Q15a/b landing; `test-fast`, `demo-build`, `set-password` exist today.
3. Rule table cites guard ids (`G2`, `G4`, `G6`, `G8`) with a pointer to `prevention.md` §2 rather than file names, because the guard files do not exist yet. Replace with file names after T-Q15a (R3 asks for rule, guard file, error text).
4. The pure-layer definition permits `logging` in services (per the task brief); ADR-0130 §5 and the open question Q1 in the inventory (E07) leave this undecided in text.
5. The CPU lock path `/tmp/qa-audit-heavy.lock` is named after this audit; rename if the lock should be general.
6. No edit to the Releases section (R8) or the user-level `~/.claude/rules` (out of scope, ADR-0130 §7).
