# Sourdough Redesign

> **What**: replace the whole presentation layer with the designer's handoff "Rising Dough · Sourdough redesign" (`docs/design/rising-dough-frontend/`), test-first, with no reuse of existing templates, CSS or presentational JS.
> **Decision**: [ADR-0107](../../adr/0107-sourdough-redesign-from-designer-handoff.md). Precondition: [ADR-0106](../../adr/0106-ui-behaviour-test-harness.md) and [`../ui-test-harness/`](../ui-test-harness/README.md). Requirements: [`docs/requirements.md` §10](../../requirements.md#10-sourdough-redesign-added-2026-11-16).
> **Tasks**: [`tasks.md`](tasks.md) (T-UR00…T-UR17, plus T-UR00b). Derived screens and deviations: [`derived.md`](derived.md). Old-file removal ledger: `removal.md` (generated at T-UR00).

## Sequencing

```
v3 ships ─ faster CI ─┬─ quality audit (T-Q01..T-Q18) ── [pre-v4-P3] remediation ─┐
                      └─ UI test harness (T-UT01..T-UT12) ────────────────────────┴─ redesign (T-UR00..T-UR17) ─ v4 Phase 2
                                                    v4 Phase 1 (crypto core, no UI) may run alongside the redesign ─┘
```

- Starts when the harness exit gate (T-UT12) and the `[pre-v4-P3]` quality-audit remediation are ✅ (ADR-0107 §9).
- Must be released before v4 Phase 2 starts, because v4 Phase 2 is the first v4 phase that adds screens.

## Phases

| Phase | Tasks | What | Gate |
|---|---|---|---|
| 0 — Entry | T-UR00, T-UR00b | preconditions, open design questions, work branch | operator sign-off |
| 1 — Foundation | T-UR01..T-UR04 | assets and toolchain, base layout and shell, server-side value helpers, shared fragments and dialog plumbing | shell UI map on new markup; crawler green on migrated + unmigrated pages |
| 2 — Surfaces | T-UR05..T-UR14 | one item per surface, in parallel | per-surface definition of done (below) |
| 3 — Cutover | T-UR15..T-UR17 | delete old frontend, full validation, release | release checklist; `drill-gate` green |

## Per-surface loop (test-first)

1. **Point the UI map at the handoff.** Rewrite `tests/ui_map/<surface>.py` against the handoff's markup. Confirm it with `--target=mockup` (T-UT09): the journeys pass on the static handoff.
2. **Red.** Run contract, journey, crawler and visual tests against the app. The surface's tests fail; nothing else does. The visual tests fail against the handoff references (generated in the pinned Playwright container, fixture seeded with the handoff's own data, T-UR00b); that red run is the starting point.
3. **Green.** Build `pages/<surface>/…` and `fragments/…` from the handoff's markup, wire HTMX per ADR-0107 §6, adapt the router context. Contract tests stay green unchanged throughout.
4. **Delete the stand-ins** for that surface: no `stand-in.js`, `data-demo*`, `action="#"`. **Delete the surface's old files** listed in `removal.md`.
5. **Verify.** Pixel parity: visual diff against the handoff references at 1440 / 1024 / 375, light and dark, at the strict default tolerance (0.1%). A looser tolerance needs a `derived.md` "Tolerance exceptions" row with the reason and operator sign-off; `frontend-visual-audit` on the surface's routes; axe at 375 and 1440 in both themes.
6. **Record** any deviation or derived screen in `derived.md`.

## Per-surface definition of done

- UI-map module points only at new markup; no old-markup names left for the surface.
- Contract tests unchanged and green; journeys and crawler green for the surface at 375 and 1440.
- Visual diff within the strict default tolerance (0.1%), or within the surface's `derived.md` tolerance exception (reason + operator sign-off), both themes. References come from the pinned container and the fixture data equals the handoff data (ADR-0106 amendment 2026-11-22).
- `frontend-visual-audit` clean (no `horizontalScroll`, `overflowingElements`, `duplicateIds`, `consoleErrors`, `requestFailures`) at 1440 / 1024 / 375.
- axe: 0 serious or critical (handoff's two decorative exclusions only).
- No inline `style=""`; no stand-in attributes; no old CSS or old template included.
- The surface's old files and the Python they alone used are deleted, and their `removal.md` rows say `deleted` (T-UR15 sweeps what shared surfaces still needed).
- Scoped tests green in the item worktree; PR CI runs the full suite (ADR-0120).

## Guardrails

- **Presentation from the handoff only** (ADR-0107 §1–§2). Old templates and CSS may be read to understand behaviour, never copied.
- **Behaviour is pinned by the harness.** If a contract test needs to change, stop: that is a behaviour change and needs a requirement or ADR first.
- **Parity, not features.** Handoff-only screens are wired only after a requirement exists (`derived.md` records the decision).
- **No mixed chrome in prod.** Release once, after T-UR15 (ADR-0107 §8). Prod only via GitHub Actions from `main` (ADR-0099).
- **Reuse check** (ADR-0130, CLAUDE.md "Canonical modules"): search before writing a helper, reuse the canonical module, report `Searched / Reused / New helper` in every surface handoff; new templates start at zero on the template-logic guards (no allowlist entries).
- **Prod DB hands off.** All work on scratch DBs or `data/demo.sqlite`.
- **Orchestrator mode** (ADR-0066) for Phase 2, one worktree and branch per surface; merge `ui/sourdough` into the item branch to resolve conflicts, never rebase. Check `MERGE_HEAD` and the branch tip before every merge (other sessions merge too).
- **Long-lived branch hygiene.** Merge `v3` (later `main`) into `ui/sourdough` at least at the end of every phase.

## Budgets (from the handoff and `~/.claude/rules/web/performance.md`)

| What | Budget | Handoff at delivery |
|---|---|---|
| CSS, gzipped, all files | ≤ 50 kB | 23 kB |
| JS, gzipped, all files (htmx and kept behaviour JS included) | ≤ 30 kB + htmx | 11 kB |
| Fonts | ≤ 250 kB | 60 kB |
| LCP / CLS / INP on `/today`, `/ledger`, `/plan` | < 2.5 s / < 0.1 / < 200 ms | — |
