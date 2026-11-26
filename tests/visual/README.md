# Visual regression

Opt-in suites (not part of `just ci`). ADR-0027 section 4, amended by ADR-0106.

## Route snapshots (`test_snapshots.py`, T-Q251)

Two remaining old-UI routes (budget, forecast; migrated pages are compared against the handoff references) x 375/1024/1440, light theme, baselines in `__snapshots__/` (Linux only). Run with `just visual` (docker, pinned Playwright container) or via `.github/workflows/visual.yml`; regenerate with `just visual-update` or the `update_baselines` dispatch (artifact, then commit). Never generate baselines on macOS. Tolerance `MAX_DIFF_PIXEL_RATIO = 0.001`. Missing baseline: fails in CI, skips locally.

## Handoff references (`handoff.py`, `test_reference.py`, T-UT10)

References come from the designer handoff (`docs/design/rising-dough-frontend/`, frozen), not from the app.

- Never committed (ADR-0147 section 1): `tests/visual/reference/` is gitignored and rendered in the same job and pinned container as the app (the `reference` job of `visual.yml`, advisory until surfaces migrate). CI shards the 1272 tests into six jobs of 212, one per width x theme (`strategy.matrix`, `fail-fast: false`, 45 min each): the job sets `REFERENCE_SHARD=<viewport>:<theme>` (e.g. `1440:dark`; also the `--reference-shard` option in `tests/visual/conftest.py`) so `handoff.generate` renders only that shard's references and only its tests run. Artifacts per shard: `visual-references-<viewport>-<theme>`, `visual-reference-actual-<viewport>-<theme>`; each shard appends a pass/fail and wall-time line to the job summary. Rendering uses the OVERLAID handoff (`overlay.py`, data from `handoff_overlay.toml`).
- Render locally: `just visual-reference [surface]` (docker, pinned container; never on the host). Serves the handoff on 127.0.0.1, screenshots every page (106) at 1440 / 1024 / 375, light and dark (`?theme=`), animations frozen, browser clock fixed at 2026-10-31T10:00Z, fonts awaited, network idle. Output: `reference/<group>/<page>.<viewport>.<theme>.png`.
- Compare: `just test-visual --reference=handoff [surface]` (same container; surface: today, accounts, ledger, plan, settings, auth, errors, overlays). Renders the references first, then runs only `test_reference.py` for every surface. Expected red with the old app (T-UR00b red run) until each surface migrates.
- Fixture: the app side of `test_reference.py` uses the frozen server on the handoff seed (next section) at 2026-10-31 (`frozen_server.HANDOFF_FIXTURE_DATE`). `test_snapshots.py` (old-UI route baselines, removed per migrated surface) still serves a copy of `data/demo.sqlite`.

### Tolerance (ADR-0147 section 2)

One strict tolerance for every app-vs-handoff comparison, all surfaces alike (`handoff.compare`):

| Check | Limit |
|---|---|
| Differing pixels | `MAX_DIFF_PIXEL_RATIO` = 0.1% |
| Largest 8-connected differing region | `MAX_DIFF_CLUSTER_PX` = 52 px (calibrated, T-UR00b) |
| Handoff vs itself (noise floor) | `SELF_TOLERANCE` = 0.05% |

Different image sizes always fail (`handoff.passes`), whatever the ratio; the reported ratio covers the shared top-left window plus the missing area, and the message carries both sizes. The cluster cap catches a small but real defect (a missing icon, a shifted label) that stays under the ratio on a tall page. Calibration: every handoff-vs-itself test appends `<cluster> <page> <viewport> <theme>` to `$VISUAL_KEEP_DIR/self-clusters.txt` (default `visual-actual/`), and each shard's summary line reports `max self-cluster: <N>px`. Both files are uploaded with the `visual-reference-actual-<viewport>-<theme>` artifact (the reference job sets `VISUAL_KEEP_DIR=visual-actual`). Set the cap to twice the largest self-cluster seen over at least two CI runs under load. Exceptions only through the "Tolerance exceptions" table in `docs/plans/ui-redesign/derived.md` (reason plus operator sign-off). A failing comparison writes `<page>.<viewport>.<theme>.diff.png` into `VISUAL_KEEP_DIR`: differing pixels red, the largest cluster outlined in blue; the assertion message carries ratio, cluster size and its box. `test_snapshots.py` (old-UI baselines) keeps its own `diff_ratio` threshold (`MAX_DIFF_PIXEL_RATIO` there is its own constant).

#### Intended differences, tolerance exceptions, overlay rows

Three different tools, do not mix them. A page that differs from the handoff by operator decision is an *intended difference*: a row of "## Intended differences" in `docs/plans/ui-redesign/derived.md`, parsed by `intended.py` and marked `xfail(strict=True)` in `test_app_matches_handoff` for the listed page and width/theme shards (only the app comparison, never the handoff self test). It must fail; if it starts to match, the strict xfail fails (XPASS) and the row must go. A *tolerance exception* is a pixel allowance on a page that should match (the "Tolerance exceptions" table, reason plus sign-off). An *overlay row* (`handoff_overlay.toml`, `overlay.py`) changes the handoff side so both render the same data; it removes a data difference and says nothing about design. A shards cell must name widths/themes or say "all" (free text raises); when two rows list the same page and shard the first row wins. `test_intended.py` checks the parser and that the marked set equals the table.

#### Cluster cap calibration (T-UR00b)

`MAX_DIFF_CLUSTER_PX` = 52 = 2 x 26 px, the largest handoff-vs-itself cluster per shard across three `visual.yml` runs (2026-11-24). The per-shard maxima were the same in all three runs:

| Shard (viewport:theme) | Max self-cluster | Runs |
|---|---|---|
| 375:light | 26 px | 45496302019, 45496318944, 45498452834 |
| 375:dark | 19 px | 45496302019, 45496318944, 45498452834 |
| 1024:light | 15 px | 45496302019, 45496318944, 45498452834 |
| 1440:light | 15 px | 45496302019, 45496318944, 45498452834 |
| 1024:dark | 14 px | 45496302019, 45496318944, 45498452834 |
| 1440:dark | 14 px | 45496302019, 45496318944, 45498452834 |

Runs 45496302019 and 45496318944 ran on branch `wi/ui/sourdough/UR00bD` at `afbd61f1`; run 45498452834 ran on `ui/sourdough` with the final UR00bD code. Shard wall times were 335-768 s (timeout 45 min). The red run 45493474608 failed every shard on the old app (106 failed / 106 passed); run 45498452834: 105 failed, 107 passed per shard.

Recalibration rule: rerun the calibration (`visual-actual/self-clusters.txt` from the reference job, twice the largest value over at least two CI runs under load, ADR-0147 section 2) whenever the pinned Playwright container or the fonts change. Changing the cap needs an amendment to ADR-0147.

### Normalised state

- The app selects the amount of an opened dialog (`amount-input.js`); a static handoff mock cannot show a selection, so `handoff_recurring.settle` collapses it for `SETTLED_DIALOGS` (deliberate difference, `derived.md`); focus is kept.
- Focus after a 422 (Q1): `handoff_recurring._incomplete` clicks the dialog title, taking the focus from the field the dialog focused (`dialog.js` focuses the first invalid input); the field shows no ring in the file; its static ring sits on the close button, which `handoff_recurring._focus_close_ring` focuses after the click (Shift press then focus, as for the one-time password; T-UR00b N3: cluster 504 px to 0).
- `edit-recurring--empty` (`handoff_recurring._empty`): the user clicks the dialog title, so the category-list trigger loses its focus ring (the static handoff shows none), then focuses the close button with its ring (`_focus_close_ring`: Shift press then focus), and every scrolled element of the dialog is reset to `scrollTop = 0` (the user scrolls back up); `derived.md` has the row (F9).
- Pointer and scroll (V1): `_row_menu` focuses the trigger with `preventScroll` then presses Enter (the handoff opens at scroll 0); the year-cell recipe scrolls the grid back to its left edge and parks the pointer at (0,0); `handoff_recurring._transaction_error` and `handoff_newentry._error` call `mouse.move(0, 0)` (no hover on the save button); the one-time-password close-button ring comes from a Shift press then focus (stands in for keyboard Tab so `:focus-visible` shows).

- New entry (N2): `handoff_newentry._scroll_back_up` resets every scrolled element of the dialog to `scrollTop = 0` after the typed states (the user scrolls back up to the amount; `repeats-fixed` at 1024 and 375 differed by the scroll). `new-entry--repeats-formula` ends on the close button (Shift press then focus, as for the one-time password: the file shows its ring, no hover). `new-entry--over-limit` types the note `Takeaway` and presses Home (the file shows the 13,000.00 hero from its first digit and the note). `new-account--error` waits for the field error before moving focus: the 422 swap raced the refocus (1.96 % flake).
- Not reproducible, left red: `new-entry--error` (the file shows Takeaway checked beside "Pick a category" and a minus on the 0.00 hero: unreachable by a user, and an overlay row cannot reorder or check chips) and `edit-recurring--picking` (the file lists the ticked categories first, the app lists alphabetically; no documented "selected first" rule).

### Known gaps

- Overlay pages (`pages/overlays/*`) are compared against the plain `/today` route without opening the dialog; overlay routing is a later item.
- Errors surface: 404 compares against `/settings/users/999999/edit` (full-page 404; unknown paths answer JSON, so they never render the page) and 422 against `/budget?month=zz`. The 409 and 500 pages have no deterministic full-page GET, so they stay on the 404 route and stay red until one exists.
- Forecast and flow chart geometry: committed `source = "geometry"` rows at the end of `handoff_overlay.toml`, generated by `uv run python -m tests.visual.test_overlay_geometry` and checked for drift by that module (ADR-0147 section 4 amendment 2026-11-25).
- Forecast net cell: a month the app projects positive where the board shows a loss (Dec 2026, Sep 2027) keeps the board's negative styling (overlay class), so those cells differ.
- The `recurring-board` modifier is not yet wired per page in `test_reference.py`.

### Bootstrap (before baselines exist)

`workflow_dispatch` only works once `visual.yml` is on `main`. Until baselines are committed, a PR run fails on every missing baseline, but each failing test still writes its actual screenshot to `__snapshots__/<route>.<width>.png`, and the workflow uploads that directory as the `visual-baselines` artifact (also on failure). Download it from the PR run and commit it. Later regenerations use the `update_baselines` dispatch or `just visual-update`.

## Working with this harness

Limits and the run that found them: [run log, environment and process limitations](../../docs/runs/2026-11-26-handoff-reference-comparison.md#environment-and-process-limitations).

- Use `visual.yml` on a pushed `wi/**` branch as the lab: `gh workflow run visual.yml --ref <branch>`.
- Branch names must be `wi/<main>/<id>` (for example `wi/ui/sourdough/B2`); `merge-item` and `check-item` derive the item branch from the current branch.
- Run pytest as one plain single-file command with an absolute path; the agent guard denies directory runs and chained commands.

## Handoff seed (`handoff_seed.py`, T-UR00b, ADR-0147 §3)

One base seed holds the handoff's entities at the frozen date 2026-10-31: 10 accounts (balances fitted to the handoff's figures; credit card with its 14,977.37 limit), 22 live categories plus 2 system ones (3 soft-deleted), 32 ledger rows (the 11 listed on the Ledger page, per-category lump entries that give the budget page's spent figures, and six Jul to Sep 2026 income and expense entries that give the analytics flow chart the board's four months), 4 live planned items (the 4th, "Annual bonus" 25,000.00 on 20 Nov, lifts the projection to the board's five-gridline axis; +1 deleted), 15 recurring rules (4 with the 19 % formula, 7 overrides), 13 budget defaults, income anchor Salary, users Ola and Ewa, a pending invite for accountant@example.test and the owner's two sessions (this Firefox one and a Safari one on iPhone, 83.24.117.21). Nothing is typed as a total: net worth, left per day and so on come from the app's services (`test_handoff_seed.py` pins them).

`build_seed(db_path, *, modifiers=())` migrates a fresh DB (it refuses an existing file), writes through the repositories and services with the clock frozen, and returns the dev session token. The `scratch_db` / `live_server` fixtures use it for `test_reference.py`; the `handoff_server(modifiers)` factory serves a modified seed for one state.

Modifiers (pure `SeedData -> SeedData` functions, `MODIFIER_NAMES`):

| Modifier | Effect |
|---|---|
| `empty` | Today `--empty`: no accounts, ledger, planned or recurring |
| `empty-accounts` | Accounts `--empty` (same data as `empty`) |
| `empty-ledger` | no transactions |
| `empty-planned` | no live planned items |
| `empty-recurring` | no rules or overrides |
| `recurring-board` | the 12 rules `ledger/recurring.html` lists (drops Today's three 07 NOV rules; the base keeps 15 because the Today boards show them as upcoming) |
| `long` | two 1,234,567.89 rows with a long description |
| `invite-expired` | the invite is 8 days old (link state expired) |
| `invite-used` | the invite was accepted (link state used) |
| `no-matches` | no data change: a filter query that matches nothing |
| `over-limit` | no data change: a 13,000.00 entry exceeds the card's 12,521.63 left |
| `form-error` | no data change: 422, wrong password and similar request states |

Values the seed cannot produce are not faked here; they are rows in `handoff_overlay.toml` (UR00bB, value-inventory section 5). Known today: tab counts 616 / 27 rules and per-account TXNS counts (the seed holds only the listed entries), committed 34.60 / left 1,399.93 / 199.99 per day / afford figures (the app also commits the overdue planned Annual insurance: 446.60 / 987.93 / 141.13), "checked 01 JUL" and "01 APR" for accounts with a reconciliation row, future-dated session and user times, the 21-category picker count, and the shared formula result 1,836.93. Also overlaid: the Safari session's start / last seen / expiry (the board's dates fall after the frozen day; the seed keeps the clock times 18:40 and 22:03 on 26 and 30 Oct) and the forecast table's per-month cells (57 of 60, generated from `forecast.monthly_projection`; only Oct 2026 income, net and end balance already match). The forecast net cell keeps the board's negative class and arrow, so a month the app projects positive where the board shows a loss (Dec 2026, Sep 2027) carries the board's styling.
