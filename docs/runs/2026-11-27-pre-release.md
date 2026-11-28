# Run 2026-11-27 pre-release

- Work branch: `ui/sourdough`; base `?`; PR: #54 (draft, `ui/sourdough` -> `main`; to be marked ready by the operator)
- Request: operator "let's do all we can before the release" after UI acceptance at `3df85e88`. Decisions in `docs/plans/ui-redesign/operator-decisions-2026-11-27.md`.
- Waves: `?`; items: 20 merged (listed below); agent runs: `?` (the table below has one row per item, not per run).
- Not merged: CSP (T-UR16 hardening) PARTIAL after timebox: Chromium and Firefox show 0 violations with style-src nonce-only; WebKit reports 3 style-src-attr violations on the native select in `fragments/ledger/filter-bar.html`. The release keeps `'unsafe-inline'`; follow-up T-UR99; branch `origin/wi/ui/sourdough/CSP` `351d7930`.

## Items merged

| item | task | merge sha |
|---|---|---|
| SCRIBE5 | ? | e65a3f9a |
| OVERCNT | T-UR70 | c5643be5 |
| CATCASE | T-UR95 | cd83c243 |
| GUARD | T-UR72 | b196e379 |
| FXSAVE | T-UR69 | 658bbf0b, 08906bf2 |
| YEARCELL | T-UR84 | 0134a4e7 |
| PLANCSS | T-UR85/71 | d3d9ca1c |
| FLASH | T-UR96 | 8ed5a6f4 |
| SNAPROUTES | T-UR98 | 99d99658 |
| UIMAP | T-UR86/88 | 29a0b6e4 |
| LEGEND | T-UR94/87 | 134e05b2 |
| KEYMAP | T-UR97 | f7b673c1 |
| PICKNEW | T-UR68 | 3b360a20 |
| FORMULA | T-UR89 | e85b245e |
| SCRIBE6 | ? | 22af385b |
| SWEEP | T-UR16 | 5b77555a |
| LEDGERPH | T-UR74 | 55192fcd |
| A11YHERO | T-UR16 | 7ac72bea |
| CIFIX | - | 03f818db |
| NOJSCSRF | T-UR84 | 3ed5d045 |

## Agent runs

Wall times are not in the brief and are recorded as `n/a`. Roles and per-run attempts are not in the brief and are `?`. Verdict is the item's outcome as given in the brief; returns are listed under Returns and re-work.

| item | role(s) | verdict |
|---|---|---|
| SCRIBE5 | ? | MERGE |
| OVERCNT | ? | MERGE |
| CATCASE | ? | MERGE |
| GUARD | ? | MERGE (after RETURN x2) |
| FXSAVE | ? | MERGE (after RETURN) |
| YEARCELL | ? | MERGE (after RETURN) |
| PLANCSS | ? | MERGE |
| FLASH | ? | MERGE |
| SNAPROUTES | ? | MERGE |
| UIMAP | ? | MERGE |
| LEGEND | ? | MERGE |
| KEYMAP | ? | MERGE |
| PICKNEW | ? | MERGE (after RETURN; audit FINDINGS, then CLEAN) |
| FORMULA | ? | MERGE (first approach blocked, redone) |
| SCRIBE6 | ? | MERGE |
| SWEEP | ? | MERGE |
| LEDGERPH | ? | MERGE (audit FINDINGS, then CLEAN) |
| A11YHERO | ? | MERGE |
| CIFIX | ? | MERGE (audit FINDINGS, see NOJSCSRF) |
| NOJSCSRF | ? | MERGE |

## Returns and re-work

- FXSAVE: review RETURN (weak tests); then merge-item guard fail (raw markup asserts), fixed before merge.
- GUARD: RETURN x2 (redirect parsing).
- YEARCELL: RETURN (inline style without nonce).
- PICKNEW: RETURN (e2e: `beforeSwap` read `detail.elt`, which is the swap target; fix is `detail.requestConfig.elt`; dup-count test assumed a global count). Audit FINDINGS (8px shift), then re-audit CLEAN.
- LEDGERPH: audit FINDINGS (1024 clip), fixed, re-audit CLEAN.
- CIFIX: audit FINDINGS (no-JS CSRF 403, pre-existing); handled by the NOJSCSRF item.
- FORMULA: first approach blocked by the contract test (`data={}` gives 422); redone client-side.

## Wave tests and CI

- No local wave tester in this run (policy 2026-11-26: the wave verdict is GitHub CI and e2e on the branch tip).
- `ci.yml` full suite red on `f7b673c1` and `3b360a20` (blamed YEARCELL, KEYMAP, LEGEND, PICKNEW); fixed by CIFIX.
- On `3ed5d045`: CI, e2e, a11y-perf, Security and Terraform all success.
- Visual failure: 180 missing baselines (expected until the T-UR65 operator dispatch) plus the advisory handoff comparison.

## Load and incidents

- Peak 5-min load: 30-37 during the CSP and WebKit local runs early in the run; low (2-8) later.
- Stops and incidents:
  - CATCASE reviewer detached the main checkout HEAD. Briefs since then say never checkout in the main checkout.
  - Stray lock waiters from stopped agents.
  - Orphan uvicorn servers from finished agents, killed at end of day.
  - Operator paused the run overnight 2026-11-27 and resumed 2026-11-28.

## Deviations

- OVERCNT commit subjects use `(T-UR70)` not `(OVERCNT)` (brief error).
- LEDGERPH brief named `pages/ledger.css` instead of `components/ledger.css` (brief error).
- LEGEND e2e uses `date.today()` with a reasoned `noqa` (follow-up T-UR102).

## Follow-ups

- T-UR99 to T-UR103 (in `docs/plans/ui-redesign/tasks.md`).

## Lessons

- Audit commits pushed to an item branch cancel its e2e run; read the run on the audit tip.
- Without a local wave tester, read `ci.yml` on main between merge bursts.
- New ui_map names need a mockup twin.
- Brief owned globs must name the real files.
- zsh does not word-split `$vars`.

## Operator list

1. Dispatch `visual.yml` with `update_baselines=true`; agent commits baselines; then apply `q-visual-reference-trigger.md` part 2 (T-UR65).
2. T-UR22 drill workflow patch (`q-t-ur22-drill-workflow.md`).
3. `SETUP_TOKEN_HASH` prod secret.
4. Mark PR #54 ready, drill-gate, explore drill.
5. ADR-0154 number clash with PR #59.
6. Questions: picker creates expense-only categories, OK? Sweep minor findings: fix or accept.

## Escalations and deferred questions

- Deferred questions asked at the end: `?` (the operator list above is the question set).
