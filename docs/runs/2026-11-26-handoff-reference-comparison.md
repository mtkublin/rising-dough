# Run 2026-11-26 handoff-reference-comparison

- Work branch: `ui/sourdough`; base `1d48851`; PR: ?
- Request: T-UR00b handoff reference comparison: map every overlay and page, merge per-surface parity items, and report what stays blocked (not green).
- Waves: ?; items: 33 merged, 1 dropped (O2); agent runs: ?

## Items

Role is implementer for every item. Model is sonnet except X1 (haiku). Verdict is the role's status at merge (`MERGE`). Wall times are not recorded.

| item | role | model | merge sha | summary | verdict |
|---|---|---|---|---|---|
| H1 | implementer | sonnet | 0b52f5a | overlays render over their handoff base surface (ADR-0147) | MERGE |
| S1 | implementer | sonnet | fa6c0e1 | seed + Today cap + ledger glyph match the handoff | MERGE |
| H2 | implementer | sonnet | 281812b | page routes, anonymous auth, modifiers, settings tabs | MERGE |
| W1 | implementer | sonnet | 85e8447 | click recipes for client-side overlays | MERGE |
| W2 | implementer | sonnet | 6c18fec | users and invites overlay openers | MERGE |
| X1 | implementer | haiku | badede2 | detect-secrets false positive in mapping test | MERGE |
| E1 | implementer | sonnet | 654c0de | state recipes for error/auth/today state pages | MERGE |
| F1 | implementer | sonnet | 16304ef | plan surface handoff parity (budget rows, year rows, seed, overlay rows) | MERGE |
| W4a+W4b+W3 | implementer | sonnet | 40bfc05 | overlay mappings integrated by M1 (UNMAPPED_OVERLAYS then only override--year-cell) | MERGE |
| X2 | implementer | sonnet | 9e0a261 | CI tests aligned with F1 plan rules and seed | MERGE |
| F4 | implementer | sonnet | 108b685 | accounts/auth/errors parity (error pages, offline card, auth copy, currency validation) | MERGE |
| H3 | implementer | sonnet | 88675c4 | afford 250.00 mapping on Today pages, row-menu pointer parked | MERGE |
| F5 | implementer | sonnet | afec381 | Today / new-entry / shell parity (skeleton, flash copy, empty seed, exact bar cells) | MERGE |
| F2 | implementer | sonnet | 58624ad | ledger planned/recurring/actual parity (entry order, expanded override rows, seed shape) | MERGE |
| F3 | implementer | sonnet | 2eb889a | settings parity (duplicate category 422, security/users copy, category dialogs, one-time password copy) | MERGE |
| X3 | implementer | sonnet | 3488f95 | CI tests aligned after F3/F4/F5 merges | MERGE |
| F7 | implementer | sonnet | 1182712 | plan dialogs, inline year-cell editor, UNMAPPED_OVERLAYS empty | MERGE |
| H4 | implementer | sonnet | b75e9d4 | harness mapping (settings categories modifier, long board route) | MERGE |
| O1 | implementer | sonnet | 75d65c4 | overlay absent/class/app-value row kinds; no-matches, forecast net, analytics deltas | MERGE |
| F4b | implementer | sonnet | ea03dc6 | accounts parity (checked date, sparkline rows, new-account dialog, credit card option); handed over | MERGE |
| F6 | implementer | sonnet | 63013b5 | ledger dialogs parity (chips lead, grouped amounts, credit line, override remove) | MERGE |
| X5 | implementer | sonnet | c70d6ee | tests for the F6 picker rule (ruff) | MERGE |
| R1 | implementer | sonnet | f33072c | recent chips = most used in the last 90 days (handoff rule), seed history shaped | MERGE |
| N1 | implementer | sonnet | 8bac99c | near-pass fixes (keyboard row menus, afford text run, aria-invalid glue bug, rule titles, promote-all hidden overlay) | MERGE |
| F8 | implementer | sonnet | 81c0fdf | new-entry dialog parity (account order, grouped hero, credit line, picker a11y); handed over | MERGE |
| X6 | implementer | sonnet | e92f3d3 | CI tests after N1/R1/F8 merges | MERGE |
| V1 | implementer | sonnet | 254bd6d | viewport-specific harness fixes (row menus, year cell, long board marks, one-time password) | MERGE |
| F9 | implementer | sonnet | d4c06a8 | recent chip lead on pointer pick, formula preview line, recipe normalisation docs | MERGE |
| Q1 | implementer | sonnet | 73fc6f5 | formula component errors, live region, chart cap decimals, recurring dialog rows | MERGE |
| P1 | implementer | sonnet | d9f28d0 | docs: operator options for blocked handoff comparisons (measured) | MERGE |
| X7 | implementer | sonnet | db4357a | formula fragment tests, patch files excluded from whitespace hooks | MERGE |
| I1 | implementer | sonnet | 20a1799 | one flash region, category swatch snap, picker placeholder row | MERGE |
| N2 | implementer | sonnet | 1d48851 | recipe fixes (scroll back, close-button ring, home key, answer wait) | MERGE |
| O2 | implementer | sonnet | ? | overlay row; returned and dropped (the overlay would have hidden a real difference); branch `wi/ui/sourdough/O2` kept as reference only | RETURN |

R1 was merged in place of O2. No ADR number was added in this run.

## Wave tests

- Tester ran wave 1 only. Later waves relied on CI: the required job and the Chromium e2e job were green per head.
- Failures found and fixed by follow-up items: X1 (detect-secrets false positive in the mapping test), X2 (CI tests aligned with the F1 plan rules and seed), X3 (CI tests after the F3/F4/F5 merges), X5 (F6 picker rule tests, ruff), X6 (CI tests after N1/R1/F8), X7 (formula fragment tests; patch files excluded from whitespace hooks).
- Wave 1 tester result: ? (not in the brief).

## CI as the lab

- The reference comparison runs as `visual.yml` on `wi/**` branches through `workflow_dispatch`.
- The local lab (`handoff.compare`) measured the operator options on `d4c06a8`; see [operator-options-2026-11-26.md](../plans/ui-redesign/operator-options-2026-11-26.md).
- Newest completed `visual.yml` run whose head is an ancestor of `1d48851`: run 45738603125 on `20a1799`. Reference shard failures (212 tests per shard): `1024:light` 26, `375:light` 19, `1440:dark` 25, `375:dark` 19, `1440:light` 25, `1024:dark` 26. The reference job is advisory (`continue-on-error`) and is not in `visual-gate`.
- The run on `1d48851` was still in progress when this log was written.

## Load and incidents

- Peak 5-min load: not recorded.
- Stuck or stopped agents, overruns past 1 h, lock waits: F4b and F8 ran out of runtime budget and were handed over to a handover agent. O2 was returned and dropped (see the table).

## Escalations and deferred questions

- F4b: handed over to a handover agent after the runtime budget ran out; models ?.
- F8: handed over to a handover agent after the runtime budget ran out; models ?.
- O2: returned and dropped; replaced by R1 (recent chips).
- Operator decisions pending: [operator-options-2026-11-26.md](../plans/ui-redesign/operator-options-2026-11-26.md) (D1-D11) and [operator-decisions-2026-11-25.md](../plans/ui-redesign/operator-decisions-2026-11-25.md).
- Deferred questions asked at the end: ?
