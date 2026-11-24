# Visual regression

Opt-in suites (not part of `just ci`). ADR-0027 section 4, amended by ADR-0106.

## Route snapshots (`test_snapshots.py`, T-Q251)

Eight routes x 375/1024/1440, light theme, baselines in `__snapshots__/` (Linux only). Run with `just visual` (docker, pinned Playwright container) or via `.github/workflows/visual.yml`; regenerate with `just visual-update` or the `update_baselines` dispatch (artifact, then commit). Never generate baselines on macOS. Tolerance `MAX_DIFF_PIXEL_RATIO = 0.001`. Missing baseline: fails in CI, skips locally.

## Handoff references (`handoff.py`, `test_reference.py`, T-UT10)

References come from the designer handoff (`docs/design/rising-dough-frontend/`, frozen), not from the app.

- Never committed (ADR-0147 section 1): `tests/visual/reference/` is gitignored and rendered in the same job and pinned container as the app (the `reference` job of `visual.yml`, advisory until surfaces migrate; artifacts `visual-references`, `visual-reference-actual`). Rendering uses the OVERLAID handoff (`overlay.py`, data from `handoff_overlay.toml`).
- Render locally: `just visual-reference [surface]` (docker, pinned container; never on the host). Serves the handoff on 127.0.0.1, screenshots every page (106) at 1440 / 1024 / 375, light and dark (`?theme=`), animations frozen, browser clock fixed at 2026-10-31T10:00Z, fonts awaited, network idle. Output: `reference/<group>/<page>.<viewport>.<theme>.png`.
- Compare: `just test-visual --reference=handoff [surface]` (same container; surface: today, accounts, ledger, plan, settings, auth, errors, overlays). Renders the references first, then runs only `test_reference.py` for every surface. Expected red with the old app (T-UR00b red run) until each surface migrates.
- Fixture: the app side of `test_reference.py` uses the frozen server on the handoff seed (next section) at 2026-10-31 (`frozen_server.HANDOFF_FIXTURE_DATE`). `test_snapshots.py` (old-UI route baselines, removed per migrated surface) still serves a copy of `data/demo.sqlite`.

### Tolerance (max fraction of differing pixels)

| Comparison | Tolerance |
|---|---|
| handoff vs itself (any surface) | 0.05% (raster noise floor, observed <= 0.022% under load; most pages are exactly 0) |
| today | 2% |
| accounts | 2% |
| ledger | 3% |
| plan | 4% (SVG charts) |
| settings | 2% |
| auth | 1% |
| errors | 1% |
| overlays | 3% |

Different image sizes always fail (ratio 1.0). Values live in `handoff.SURFACE_TOLERANCE`; tighten as surfaces migrate.

### Bootstrap (before baselines exist)

`workflow_dispatch` only works once `visual.yml` is on `main`. Until baselines are committed, a PR run fails on every missing baseline, but each failing test still writes its actual screenshot to `__snapshots__/<route>.<width>.png`, and the workflow uploads that directory as the `visual-baselines` artifact (also on failure). Download it from the PR run and commit it. Later regenerations use the `update_baselines` dispatch or `just visual-update`.

## Handoff seed (`handoff_seed.py`, T-UR00b, ADR-0147 §3)

One base seed holds the handoff's entities at the frozen date 2026-10-31: 10 accounts (balances fitted to the handoff's figures; credit card with its 14,977.37 limit), 22 live categories plus 2 system ones (3 soft-deleted), 26 ledger rows (the 11 listed on the Ledger page plus per-category lump entries that give the budget page's spent figures), 3 live planned items (+1 deleted), 15 recurring rules (4 with the 19 % formula, 7 overrides), 13 budget defaults, income anchor Salary, users Ola and Ewa, a pending invite for accountant@example.test and the owner's Firefox session. Nothing is typed as a total: net worth, left per day and so on come from the app's services (`test_handoff_seed.py` pins them).

`build_seed(db_path, *, modifiers=())` migrates a fresh DB (it refuses an existing file), writes through the repositories and services with the clock frozen, and returns the dev session token. The `scratch_db` / `live_server` fixtures use it for `test_reference.py`; the `handoff_server(modifiers)` factory serves a modified seed for one state.

Modifiers (pure `SeedData -> SeedData` functions, `MODIFIER_NAMES`):

| Modifier | Effect |
|---|---|
| `empty` | Today `--empty`: no accounts, ledger, planned or recurring |
| `empty-accounts` | Accounts `--empty` (same data as `empty`) |
| `empty-ledger` | no transactions |
| `empty-planned` | no live planned items |
| `empty-recurring` | no rules or overrides |
| `long` | two 1,234,567.89 rows with a long description |
| `invite-expired` | the invite is 8 days old (link state expired) |
| `no-matches` | no data change: a filter query that matches nothing |
| `over-limit` | no data change: a 13,000.00 entry exceeds the card's 12,521.63 left |
| `form-error` | no data change: 422, wrong password and similar request states |

Values the seed cannot produce are not faked here; they are rows in `handoff_overlay.toml` (UR00bB, value-inventory section 5). Known today: tab counts 616 / 27 rules and per-account TXNS counts (the seed holds only the listed entries), committed 34.60 / left 1,399.93 / 199.99 per day / afford figures (the app also commits the overdue planned Annual insurance: 446.60 / 987.93 / 141.13), "checked 01 JUL" and "01 APR" for accounts with a reconciliation row, future-dated session and user times, the 21-category picker count, and the shared formula result 1,836.93.
