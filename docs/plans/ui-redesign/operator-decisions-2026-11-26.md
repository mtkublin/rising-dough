# Operator decisions, 2026-11-26 (ui/sourdough)

Answered by the operator in an interactive walk-through of [operator-options-2026-11-26.md](operator-options-2026-11-26.md) and the open questions of the run logs ([2026-11-24](../../runs/2026-11-24-ui-sourdough.md), [2026-11-26](../../runs/2026-11-26-handoff-reference-comparison.md)). Binding for the rest of the run. ADR amendments land with the items that apply them (docs first). The patches named below are in [operator-options/](operator-options/); they were measured on `d4c06a8`, so re-measure when applying.

## Handoff comparison decisions (T-UR00b)

| Id | Decision | Patch / work | Effect on the reference pages |
|---|---|---|---|
| D1 | **a + b + c(i)**: `placeholder` becomes an overlay attribute (ADR-0147 §4 amendment); the hero amount keeps its focused underline while the picker is open, shipped as an **app stylesheet rule, not an edit of the vendored `dialog.css`** (Q8 stays: vendored CSS byte-identical); seed modifier `picker-handoff-list` archives the four extra categories on the two picker pages (small seed-engine "archive after seeding"), count rows 21 → 20 on those pages. | `D1-a-placeholder.patch`, D1-b rule moved to an app sheet, D1-c(i) new | `category-picker`, `category-picker--no-match` green |
| D2 | **b**: six `aria-label` overlay rows for the budget-row bars. App rounding unchanged (left = 100 − floored spent). Not urgent. | `D2-b-bar-label-rows.patch` | `plan/budget` stays green |
| D3 | **a**: overlay rows rewrite the `accounts--empty` hero and caption to the empty values. App unchanged. | `D3-a-overlay-rows.patch` (keep its `exclude` line, D6-A is not applied) | `accounts--empty` green |
| D4 | **a: keep ADR-0105.** An overdue unpaid planned item stays committed and lowers "left". The 13 seed-value overlay rows stay; the ADR-0151 afford figure stays replaced by the seed figure. | none | unchanged (green) |
| D5 | **b: carry typed values across new-entry tabs** (amount, category, account, note; tab-only fields such as due date and cadence are not carried). `hx-include` on the tab links with the CSRF token excluded; `form_responses.open_new_entry` reads them as `posted`. Then finish QFIX10's regression test on the new behaviour; QFIX11/12 diagnostics may be deleted once the lost-note scenario passes without `fill_stable` retries. | `D5-b-carry-typed-values.patch` | none (harness never switches tabs) |
| D6 | **B: keep ADR-0089.** "After planned" keeps counting overdue and due-today unpaid items (consistent with D4-a). | none | 8 accounts pages stay different at 1440L / 1024D: **intended difference** |
| D7 | **Keep the current-password field** on the forced change page. No D7-a template, no D7-b service change; ADR-0074 unchanged. | none | `auth_force-password`, `--error` stay different: **intended difference** |
| D8-L | **Keep the credit limit required** for every liability. | none | `edit-account--liability` stays different: **intended difference** |
| D8-R | **Full handoff reconcile dialog**: remove `record as`, the snapshot checkbox and `preview`; the hero updates live as the balance is typed; `record as` is always the Reconciliation category; a balance snapshot is always saved; seed snapshots per the handoff. Requirements and the reconcile ADR first (service behaviour changes). | `D8-R-reconcile-extras-out.patch` as the template start, plus live hero, service and seed work | `reconcile`, `reconcile--liability` target green (the liability help line may remain; re-measure) |
| D8-E | **Overlay op that inserts the 11th account row** into the `delete-account` handoff backdrop (ADR-0147 §4 amendment: the overlay may insert a row copied from an existing row's markup, text changed only). | new | `delete-account` green |
| D8-T | `as of` stays out (no migration). | none | none |
| D9 | **A: one `#flash-region`** (polite); the error flash keeps `role="alert"`. Also resolves the logged double `role=alert` follow-up. | `D9-A-merge-flash-region.patch` + the listed test selector edits | `today--flash` green |
| D10 | **A: test-only token port** in `tests/visual/frozen_server.py` (board sample for the one-time password request, CSPRNG for everything else). Add a guard test that production wiring never uses the fixed source. Production generator unchanged (ADR-0061 §8). | `D10-A-token-port.patch` | `one-time-password` green |
| D11 | **S: the edit dialog snaps to the nearest swatch** (preview and ring); boards keep the stored colour. A save without touching the colour stores the swatch colour: record this silent recolour in the ADR. | `D11-S-snap-to-nearest-swatch.patch` | `edit-category` green |

### Reds outside D1-D11

- Fix the harness channel mismatch (RGBA vs RGB on equal sizes, `handoff._decode` / `compare`).
- Investigate and fix `new-entry--repeats-fixed` (dialog offset about 70 px at 1024D and 375L) and `new-entry--repeats-formula` (small cluster on every shard) as app or recipe bugs.
- `new-account--error` focus ring after a 422 is an **intended difference** (the app focuses the first invalid field, a11y).

### Intended differences and the gate

- New table "Intended differences" in [derived.md](derived.md): page, shard(s), decision id, operator sign-off (this file). `tests/visual/test_reference.py` marks those pages `xfail(strict=True)`, so a new or vanished difference still shows. ADR-0147 amendment. This is not a tolerance exception (those stay for non-data reasons only).
- The reference comparison **stays advisory** (`continue-on-error`, not in `visual-gate`) for now.
- **Follow-up (operator):** once the UI state is accepted, the accepted app screenshots are recorded and become the reference, so the comparison is green with no overlay workarounds or xfails; only then does it become a required check (ruleset change by the operator). Needs its own ADR (supersedes the handoff-as-reference parts of ADR-0147 for regression purposes).

## Other decisions

- **Amount inputs**: accept grouped digits on input (thousands separators comma, space and no-break space stripped before the `.` decimal) in `domain/money.parse_amount_str`; inputs keep rendering the bare value. Requirements first.
- **T-UR42 (FX rates table, Q20) and T-UR22 (drill: bootstrap admin off, setup token in the workflow output)**: both land **before** the redesign release (T-UR17).
- **Logged bugs** ("Follow-ups logged 2026-11-25" in [tasks.md](tasks.md)): **all fixed before the release**: dialog 500s on bad `day_of_month`, year, opening balance and duplicate category name; bad values saved (`day_of_month=45`, empty or `abc` budget override); `/today` promote toast lost to `HX-Refresh`; clipped actions column at 1024 px; removed routes answer 405 instead of 404; bare `account not found` body; service `ValidationError` flash without `HX-Reswap: none`; palette / tab-bar `+` and `n` leaving `/ledger`.

## Operator steps still open (unchanged)

- Apply the two `ci.yml` edits ([q2-ci-checkout.md](q2-ci-checkout.md), [q-ci-tailwind-removal.md](q-ci-tailwind-removal.md)).
- Add the `prod` secret `SETUP_TOKEN_HASH` and run the approved apply ([q10-operator-steps.md](q10-operator-steps.md)); checked 2026-11-26: the secret is not set.
- Explore drill click-through, mark PR #54 ready, merge (human contract, Q11).
