# Sourdough Redesign

> **What**: replace the whole presentation layer with the designer's handoff "Rising Dough · Sourdough redesign" (`docs/design/rising-dough-frontend/`), test-first, with no reuse of existing templates, CSS or presentational JS.
> **Decision**: [ADR-0107](../../adr/0107-sourdough-redesign-from-designer-handoff.md). Precondition: [ADR-0106](../../adr/0106-ui-behaviour-test-harness.md) and [`../ui-test-harness/`](../ui-test-harness/README.md). Requirements: [`docs/requirements.md` §10](../../requirements.md#10-sourdough-redesign-added-2026-11-16).
> **Tasks**: [`tasks.md`](tasks.md) (Phase P T-UR29…T-UR35, then T-UR00…T-UR28, plus T-UR00b). Backend preconditions: [ADR-0148](../../adr/0148-redesign-backend-preconditions-released-first.md). Visual parity method: [ADR-0147](../../adr/0147-handoff-parity-ci-rendered-references-and-data-overlay.md). Derived screens and deviations: [`derived.md`](derived.md). Old-file removal ledger: `removal.md` (generated at T-UR00).

## Sequencing

```
v3 ships ─ faster CI ─┬─ quality audit (T-Q01..T-Q18) ── [pre-v4-P3] remediation ─┐
                      └─ UI test harness (T-UT01..T-UT12) ────────────────────────┴─ preconditions release (T-UR29..T-UR35) ─ redesign (T-UR00..T-UR28) ─ v4 Phase 2
                                                    v4 Phase 1 (crypto core, no UI) may run alongside the redesign ─┘
```

- Starts when the harness exit gate (T-UT12) and the `[pre-v4-P3]` quality-audit remediation are ✅ (ADR-0107 §9), and after the backend precondition release (Phase P) is live in prod (ADR-0148). The migration itself is frontend work only.
- Must be released before v4 Phase 2 starts, because v4 Phase 2 is the first v4 phase that adds screens.

## Phases

| Phase | Tasks | What | Gate |
|---|---|---|---|
| P — Preconditions | T-UR29..T-UR35 | backend only: user edit guards, invite data layer and email port, setup-token service, account delete rule, value inventory and data gaps; own PR and release | released to prod; smoke green |
| 0 — Entry | T-UR00, T-UR00b | preconditions, open design questions, work branch | operator sign-off |
| 1 — Foundation | T-UR01..T-UR04 | assets and toolchain, base layout and shell, server-side value helpers, shared fragments and dialog plumbing | shell UI map on new markup; crawler green on migrated + unmigrated pages |
| 2 — Surfaces | T-UR05..T-UR14 | one item per surface, in parallel | per-surface definition of done (below) |
| 3 — Cutover | T-UR15..T-UR17 | delete old frontend, full validation, release | release checklist; `drill-gate` green |

## Per-surface loop (test-first)

1. **Point the UI map at the handoff.** Rewrite `tests/ui_map/<surface>.py` against the handoff's markup. Confirm it with `--target=mockup` (T-UT09): the journeys pass on the static handoff.
2. **Red.** Run contract, journey, crawler and visual tests against the app. The surface's tests fail; nothing else does. The visual tests fail against the handoff references (rendered in CI in the pinned Playwright container from the vendored handoff plus the data overlay; app seeded with the handoff's data, T-UR00b, ADR-0147); that red run is the starting point.
3. **Green.** Build `pages/<surface>/…` and `fragments/…` from the handoff's markup, wire HTMX per ADR-0107 §6, adapt the router context. Contract tests stay green unchanged throughout.
4. **Delete the stand-ins** for that surface: no `stand-in.js`, `data-demo*`, `action="#"`. **Delete the surface's old files** listed in `removal.md`.
5. **Verify.** Pixel parity: visual diff against the handoff references at 1440 / 1024 / 375, light and dark, at the strict default tolerance (0.1% of pixels and the cluster cap `MAX_DIFF_CLUSTER_PX`, ADR-0147 §2). A looser tolerance needs a `derived.md` "Tolerance exceptions" row with the reason and operator sign-off; `frontend-visual-audit` on the surface's routes; axe at 375 and 1440 in both themes.
6. **Record** any deviation or derived screen in `derived.md`.

Overlay references (T-UR00b, ADR-0147 amendment 2026-11-25): each handoff overlay page is its surface's full board with one dialog open, so the app side loads the overlay's own base route (derived from the nav and tab `aria-current` in the handoff file, with that page's seed modifiers) and fetches the dialog into `#modal-root`; it never defaults to `/today`. The client-side states with no dialog route (command palette and its filtered and no-match states, shortcuts, period pickers, the six row menus, the category picker) are opened by the real click or key recipe in `tests/visual/handoff_clicks.py`; `override--year-cell` stays unmapped (the app has no inline year-cell editor).

## Per-surface definition of done

- UI-map module points only at new markup; no old-markup names left for the surface.
- Contract tests unchanged and green; journeys and crawler green for the surface at 375 and 1440.
- Visual diff within the strict default tolerance (0.1% and the cluster cap), or within the surface's `derived.md` tolerance exception (reason + operator sign-off), both themes, at 1440 / 1024 / 375, pages and overlays. References are rendered in the CI job from the overlaid handoff and the seed equals the handoff data (ADR-0106 amendment 2026-11-22, ADR-0147). Data mismatches are fixed by overlay rows (text and value attributes only), never by app logic or a looser tolerance.
- `frontend-visual-audit` clean (no `horizontalScroll`, `overflowingElements`, `duplicateIds`, `consoleErrors`, `requestFailures`) at 1440 / 1024 / 375.
- axe: 0 serious or critical (handoff's two decorative exclusions only).
- No inline `style=""`; no stand-in attributes; no old CSS or old template included.
- The surface's old files and the Python they alone used are deleted, and their `removal.md` rows say `deleted` (T-UR15 sweeps what shared surfaces still needed).
- Scoped tests green in the item worktree; PR CI runs the full suite (ADR-0120).

## Guardrails

- **Presentation from the handoff only** (ADR-0107 §1–§2). Old templates and CSS may be read to understand behaviour, never copied.
- **Behaviour is pinned by the harness.** If a contract test needs to change, stop: that is a behaviour change and needs a requirement or ADR first; transport-markup assertions follow ADR-0152.
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
