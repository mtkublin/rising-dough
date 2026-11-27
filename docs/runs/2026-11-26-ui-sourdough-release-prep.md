# Run 2026-11-26 ui-sourdough-release-prep

- Work branch: `ui/sourdough`; base `746a9e59` (merge(UR16S)); PR: #54 (draft, `ui/sourdough` -> `main`; to be marked ready by the operator)
- Request: bring `ui/sourdough` to ready-for-release grade before the operator's explore drill.
- Waves: 3 (closed by the bookkeeping merges SCR1 `51123e64`, SCR2 `82009545`, SCR3 `1bd15a7c`); items: 29 merge commits on the branch in this run (26 implementation items, 3 wave bookkeeping merges), plus UR16S after wave 3; agent runs: n/a (the per-run table below lists the runs the brief records; the rest are not reconstructed).
- Not merged: SLASH (`a8b292b8`, "/ focuses the ledger search field") is committed on its branch but not an ancestor of `746a9e59`; status at write time: in review. CSP (`wi/ui/sourdough/CSP`) is parked, not merged.

## Items merged

Times are the merge commit's committer time (`git log --merges`, +0100). Wave is derived from the position of the bookkeeping merges: before SCR1 = wave 1, between SCR1 and SCR2 = wave 2, between SCR2 and SCR3 = wave 3, after SCR3 = no bookkeeping merge yet.

| wave | item | merge sha | merged (+0100) | summary |
|---|---|---|---|---|
| 1 | DOC1 | 352fbe4c | 2026-11-26 14:09:06 | docs: operator decisions corrected, ADR-0147/0107 amendments, intended differences table |
| 1 | DOC2 | fc9c0aab | 2026-11-26 14:11:00 | docs: requirements F1.1/F1.1a/F2.5 and tasks T-UR44..T-UR51 |
| 1 | D5 | 54cabd3b | 2026-11-26 14:20:00 | new-entry tabs carry typed amount, category, account, note (D5-b, T-UR44) |
| 1 | D1B | 7ad71800 | 2026-11-26 14:21:02 | app-owned `rd/app/overrides.css`; vendored rd CSS byte-identical; D1-b picker underline |
| 1 | AMT | a2e070fc | 2026-11-26 14:30:32 | amount input accepts space/nbsp thousands grouping (T-UR46) |
| 1 | CI1 | 51718efc | 2026-11-26 14:31:25 | ci.yml: guard checkout fetch-depth 0 + blob:none (Q2); Tailwind step removed (T-UR15) |
| 1 | OVL1 | b3940d92 | 2026-11-26 14:31:57 | harness: D2-b/D3-a overlay rows, D10-A test token port + guard, RGB compare, picker-handoff-list seed modifier |
| 1 | BUGB | c4162bf4 | 2026-11-26 15:08:01 | typed id routes 404 not 405, HTML/flash 404 for every not-found, HX-Reswap none on 422 (T-UR48 b-d) |
| 1 | BUGCE | 40a17c3c | 2026-11-26 15:08:49 | new-entry openers open the dialog in place; 1024 planned/recurring actions not clipped (T-UR48e, T-UR49) |
| 1 | SCR1 | 51123e64 | 2026-11-26 15:09:38 | wave-1 bookkeeping: tasks, CHANGELOG, ADR index |
| 2 | D8E | 9215e6b9 | 2026-11-26 15:31:08 | overlay insert_row op + guard; delete-account backdrop gets the 11th account (D8-E) |
| 2 | INTENDED | edb37f0f | 2026-11-26 15:31:33 | intended differences parsed from derived.md, strict xfail in the reference comparison |
| 2 | D8R | d6d8221b | 2026-11-26 15:39:24 | reconcile dialog per handoff: live hero, always Reconciliation + snapshot, no extras (D8-R, T-UR45) |
| 2 | BUGA | 5561a853 | 2026-11-26 15:47:52 | dialog validation: 422 not 500, no bad values saved, empty amount copy (T-UR47) |
| 2 | OVR1024 | ba245dee | 2026-11-26 15:48:29 | planned/recurring table override only below 70rem; 1024 recorded as intended difference (T-UR49) |
| 2 | BUGA2 | c57383e1 | 2026-11-26 16:12:36 | saves/promotes off the ledger keep the flash and refetch via events, no HX-Refresh (T-UR48a) |
| 2 | T22 | 8b4e0d1f | 2026-11-26 16:24:02 | drill: per-deploy setup token via hashed dispatch input (repo public: token never in GitHub); bootstrap admin fallback (T-UR22) |
| 2 | W2FIX | ec1f2345 | 2026-11-26 16:28:01 | tests follow wave-2 behaviour: blank override refused, :int route keys normalised, reconcile ignores posted category (T-UR45, T-UR47) |
| 2 | FLASHCA | d9309309 | 2026-11-26 16:48:55 | new category and account saves keep the flash and refetch via events, no HX-Refresh (T-UR48a) |
| 2 | SCR2 | 82009545 | 2026-11-26 16:49:25 | wave-2 bookkeeping: T-UR45, T-UR47 done; changelog |
| 3 | CIFIX | 84ebafda | 2026-11-26 17:03:55 | formula create test expects the off-ledger stale events (T-UR48a) |
| 3 | RECSYNC | 279d0c4c | 2026-11-26 17:08:50 | zero-delta reconcile says Already in sync; snapshot wording matches the schema (T-UR45, S1.10) |
| 3 | DEAD | ec9131d5 | 2026-11-26 17:18:09 | dead-Python sweep: unused Jinja filters, year_cell_state, format_whole, any_recurring_row removed (T-UR51) |
| 3 | RACE | 7bae62cf | 2026-11-26 17:54:51 | typed note no longer lost: the amount's delayed focus-select runs only while it still has focus (T-UR44, T-UR48) |
| 3 | INV1 | 5301de28 | 2026-11-26 18:14:53 | reference reds: reconcile/picker recipes, D6-B rows; reconcile lists newest snapshots first; Today names archived categories (T-UR00b, T-UR50). Reused `categories_service.list_all(include_deleted=True)`; new helper `today_data.categories_with_archived` (thin wrapper, not registered) |
| 3 | UR41 | b63b2283 | 2026-11-26 18:30:39 | frontend audit re-run on the migrated templates: no blockers, 3 minor designer findings (T-UR41) |
| 3 | WEBKIT | bea9ce19 | 2026-11-26 18:31:45 | WebKit e2e green: download interruptions settled in the crawl, picker chip leads on WebKit (pointerdown), setup journey xfail on http (T-UR40 prep). Merged on e2e evidence; the WebKit visual audit is incomplete (driver hung), JS-only |
| 3 | SCR3 | 1bd15a7c | 2026-11-26 18:36:42 | wave-3 bookkeeping: T-UR41/42/44/48/49/51 done; changelog |
| after 3 | UR16S | 746a9e59 | 2026-11-26 18:41:19 | T-UR16 width sweep 320/768/1920, keyboard map, reduced motion: no blockers, 2 minor findings |

## Agent runs

Wall times are not in the brief and are recorded as n/a. Role models per the brief: implementers Sonnet except RACE's final attempt (Opus); reviewers Sonnet; scribes and testers Haiku; visual auditors Sonnet. Per-item reviewer rows are not listed: the brief does not give them.

| wave | item | role | model | attempt | wall time | verdict | note |
|---|---|---|---|---|---|---|---|
| 3 | RACE | implementer | sonnet | 1 | n/a | STOPPED | stopped at ~110 min without a final report |
| 3 | RACE | implementer | sonnet | 2 (handover) | n/a | RETURN | test-only fix; root cause not closed |
| 3 | RACE | implementer | opus | 3 | n/a | MERGE | escalated after two Sonnet attempts; root cause: `amount-input.js` delayed `select()` stealing focus; merged `7bae62cf` |
| 3 | INV1 | implementer | sonnet | 1 | n/a | STOPPED | stopped after ~80 min idle |
| 3 | INV1 | implementer | sonnet | 2 (handover) | n/a | PARTIAL | then two app fixes, merged in `5301de28` |
| 2 | BUGA2 | implementer | sonnet | 1 | n/a | STUCK | first agent stuck; handed over |
| 2 | BUGA2 | implementer | sonnet | 2 (handover) | n/a | MERGE | merged `c57383e1` |
| - | CSP | implementer | sonnet | 1 | n/a | STOPPED | stopped after push; branch `wi/ui/sourdough/CSP` |
| - | CSP | implementer | sonnet | 2 (handover) | n/a | PARKED | fragment nonce mismatch fixed on branch; WebKit `style-src-attr` violations remain; not merged |
| 1 | wave 1 tests | tester | haiku | 1 | n/a | GREEN | local tester |
| 2 | wave 2 tests | tester | haiku | 1 | n/a | RED | 5 stale tests, fixed by W2FIX |
| 2 | wave 2 tests | tester | haiku | 2 (re-test) | n/a | STOPPED | stopped by operator request (see below) |
| 3 | UR41 | visual-auditor | sonnet | 1 | n/a | FINDINGS | no blockers, 3 minor designer findings |
| 3 | WEBKIT | visual-auditor | sonnet | 1 | n/a | INCOMPLETE | driver hung; merged on e2e evidence, JS-only |
| after 3 | UR16S | n/a | n/a | n/a | n/a | FINDINGS | no blockers, 2 minor findings (from the merge subject) |

## Wave tests

| wave | base..head | test-changed | test-e2e | failures (blamed item) |
|---|---|---|---|---|
| 1 | n/a (tip at SCR1 `51123e64`) | GREEN (local tester) | n/a | none |
| 2 | n/a; GitHub CI on `ec1f2345` / `82009545` | RED (local tester), 5 stale tests | n/a | W2FIX; one remaining stale test on the GitHub CI tips (CIFIX) |
| 2 | re-test | stopped by operator request | n/a | n/a |
| 3 | GitHub CI on later tips | CI success on the tip | Chromium success on the tip; WebKit green (WEBKIT) | none on the tip |

Operator decision, 2026-11-26: "why are there local test suites running? didn't we settle for running those on GH?" Rule from then on: no local wave tester; the wave verdict is GitHub CI plus e2e on the branch tip.

## Load and incidents

- Peak load: ~15 on 8 cores during the local wave-2 suite (time n/a; no `uptime` sample recorded).
- GitHub API rate limit exhausted at ~14:55 and ~15:59 (reset 16:07). Agents were told to use `gh run watch --interval 90`.
- Stuck or stopped agents: RACE first Sonnet agent (stopped at ~110 min, no final report); INV1 implementer (stopped after ~80 min idle); CSP implementer (stopped after push); BUGA2 first agent (stuck); wave-2 re-test tester (stopped by operator request); WEBKIT visual audit (driver hung).
- Overruns past the 1 h agent budget: RACE and INV1 (both handed over).
- Lock waits: n/a.

## Stops and handovers

- RACE: Sonnet attempt stopped at ~110 min; Sonnet handover fixed the test only and returned; Opus found the root cause (`amount-input.js` delayed `select()` stealing focus) and merged the fix.
- INV1: stopped after ~80 min idle; handover agent returned PARTIAL; two app fixes followed and merged in `5301de28`.
- CSP: stopped after push; handover fixed the fragment nonce mismatch on the branch. WebKit `style-src-attr` violations remain, so CSP is PARKED, not merged, and `wi/ui/sourdough/CSP` is kept.
- BUGA2: first agent stuck; handed over and merged in `c57383e1`.
- Wave-2 local tester: re-test stopped by operator request (see Wave tests).
- WEBKIT: visual audit incomplete (driver hung); merged on e2e evidence, JS-only.

## Escalations and deferred questions

- RACE: Sonnet -> Sonnet (handover) -> Opus, after two Sonnet attempts, root cause in `amount-input.js`.
- INV1: Sonnet -> Sonnet handover (PARTIAL), then two app fixes.
- Deferred questions asked at the end: 5
  1. D6-B intended-difference row extended from 8 to 11 pages (delete-account, reconcile, reconcile--liability on the same accounts backdrop): confirm.
  2. CSP `style-src` hardening (T-UR16): do it after the drill, or drop for v1?
  3. PAR-B precedent (earlier deferred).
  4. Planned-save flash miss (earlier deferred).
  5. Case-sensitive duplicate category names (earlier deferred).

## Designer change requests

1. Chip order on `new-entry--error` and `edit-recurring--picking` (reference pages red; no decision).
2. `/today` hero loaf overlaps the caption at 375.
3. `.rd-tabs` strip hides tabs without a hint at 375 (settings, "security").
4. Year grid Oct-Dec off-screen at 1024.
5. New-entry dialog at 320 truncates the account and date values.

## Operator actions before the explore drill

1. Apply `docs/plans/ui-redesign/q-t-ur22-drill-workflow.md` (`drill.yml` + `terraform.yml`, `setup_token_hash` input).
2. Optional prod secret `SETUP_TOKEN_HASH`.
3. Two `ci.yml` edits: `q2-ci-checkout.md` and `q-ci-tailwind-removal.md`.
4. Run the explore drill.
5. T-UR40 ruleset (WebKit e2e is now green).
6. Mark PR #54 ready and merge.

## Process lessons (for an ADR-0150 amendment; docs-first, not done in this run)

1. Drop the local wave tester in favour of GitHub CI on the branch tip.
2. "One final report per subagent" made later agent reports vanish; the orchestrator must poll CI and use SendMessage.
3. `merge-item` prune deletes the empty `worktree-agent-*` placeholder branch of an agent that has not yet switched branch (harmless here; the worktree was kept).
4. `agent_guard` blocks reviewers and auditors from single-file pytest and webkit runs, and reads `2>&1` as a directory run.

## Follow-ups

- CSP WebKit leads (see the branch notes).
- `_orphans` keyed by message text.
- No test for the amount focus-select feature.
- Tiny corner clusters: category picker at 1024, reconcile at 375 light.
- `budget.py:147` and `:204` return a raw "invalid amount" 422 body for non-dialog posts.
- The `wip(INV1)` commit subject is accepted (no history rewrite).
