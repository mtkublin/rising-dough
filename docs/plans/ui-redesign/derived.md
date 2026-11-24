# Sourdough Redesign — Derived Screens, Decisions and Deviations

> ADR-0107 §1 and §7. Filled in at T-UR00 (decisions), then by each surface task (derived screens and deviations).

## Open design questions (T-UR00)

| # | Question | Source | Decision | Date |
|---|---|---|---|---|
| 1 | Visible entry point for bulk selection, or keep the hidden checkbox column (Tab / `x`)? | handoff README §6.7 | As delivered: hidden checkbox column (Tab / `x`), no visible entry point (operator) | 2026-11-22 |
| 2 | Inline promote row variant, or the promote dialog only? | handoff README §6 "no board" | Dialog only; inline routes removed (ADR-0134 §5) | 2026-11-21 |
| 3 | `g o` (board) or `g t` for Today? | handoff README §5 | `g t`; handoff corrected by overlay rows, app templates use `g t` (operator; ADR-0147 §5) | 2026-11-22 |

## Parity gaps (from `../ui-test-harness/parity.md`, T-UT06)

> **Resolved 2026-11-21.** The designer answered all 16 gaps ([designer-change-request.md](designer-change-request.md)); the operator decided the product questions ([ADR-0134](../../adr/0134-redesign-scope-decisions-from-the-designer-change-request.md)). The Edit user follow-up was answered too (ST17, kept).

| Feature / screen | Status | Decision | Date |
|---|---|---|---|
| SH13 Export | board now exists | `export` menu beside Ledger tabs, kept on phone (ADR-0134 §6; T-UR28) | 2026-11-21 |
| TD10 Net-worth card | board exists | parity row was wrong; per-account list dropped by the designer | 2026-11-21 |
| L11 Recurring strip | dropped | covered by the Recurring hero | 2026-11-21 |
| L18 Credit-limit hint | board now exists | line under account, pink warning, save allowed | 2026-11-21 |
| L23b Inline promote | dropped | dialog only; remove inline routes (T-UR24) | 2026-11-21 |
| ST10, ST15, ST18, ST19 | boards now exist | forced change, add user, reset, delete (ADR-0134 §10; T-UR20) | 2026-11-21 |
| SH12 Theme switch | app change | redesign release, default system (T-UR27) | 2026-11-21 |
| AU07 First-run | app change | `/setup` with one-time token (T-UR21, T-UR22) | 2026-11-21 |
| AU08, AU09, ST16 Invites | app change | invites beside direct add; email behind a switch after cost check (T-UR18..T-UR20) | 2026-11-21 |
| AU14 Offline | app change, partly deferred | save-failure path in release; service worker deferred (T-UR25, T-UR26) | 2026-11-21 |
| AC07 Account delete | app change | refuse while referenced (T-UR23) | 2026-11-21 |
| ST17 Edit user | board now exists | kept: name + member/admin, email read-only; first row-menu item; own row has no menu (ADR-0134 §11; T-UR20) | 2026-11-21 |

## Derived screens

| Screen | Surface task | Built from | Notes |
|---|---|---|---|
| _…_ | | | |

## Deviations from the handoff

| Where | Deviation | Reason | Task |
|---|---|---|---|
| _…_ | | | |

## Tolerance exceptions

> Default is the strict visual tolerance: 0.1% differing pixels and the cluster cap `MAX_DIFF_CLUSTER_PX` (ADR-0106 amendment 2026-11-22, ADR-0147 §2). A surface may use a looser value only with a row here: reason plus operator sign-off, naming which limit is loosened. Data mismatches never justify an exception; they are overlay rows (below).

| Surface | Ratio / cluster cap | Reason | Operator sign-off | Task |
|---|---|---|---|---|
| _…_ | | | | |

## Handoff data overlay

> ADR-0147 §3–§4. Rows live in `tests/visual/handoff_overlay.toml` (T-UR00b); this section summarises why each group of rows exists. Text and value attributes only; the vendored handoff is never edited.

| Pages | What is corrected | Reason | Task |
|---|---|---|---|
| all pages with the nav and shortcuts dialog | `g o` → `g t` (`aria-keyshortcuts`, key labels) | operator decision, question 3 | T-UR00b |
| `overlays/delete-account*` | "Investments E" → an account in the seed | not in the handoff's account list (handoff README §6 item 17) | T-UR00b |

HTMX error flashes render the old partial's markup inside the new regions until T-UR15 (T-UR02, UR02b).
