# Budget Planner — developer commands.
# Discoverable via `just --list`.

set shell := ["bash", "-cu"]
set dotenv-load := true

# --- environment -----------------------------------------------------------

# Install runtime + dev deps from the pinned uv.lock, install pre-commit
# hooks + Node dev toolchain. `--frozen` fails if the lock drifts from
# pyproject.toml so local installs mirror CI exactly (T-D12).
install:
    uv sync --frozen --group dev
    uv run pre-commit install --install-hooks
    npm ci

# Install only the pre-commit hooks (no dependency sync).
install-hooks:
    uv run pre-commit install --install-hooks

# --- dev loop --------------------------------------------------------------

# Run FastAPI with hot reload. Binds 127.0.0.1 per ADR-0005.
#
# Optional flag: --db=<path> switches BUDGET_DATABASE_URL to the given
# SQLite file. Default is data/budget.sqlite (treated as prod — see
# CLAUDE.md "Databases"). Examples:
#   just dev                              # prod DB
#   just dev --db=data/demo.sqlite        # demo DB
#   just dev --db=/tmp/scratch.sqlite     # ad-hoc throwaway
dev *args:
    #!/usr/bin/env bash
    set -eu
    DB_PATH=""
    for a in {{args}}; do
      case "$a" in
        --db=*) DB_PATH="${a#--db=}" ;;
        *) echo "[dev] unknown arg: $a" >&2; exit 2 ;;
      esac
    done
    if [ -n "$DB_PATH" ]; then
      export BUDGET_DATABASE_URL="sqlite:///$DB_PATH"
      echo "[dev] BUDGET_DATABASE_URL=$BUDGET_DATABASE_URL"
    else
      echo "[dev] using default DB (data/budget.sqlite — prod)"
    fi
    uv run uvicorn budget_planner.web.app:app \
      --reload --host 127.0.0.1 --port 8000

# Shortcut for the demo DB. Run `just demo-build` first to materialize it.
dev-demo:
    just dev --db=data/demo.sqlite

# (Re)build the anonymized demo DB from the prod DB. Non-destructive to
# prod — reads data/budget.sqlite, writes data/demo.sqlite.
demo-build:
    uv run python data/scripts/build_demo_db.py \
      --from data/budget.sqlite --to data/demo.sqlite --force

# Build Tailwind CSS once (purged + minified) → static/tailwind.css. See ADR-0027.
css:
    npm run css

# Rebuild Tailwind on save; run alongside `just dev`.
css-watch:
    npm run css:watch

# Run Playwright visual-regression snapshot suite. Opt-in; not part of `just ci`.
test-visual:
    uv run pytest tests/visual -m visual --override-ini="addopts=-ra --strict-config --strict-markers" --no-cov

# Refresh visual-regression baselines after an intentional design change.
test-visual-update:
    VISUAL_UPDATE=1 uv run pytest tests/visual -m visual --override-ini="addopts=-ra --strict-config --strict-markers" --no-cov

# --- quality gates ---------------------------------------------------------

# Run all linters: ruff, sqlfluff, djlint.
# djlint exits 2 when the target directory is empty (Phase 0 reality); tolerate
# that specific "no files" message so pre-Phase-3 CI stays green. Any real
# lint error still fails because the string check only matches the empty case.
lint:
    uv run ruff check src tests
    uv run sqlfluff lint migrations
    out=$(uv run djlint src/budget_planner/web/templates --check 2>&1); status=$?; if [ $status -ne 0 ] && ! echo "$out" | grep -q "No files to check"; then echo "$out" >&2; exit $status; fi; echo "$out"
    npm run stylelint --silent

# Auto-fix formatting + simple lint issues.
format:
    uv run ruff format src tests
    uv run ruff check src tests --fix
    uv run sqlfluff fix migrations
    out=$(uv run djlint src/budget_planner/web/templates --reformat 2>&1); status=$?; if [ $status -ne 0 ] && ! echo "$out" | grep -q "No files to check"; then echo "$out" >&2; exit $status; fi; echo "$out"

# mypy --strict over the package + tests.
typecheck:
    uv run mypy src tests

# Full pytest suite with coverage. 90% gate wired here and in CI.
test:
    uv run pytest

# Everything CI runs. Keep deterministic — no network except frankfurter mocks.
ci: lint typecheck test

# --- database --------------------------------------------------------------

# Apply all pending SQL migrations. Implemented in Phase 1 (T-010).
migrate:
    uv run python -m budget_planner.db.migrate

# Seed system data (default categories, demo accounts). Implemented in Phase 1 (T-012).
seed:
    uv run python -m budget_planner.db.seed

# Nuke and recreate the dev DB from scratch. Destructive.
db-reset:
    rm -f data/budget.sqlite data/budget.sqlite-wal data/budget.sqlite-shm
    just migrate
    just seed
