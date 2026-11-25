# Run 2026-11-24 ui-sourdough

- Work branch: `ui/sourdough`; base `175b41d1` (wave 6); tip at log time `b43d8c6b`; PR: #54 (draft, per handover)
- Request: finish the ui-redesign run on `ui/sourdough` (T-UR items, parity items, CI repair) from the local orchestrator handover (`docs/runs/2026-11-25-ui-sourdough-handover.md`) through the remote session; release end point per handover Q11 (PR #54 green, drill-gate, then stop).
- Waves: 2 (wave 6 from `175b41d1`, wave 6b after the handover), plus CI-repair and parity sub-batches; items: 57 merged item merges (21 in wave 6, 36 in wave 6b); agent runs: ? (not tracked, see below)

## Waves

- **Wave 6** (base `175b41d1`, through the handover): UR04e `8f958ecd`, UR00c `59d19398`, UR04f `5be4c7c1`, UR12 `8de349c3`, UR13 `15aa38f6`, UR07b `2540995c`, UR11b `dd99961c`, UR02c `faff04b2`, UR27 `427f6c17`, UR21 `ef3458b2`, UR04g `4d4bd510`, QOR1 `82344851`, QCI1 `ca6768e2`, UR21b `4fd9dd4c`, UR09a `adff8da9`, UR10b `e6daa30c`, UR21c `f6fd3573`, UR12b `294bbbce`, UR00d `2e2457f6`, UR00e `2dbf6502`, UR02d `2c6f39f5`. Bookkeeping: SCRIBE6 `db2c1054`, SCRIBEHO `df6545c1`, main merge `aa771d57`.
- **Wave 6b** (items merged 2026-11-25 after the handover):
  - Handover queue: UR09b `249d94c2` (also `3b190535`), UR28b `fc5c8e2a`, UR08b `9c42c5dd`, UR14 `a5ad323e`, UR02e `53e01c52`, UR10a `942e2f8d`, UR08c `761d280d`, UR21d `e472afb9`, UR40a `dfb11105`, UR42a `95ddde59`, UR24 `f62c0bb6`, UR41a `0fba76e9`, UR43a `9eea034f`.
  - Wave 6b bookkeeping: SCRIBE6B `31a29b6a`.
  - Later items: UR28 `c765a4d8`, UR23 `e3ec9932`, UR21a `4495a27c`, UR00f `3c5aec99`, UR20a `e41ee9fe`, UR20b `9c1a902d`.
  - CI-repair items QFIX1-9: QFIX1 `38683f35`, QFIX2 `eb53536c`, QFIX3 `91de6dfe`, QFIX4 `be8082f6`, QFIX5 `4e11d8aa`, QFIX6 `bce51a9a`, QFIX7 `5ec2559c`, QFIX8 `fa0179ba` (and `6c105cc8`), QFIX9 `aff88b94`.
  - Cutover: UR15a `c9d835d5`, UR15b `ba0c7226`, UR15c `6eab98c6`, UR15d `d8e57560`.
  - Parity: PAR-A `f13810bd`, PAR-B `b43d8c6b`, PAR-C `0533c399`, PAR-D `6e1cb970`.
  - QFIX10: not merged. Branches `QFIX10`, `QFIX11`, `QFIX12` exist on origin only.

## Agent runs

Per-agent wall times and models were not tracked in this session (remote session; subagent notifications only). Rows are per item: role and model are `?` unless the merge subject or the handover says so. The verdict column gives the merge; reviewer RETURN counts are `?`.

| wave | item | role | model | attempt | wall time | verdict | note |
|---|---|---|---|---|---|---|---|
| 6 | UR04e | ? | ? | ? | ? | merged `8f958ecd` | RETURN count ? |
| 6 | UR00c | ? | ? | ? | ? | merged `59d19398` | RETURN count ? |
| 6 | UR04f | ? | ? | ? | ? | merged `5be4c7c1` | RETURN count ? |
| 6 | UR12 | ? | ? | ? | 38 min (handover) | merged `8de349c3` | RETURN count ? |
| 6 | UR13 | ? | ? | ? | ? | merged `15aa38f6` | RETURN count ? |
| 6 | UR07b | ? | ? | ? | ~78 min (handover) | merged `2540995c` | shell hung 44 min, killed (handover) |
| 6 | UR11b | ? | ? | ? | ? | merged `dd99961c` | RETURN count ? |
| 6 | UR02c | ? | ? | ? | ? | merged `faff04b2` | RETURN count ? |
| 6 | UR27 | ? | ? | ? | ? | merged `427f6c17` | sent GETs to port 8000 (handover) |
| 6 | UR21 | ? | ? | ? | ? | merged `ef3458b2` | allowlist FAIL overridden, framework row (handover) |
| 6 | UR04g | ? | ? | ? | ? | merged `4d4bd510` | auditor heredoc hung 88 min, killed (handover) |
| 6 | QOR1 | ? | ? | ? | ? | merged `82344851` | orchestrator idle stall (handover) |
| 6 | QCI1 | ? | ? | ? | ? | merged `ca6768e2` | |
| 6 | UR21b | ? | ? | ? | ? | merged `4fd9dd4c` | |
| 6 | UR09a | ? | ? | ? | ~3 h (handover) | merged `adff8da9` | 1 h budget exceeded (handover) |
| 6 | UR10b | ? | ? | ? | ? | merged `e6daa30c` | audit `docs/audits/2026-11-25-t-ur10b-planned-recurring-dialogs.md` |
| 6 | UR21c | ? | ? | ? | ? | merged `f6fd3573` | wave 6 tester RED fix |
| 6 | UR12b | ? | ? | ? | ? | merged `294bbbce` | edited 2 test files outside Owns (handover) |
| 6 | UR00d | ? | ? | ? | ? | merged `2e2457f6` | |
| 6 | UR00e | ? | ? | ? | ? | merged `2dbf6502` | |
| 6 | UR02d | ? | ? | ? | ? | merged `2c6f39f5` | wave 6 tester RED fix |
| 6b | UR09b | reviewer | ? | ? | ? | MERGE (handover) `249d94c2` | parked on Q26; merged twice in history (`3b190535`) |
| 6b | UR28b | ? | ? | ? | ? | merged `fc5c8e2a` | |
| 6b | UR08b | ? | ? | ? | ? | merged `9c42c5dd` | parked on Q21, then merged |
| 6b | UR14 | ? | ? | ? | ~62 min (handover) | merged `a5ad323e` | Q21/Q22 edits; `6dad7b86` also a UR14 merge |
| 6b | UR02e | ? | ? | ? | ? | merged `53e01c52` | Q29 |
| 6b | UR10a | ? | ? | ? | ~37 min plus fixes (handover) | merged `942e2f8d` | F1-F3 fixed; `wip(UR10a)` commit subject kept |
| 6b | UR08c | ? | ? | ? | ? | merged `761d280d` | Q15 |
| 6b | UR21d | ? | ? | ? | ? | merged `e472afb9` | Q28 |
| 6b | UR40a | ? | ? | ? | ? | merged `dfb11105` | Q1/Q9/Q16 recorded |
| 6b | UR42a | ? | ? | ? | ? | merged `95ddde59` | Q14, ADR-0153 |
| 6b | UR24 | ? | ? | ? | ? | merged `f62c0bb6` | e2e baseline failures tracked separately |
| 6b | UR41a | ? | ? | ? | ? | merged `0fba76e9` | Q12 |
| 6b | UR43a | ? | ? | ? | ? | merged `9eea034f` | Q25 |
| 6b | QFIX1 | ? | ? | ? | ? | merged `38683f35` | CI repair |
| 6b | QFIX2 | ? | ? | ? | ? | merged `eb53536c` | CI repair |
| 6b | QFIX3 | ? | ? | ? | ? | merged `91de6dfe` | CI repair |
| 6b | QFIX4 | ? | ? | ? | ? | merged `be8082f6` | CI repair |
| 6b | QFIX5 | ? | ? | ? | ? | merged `4e11d8aa` | CI repair; agent could not be resumed (see Escalations) |
| 6b | QFIX6 | ? | ? | ? | ? | merged `bce51a9a` | CI repair |
| 6b | QFIX7 | ? | ? | ? | ? | merged `5ec2559c` | CI repair; reviewed, Chromium e2e green per subject |
| 6b | QFIX8 | ? | ? | ? | ? | merged `fa0179ba`, `6c105cc8` | CI repair; two merge commits |
| 6b | QFIX9 | ? | ? | ? | ? | merged `aff88b94` | CI repair after UR15c |
| 6b | UR28 | ? | ? | ? | ? | merged `c765a4d8` | |
| 6b | UR23 | ? | ? | ? | ? | merged `e3ec9932` | reviewed per subject |
| 6b | UR21a | ? | ? | ? | ? | merged `4495a27c` | reviewed per subject; operator step open (Q10) |
| 6b | UR00f | ? | ? | ? | ? | merged `3c5aec99` | 59 to 39 unmapped overlays |
| 6b | UR20a | ? | ? | ? | ? | merged `e41ee9fe` | reviewed, audited, Chromium e2e green per subject |
| 6b | UR15b | ? | ? | ? | ? | merged `ba0c7226` | reviewed, audited, Chromium e2e green per subject |
| 6b | UR20b | ? | ? | ? | ? | merged `9c1a902d` | |
| 6b | UR15a | ? | ? | ? | ? | merged `c9d835d5` | reviewed; Chromium e2e green per subject |
| 6b | UR15c | ? | ? | ? | ? | merged `6eab98c6` | |
| 6b | UR15d | ? | ? | ? | ? | merged `d8e57560` | |
| 6b | PAR-A | ? | ? | ? | ? | merged `f13810bd` | merged with a failing subject check (`docs(PAR-A)` audit commit) |
| 6b | PAR-C | ? | ? | ? | ? | merged `0533c399` | |
| 6b | PAR-D | ? | ? | ? | ? | merged `6e1cb970` | reviewed/checked; Chromium green per subject |
| 6b | PAR-B | ? | ? | ? | ? | merged `b43d8c6b` | |

Verdicts are the merge state only. Reviewer and auditor verdict paths are in `docs/audits/` (per-item audit records) and in the merge subjects; no per-run verdict file was kept for RETURN counts.

## Wave tests

| wave | base..head | test-changed | test-e2e | failures (blamed item) |
|---|---|---|---|---|
| 6 | `175b41d1..2c6f39f5` | not run | not run | tester RED at `e6daa30c`: `test_crawl` `/setup` (fixed by UR21c `f6fd3573`); `test_network_failure_shows_flash` (fixed by UR02d `2c6f39f5`, changed by Q29 in UR02e) |
| 6b | `2c6f39f5..b43d8c6b` | not run | not run | none recorded |

- No wave tester pass was run in wave 6b. GitHub CI on each tip was the full-suite check.
- Observed on read-only `gh run list` (this session): `6eab98c6` CI failure (repaired by QFIX9 `aff88b94`); `c9d835d5` CI failure; `aff88b94` CI success, e2e failure; `d8e57560` CI success, e2e failure (the UR15d tip, so `test_old_frontend_removed` ran green in CI); `f13810bd` CI success, e2e failure; `0533c399` and `6c105cc8` CI cancelled by later merges; `b43d8c6b` (log tip) CI still in progress when this log was written: result ?.

### CI repair items

- QFIX1 `38683f35`: stale snapshot context keys in ledger hero tests, q2 patch whitespace, tailwind rebuild, clock-independent seed.
- QFIX2 `eb53536c`: 4 Chromium e2e failures (auth flash locator, crawl inventory, promote flow).
- QFIX3 `91de6dfe`: stale old-UI snapshot baselines removed from the visual suite.
- QFIX4 `be8082f6`: e2e submit barrier asserts a 2xx answer before DB reads.
- QFIX5 `4e11d8aa`: djlint on the invite page, tailwind rebuild, recurring formula create test.
- QFIX6 `bce51a9a`: ruff format on `test_recurring_formula`; all pre-commit hooks green repo-wide.
- QFIX7 `5ec2559c`: `tests/contract/routes.md` regenerated.
- QFIX8 `fa0179ba`, `6c105cc8`: tailwind rebuild, clock-dependent tests, e2e barrier path.
- QFIX9 `aff88b94`: same-account validation tests assert the field-level error.
- QFIX10-12: intermittent Chromium "note typed but not posted" failure. Investigation on branches `QFIX10`, `QFIX11`, `QFIX12` (origin only). Not merged. Root cause under investigation; this log does not claim one.

## Load and incidents

- Peak 5-min load: ? in this session. Handover: load 24.5 delayed dispatch during wave 6 (local session).
- Stuck or stopped agents: UR07b shell hung 44 min (killed); UR04g auditor heredoc hung 88 min (killed); UR09a about 3 h against a 1 h budget; orchestrator idle stall 07:46-09:17 (fixed by QOR1 and the orchestrator-skill amendment).
- Lock waits: lock removals by agents (handover).

## Deviations

### From the handover (copied from `docs/runs/2026-11-25-ui-sourdough-handover.md`, "Run-log deviations so far")

- UR09a ran about 3 h against the 1 h budget; UR10a about 37 min plus fixes, stopped at handover.
- The UR04g auditor's shell heredoc hung for 88 min and was killed; earlier, the UR07b hung shell was killed after 44 min.
- The UR27 agent sent read-only GETs to port 8000 (the operator's dev server).
- UR21 merged with check-item's allowlist FAIL overridden (permanent `[[framework]]` row; ADR-0130 list amended 20→21; QCI1 later added `--allow-framework-rows`).
- Orchestrator idle stall 07:46–09:17 (one agent in flight). Fixed by QOR1 and the main amendment.
- Lock removals by agents; load 24.5 delaying dispatch; implementers self-auditing; UR12 38 min, UR07b about 78 min, UR14 about 62 min.
- Wave 6 tester RED (2 failures, fixed by UR21c and UR02d, re-verification pending).
- UR12b edited two test files outside its Owns list (forced by the seed change; the reviewer accepted it).

### This session (remote)

- `gh` was unauthenticated at the start; then working, read-only only.
- The OAuth token lacks the `workflow` scope, so `ci.yml` changes could not be pushed. The Q2 checkout edit and the UR15d Tailwind steps were handed to the operator as docs (`q2-ci-checkout.md`, `q-ci-tailwind-removal.md`).
- Remote branch deletion returned 403: all merged `wi/**` branches remain on origin.
- `just` was not installed; `rust-just` was installed via uv.
- Playwright's default browsers were unavailable; the pre-installed Chromium was used via `executable_path` and a `--no-sandbox` plugin.
- `agent_guard` blocked local e2e and pytest directory runs for implementers and reviewers. Reviewers could not run tests: their verdicts rested on code reading and `check-item`. CI was the test lab.
- Implementers skipped `pytest-fast` and some hooks, so CI found failures after merges (QFIX1-9 above).
- `merge-item` pushes cancelled in-flight CI runs (concurrency group). Tips were verified by CI only after merge bursts (`0533c399`, `6c105cc8` cancelled).
- The UR10a `wip(UR10a)` commit subject and the PAR-A audit `docs(PAR-A)` commit scope were not rewritten (history not rewritten).
- PAR-A merged with a failing subject check.
- The intermittent Chromium flake (QFIX10-12) remains open; its root cause is under investigation.
- UR15d deleted the root `csrf.js`, `htmx-csrf.js` and `passkeys.js` copies; the ADR-0107 §2 amendment relocates the keep rows.
- Q2 and Q10 are operator steps (see below).
- Design-parity items are blocked on the operator: Q3 picker count (21 handoff vs 23 ADR-0151 vs 24 seed), Q4 bar labels vs ADR-0147 §3, Q5 `accounts--empty` vs ADR-0147, afford-it numbers vs ADR-0151.

## Escalations and deferred questions

- Escalations to Opus: none.
- Stops: handover-era stops, plus this session: none by TaskStop. Agent QFIX5 could not be resumed after `merge-item` pruned its worktree.
- Deferred questions asked at the end: see the list below (10 items).

## Operator questions and steps

1. Apply the `ci.yml` edits the token could not push: the Q2 checkout (`fetch-depth: 0`, `filter: blob:none`) per [q2-ci-checkout.md](../plans/ui-redesign/q2-ci-checkout.md), and the optional Tailwind step removal per [q-ci-tailwind-removal.md](../plans/ui-redesign/q-ci-tailwind-removal.md).
2. T-UR21a (Q10): add the GitHub `prod` environment secret `SETUP_TOKEN_HASH` and run the approved `terraform apply`, per [q10-operator-steps.md](../plans/ui-redesign/q10-operator-steps.md).
3. Design parity: picker count (Q3: 21 handoff, 23 ADR-0151, 24 seed).
4. Design parity: bar labels against ADR-0147 §3 (Q4).
5. Design parity: `accounts--empty` and the empty-state seed against ADR-0147 (Q5).
6. Design parity: afford-it numbers against ADR-0151.
7. Amount inputs: should grouped digits be accepted (`parse_amount_str` takes no grouping)?
8. Prune the stale `wi/**` branches on origin (the token cannot delete them).
9. Whether PR #54 is ready: CI on `b43d8c6b` was still running at log time; `e2e` was red on the recent merge tips. Marking the PR ready and merging to `main` are operator steps.
10. The explore drill and any prod deploy: not dispatched by this session (handover Q11).
