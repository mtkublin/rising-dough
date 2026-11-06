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
    echo "[dev] open http://localhost:8000 (passkeys do not work on an IP address)"
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

# Set a user's password (operator tool, ADR-0069 §4). `--db=<path>` is
# REQUIRED — there is no default DB, so this never hits prod by accident.
# Prompts for the password twice. Examples:
#   just set-password --db=/tmp/scratch.sqlite --email=admin@local.test
#   just set-password --db=data/budget.sqlite --user-id=1 --set-email=me@example.com --make-admin
# Other flags: --must-change-password, --password-stdin.
set-password *args:
    #!/usr/bin/env bash
    set -eu
    case " {{args}} " in
      *" --db="*) ;;
      *) echo "[set-password] --db=<path> is required (no default DB)" >&2; exit 2 ;;
    esac
    uv run python -m budget_planner.cli.set_password {{args}}

# --- container -------------------------------------------------------------

# Build the production OCI image locally (multi-stage, non-root). See T-D10
# and ADR-0032 §2 for the image contract. Requires a running Docker daemon.
docker-build:
    docker build -t rising-dough:dev .

# --- security --------------------------------------------------------------

# T-D13 — local mirror of .github/workflows/security.yml. Requires `trivy`
# installed on PATH (brew install aquasecurity/trivy/trivy) and a local
# Docker daemon for the image scan. The CI workflow is the source of truth;
# this recipe is for pre-push sanity checks.
security-scan:
    uv run pip-audit --strict
    docker build -t rising-dough:scan .
    trivy fs . --severity HIGH,CRITICAL --exit-code 1
    trivy image rising-dough:scan --severity HIGH,CRITICAL --exit-code 1

# --- prod-sim --------------------------------------------------------------

# Boot the full prod-sim compose stack (app + caddy + litestream + minio),
# wait for /ready via Caddy's self-signed TLS endpoint, run a smoke probe,
# tear everything down (volumes included) even on failure.
#
# See docker-compose.yml for the service shapes and ADR-0032 §2,
# ADR-0034, ADR-0036 for the production references.
test-prod-stack:
    #!/usr/bin/env bash
    set -euo pipefail
    teardown() {
      echo "[test-prod-stack] tearing down..."
      docker compose -f docker-compose.yml down -v --remove-orphans >/dev/null 2>&1 || true
    }
    trap teardown EXIT
    echo "[test-prod-stack] building images..."
    docker compose -f docker-compose.yml build
    echo "[test-prod-stack] starting stack..."
    docker compose -f docker-compose.yml up -d
    echo "[test-prod-stack] waiting for /ready via https://localhost:8443 ..."
    for attempt in $(seq 1 12); do
      if curl -k -fsS -o /dev/null -w "%{http_code}" https://localhost:8443/ready | grep -q '^200$'; then
        echo "[test-prod-stack] /ready → 200 (attempt $attempt)"
        break
      fi
      if [ "$attempt" -eq 12 ]; then
        echo "[test-prod-stack] /ready never returned 200; dumping logs" >&2
        docker compose -f docker-compose.yml ps >&2 || true
        docker compose -f docker-compose.yml logs --tail=200 >&2 || true
        exit 1
      fi
      sleep 5
    done
    echo "[test-prod-stack] running smoke probe (Playwright journey ships with T-D43)..."
    uv run python -c "import httpx; r = httpx.get('https://localhost:8443/ready', verify=False); assert r.status_code == 200"
    echo "[test-prod-stack] OK"

# --- terraform preflight (T-D78) --------------------------------------------

# Read-only checks before a terraform apply: inputs, project match, GHCR image,
# Tailscale tag, state backend. Usage: just tf-preflight drill|prod
tf-preflight env:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -f terraform/.env ]; then set -a; source terraform/.env; set +a; fi
    if [ "{{env}}" = "drill" ] && [ -n "${SCW_DRILL_PROJECT_ID:-}" ]; then
      export SCW_DEFAULT_PROJECT_ID="$SCW_DRILL_PROJECT_ID"
    fi
    uv run python terraform/scripts/preflight.py {{env}}

# Preflight for the drill env. Run before every drill apply.
drill-preflight:
    just tf-preflight drill
