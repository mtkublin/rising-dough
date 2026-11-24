#!/usr/bin/env bash
# Runs the visual suite inside the pinned Playwright container (ADR-0027
# amendment 2026-11-22, T-Q251). Used by .github/workflows/visual.yml and by
# `just visual` / `just visual-update`. Usage: visual_in_container.sh [update]
set -euo pipefail

pip install --quiet --break-system-packages "uv==0.11.2"
export UV_PYTHON_PREFERENCE=only-system
uv sync --group dev --frozen

if [ "${1:-}" = "reference" ]; then
  shift
  # The `references` fixture renders tests/visual/reference/ first, in this container
  # (only the shard's width:theme with --reference-shard=<viewport>:<theme>, T-UR00b).
  # One summary line per run: pass/fail counts and wall time.
  log="$(mktemp)"
  start=$SECONDS
  if uv run pytest tests/visual/test_reference.py -m visual --reference=handoff "$@" \
    --override-ini="addopts=-ra --strict-config --strict-markers" --no-cov -p no:cacheprovider \
    2>&1 | tee "$log"; then rc=0; else rc=$?; fi
  line="reference shard ${REFERENCE_SHARD_LABEL:-all}: $(tail -n 1 "$log") (wall $((SECONDS - start))s, rc=$rc)"
  echo "$line"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then echo "- $line" >> "$GITHUB_STEP_SUMMARY"; fi
  exit "$rc"
fi
if [ "${1:-}" = "update" ]; then
  export VISUAL_UPDATE=1
fi
exec uv run pytest tests/visual/test_snapshots.py -m visual \
  --override-ini="addopts=-ra --strict-config --strict-markers" --no-cov -p no:cacheprovider
