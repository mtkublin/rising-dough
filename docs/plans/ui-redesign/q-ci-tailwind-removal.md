# Operator edit: Tailwind steps in `.github/workflows/ci.yml` (T-UR15d)

Applied 2026-11-28 by WFPATCH (no change needed: ci.yml already had no Tailwind step and the Node step already says stylelint; the `css` npm script is gone).

Done 2026-11-26 (CI1): the Tailwind build step is deleted, the Node step is renamed to stylelint, the pre-commit comment is fixed, and the `css` npm script is removed from `package.json` (no other caller).

The agent token cannot push `.github/workflows/*`, so `ci.yml` is unchanged. It still works after UR15d:

- `npm ci` runs against the slimmed `package-lock.json` (Tailwind removed; stylelint, stylelint-config-standard, pixelmatch, pngjs stay for the rd CSS).
- `npm run css` now runs `uv run python scripts/build_css_bundle.py` (the rd bundle; a no-change rebuild).
- The pre-commit step no longer has `tailwind-check` or the old `stylelint` hook; `stylelint-rd` and `css-bundle-check` stay.

## Edit to make (optional clean-up, no urgency)

In `.github/workflows/ci.yml`:

1. Delete the step "Build Tailwind CSS (verifies the pre-commit tailwind-check contract)" (`run: npm run css`). The `css-bundle-check` hook already verifies the bundle.
2. Rename the step "Set up Node (dev-only toolchain — Tailwind + stylelint; ADR-0027)" to "... stylelint ...".
3. Fix the comment above "Cache pre-commit environments": drop "Runs before the Tailwind build so the tailwind-check hook sees the committed CSS" and "stylelint/tailwind-check use the npm toolchain" (only stylelint uses npm).
4. Once step 1 is done, the `css` npm script in `package.json` can go (it exists only for that step).

Other workflows (`e2e.yml`, `visual.yml`) call no npm or Tailwind step.
