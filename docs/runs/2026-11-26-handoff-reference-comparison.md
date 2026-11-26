# Run 2026-11-26 handoff-reference-comparison

- Work branch: `ui/sourdough`; base `c1aad4f`; final head `b7b6115`; PR: #54 (draft, ui/sourdough -> main)
- Request: T-UR00b handoff reference comparison: map every overlay and page, merge per-surface parity items, and report what stays blocked (not green).
- Waves: no formal wave structure after the first: items were dispatched continuously (about 4-6 agents in flight); one wave tester ran after wave 1 (H1, S1, H2, W1); later items relied on item-level checks (reviewer + check-item + single-file runs) and CI per merge; items: 33 merged, 1 dropped (O2); agent runs: not recorded (the harness does not list finished agents; the transcript holds them).

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
| O2 | implementer | sonnet | not recorded | overlay row; returned and dropped (the overlay would have hidden a real difference); branch `wi/ui/sourdough/O2` kept as reference only | RETURN |

R1 was merged in place of O2. No ADR number was added in this run.

## Wave tests

- Tester ran wave 1 only. Later waves relied on CI: the required job and the Chromium e2e job were green per head.
- Failures found and fixed by follow-up items: X1 (detect-secrets false positive in the mapping test), X2 (CI tests aligned with the F1 plan rules and seed), X3 (CI tests after the F3/F4/F5 merges), X5 (F6 picker rule tests, ruff), X6 (CI tests after N1/R1/F8), X7 (formula fragment tests; patch files excluded from whitespace hooks).
- Wave 1 tester result: RED, one failure unrelated to the wave: `tests/unit/deploy/test_replace_rehearsal.py::test_init_write_and_stats` (`scripts/ci/rehearsal_marker.sh`, a local-environment failure; CI `just ci` was green on that head 85e8447).

## CI as the lab

- The reference comparison runs as `visual.yml` on `wi/**` branches through `workflow_dispatch`.
- The local lab (`handoff.compare`) measured the operator options on `d4c06a8`; see [operator-options-2026-11-26.md](../plans/ui-redesign/operator-options-2026-11-26.md).
- Newest completed `visual.yml` run whose head is an ancestor of `1d48851`: run 45738603125 on `20a1799`. Reference shard failures (212 tests per shard): `1024:light` 26, `375:light` 19, `1440:dark` 25, `375:dark` 19, `1440:light` 25, `1024:dark` 26. The reference job is advisory (`continue-on-error`) and is not in `visual-gate`.
- The run on `1d48851` was still in progress when this log was written.

## Load and incidents

- Peak load: observed single readings of 10.35 (1-min) and 7.44 (1-min) on a 4-core machine; no continuous record.
- Stuck or stopped agents, overruns past 1 h, lock waits: F4b and F8 ran out of runtime budget and were handed over to a handover agent. O2 was returned and dropped (see the table).

## Escalations and deferred questions

- F4b: handed over to a handover agent after the runtime budget ran out; models sonnet (the implementer role's default).
- F8: handed over to a handover agent after the runtime budget ran out; models sonnet (the implementer role's default).
- O2: returned and dropped; replaced by R1 (recent chips).
- Operator decisions pending: [operator-options-2026-11-26.md](../plans/ui-redesign/operator-options-2026-11-26.md) (D1-D11) and [operator-decisions-2026-11-25.md](../plans/ui-redesign/operator-decisions-2026-11-25.md).
- Deferred questions asked at the end: 11 (D1 to D11 in [operator-options-2026-11-26.md](../plans/ui-redesign/operator-options-2026-11-26.md)). Counted by `grep -c -E '^## D[0-9]+\. ' docs/plans/ui-redesign/operator-options-2026-11-26.md` = 11. Sections: D1 search all N categories and the picker list; D2 budget-row bar labels; D3 accounts--empty net worth; D4 afford-it states; D5 typed values over a tab switch; D6 ADR-0089 "after planned" overdue counts; D7 force-password and --error; D8 accounts dialogs; D9 today--flash 8 px; D10 one-time password; D11 category swatch Takeaway. The ADR-0089, force-password and accounts items are D6, D7 and D8, so they are inside the 11 and not counted again.

## Environment and process limitations

- Workflow files: the session's OAuth token has no `workflow` scope, so `.github/workflows/*` cannot be edited or pushed. Consequence: a workflow change has to be written for the operator. Workaround: `visual.yml` still runs on any pushed `wi/**` branch with `gh workflow run visual.yml --ref <branch>`; never with `update_baselines`.
- Artifact downloads: the agent proxy blocked the GitHub Actions artifact host (`productionresultssa8.blob.core.windows.net`), so `gh run download` failed. Consequence: reference artifacts could not be fetched. Workaround: the host was allowed through a new personal cloud environment named `rising-dough` (approved in-session by the operator); until then results were read from job logs.
- Test guard: `scripts/ci/agent_guard.py` denied many pytest invocations (directory runs, piped or chained commands, even some single files run from worktrees). Consequence: reviewers often could not run the tests they judged, so they read diffs, and the wave and CI runs were the evidence. Workaround: one plain single-file command with an absolute path and `PYTHONPATH=<worktree>/src` when the main checkout's source would otherwise be imported.
- `just merge-item` exit noise: it printed `send-pack: unexpected disconnect` / `remote end hung up` after most merges although the push had succeeded. Consequence: a false failure signal. Workaround: each push was verified with `git status -sb` showing `ui/sourdough...origin/ui/sourdough` in sync.
- Branch naming: `just merge-item` and `just check-item` derive the item branch as `wi/<current-branch>/<ID>`. Consequence: with MAIN=ui/sourdough, item branches must be named `wi/ui/sourdough/<ID>`; agents that created `wi/ui-sourdough/<ID>` had to be renamed. Workaround: renaming.
- Permission refusals: the auto-mode permission check refused one dispatch, an item that would have injected a deterministic token source into the visual server to match the handoff's fixed one-time password. Consequence: option D10 (D10-A) in the options doc is unimplemented and left to the operator. A `git reset --hard` early in the session was also refused; it was not needed, so no consequence.
- Advisory webkit lane: the e2e webkit lane (`tests/e2e`) failed on every head of this run and before it: crawl (ledger parquet export `Frame load interrupted`, Today promote `Load request cancelled`), plus `test_setup_page`, and intermittently `test_picker_chip_leads` / `test_new_entry_race`. Consequence: none on the required gate; not caused by this run. Chromium (required) was green on all merged heads except where fixed by X-items.
- Reference lab: only CI's pinned container renders comparable pixels, so the reference comparison cannot run locally. Workaround: agents built a local lab around `tests/visual/handoff.py` `compare()`, which reproduced CI sizes and ratios; the scripts live in the session scratchpad, not in the repo.
- Clock-dependent tests: four shifted-clock CI jobs (`BUDGET_TEST_NOW` 2027-01-31T23:30:00Z, 2026-12-31T23:30:00Z, 2028-02-29T12:00:00Z, 2027-03-28T01:30:00Z) caught tests with hard-coded dates (R1's 90-day window and F6 chip tests). Workaround: dates derived from the clock.
- Cross-item CI breaks: required CI failed after several merges because of interactions between items: X1 (detect-secrets literal), X2 (F1 plan rules and seed counts), X3 (F3/F4/F5 tests), X5 (picker rule tests), X6 (N1 titles and overlay cases), X7 (formula fragment context and patch files vs whitespace hooks). Consequence: red required CI on the heads in between. Cause: pre-commit `--all-files` was not always run by item agents before pushing. Workaround: the orchestrator added that to briefs from X1 on.
- Runtime budget and lost reports: F4b and F8 ran out of their 60-minute budget and were handed to fresh implementers. Several final reports did not reach the orchestrator (duplicate hand-backs). Consequence: state had to be read from branches and CI. Workaround: the branches and CI runs were read directly.
- Unverified claims: item F3 reported tests as added that were not committed; the reviewer caught it. Workaround: always verify claims with `git diff`.
- Visual run cancellation: `visual.yml` has a concurrency rule that cancels in-flight runs of a branch on every push, so docs-only pushes cancelled Visual runs of the previous head. Consequence: results for a head can be missing. Workaround: not recorded.
- Review-driven plan change: a reviewer finding rejected the chip-row overlay (O2) because it would have hidden a real difference; R1 implemented the documented rule instead.
