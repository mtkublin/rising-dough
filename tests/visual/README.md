# Visual regression

Opt-in suites (not part of `just ci`). ADR-0027 section 4, amended by ADR-0106.

## Route snapshots (`test_snapshots.py`, T-Q251)

Eight routes x 375/1024/1440, light theme, baselines in `__snapshots__/` (Linux only). Run with `just visual` (docker, pinned Playwright container) or via `.github/workflows/visual.yml`; regenerate with `just visual-update` or the `update_baselines` dispatch (artifact, then commit). Never generate baselines on macOS. Tolerance `MAX_DIFF_PIXEL_RATIO = 0.001`. Missing baseline: fails in CI, skips locally.

## Handoff references (`handoff.py`, `test_reference.py`, T-UT10)

References come from the designer handoff (`docs/design/rising-dough-frontend/`, frozen), not from the app.

- Regenerate: `just visual-reference [surface]` (`--committed` limits it to the committed subset). Serves the handoff on 127.0.0.1, screenshots every page at 1440 / 1024 / 375, light and dark (`?theme=`), animations frozen, browser clock fixed at 2026-10-31T10:00Z, fonts awaited, network idle. Output: `reference/<group>/<page>.<viewport>.<theme>.png`.
- Compare: `just test-visual --reference=handoff [surface]` (surface: today, accounts, ledger, plan, settings, auth, errors, overlays; or `--surface=`). Runs only the reference tests.
- Committed subset (size budget, ~13 MB): non-overlay pages at 1440 and 375. Overlays and 1024 are gitignored; tests skip missing images, run `just visual-reference` to get them (full set 546 images, ~68 MB).
- Fixture: the app side uses the frozen server on `data/demo.sqlite` at 2026-10-31 (`frozen_server.HANDOFF_FIXTURE_DATE`); the handoff sample data (period 7 Oct to 7 Nov, day 25 of 31) was drawn from that DB on that day. The app comparison (`test_app_matches_handoff`) is off until a surface is added to `MIGRATED_SURFACES` in `test_reference.py` (ADR-0107 migration).

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
