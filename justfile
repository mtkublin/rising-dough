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

# ONE-TIME prod DB seed (ADR-0099 exception d; runbook docs/plans/v3/runbooks/prod-db-seed.md).
# Reads data/budget.sqlite (read-only snapshot) and overwrites the prod VM DB. Needs --yes-i-own-prod-data.
prod-db-seed *args:
    @echo "################################################################"
    @echo "# WARNING: copies your LOCAL PROD DB onto the PRODUCTION VM.   #"
    @echo "# One-time operation. Requires explicit in-session user go.    #"
    @echo "################################################################"
    bash scripts/prod_db_seed.sh {{args}}

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
    uv run lint-imports
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
# Parallel via xdist (ADR-0108 §1); cap workers with PYTEST_WORKERS (orchestrator
# item agents use 2). PYTEST_WORKERS=0 runs serially.
test:
    uv run pytest -n "${PYTEST_WORKERS:-auto}" --dist loadgroup

# --- mutation testing + guards (ADR-0131, ADR-0130) --------------------------

# Mutation run over domain + services (advisory, never a gate). 20-35 min: run
# it in the background. PYTEST_WORKERS=2 keeps the test side light.
mutate:
    PYTEST_WORKERS=2 uv run mutmut run --max-children 4

# Scores per package + survivors by module, post-filtered (equivalent and
# low-value string mutants dropped). Pass --check to compare with the baseline.
mutate-report *args:
    uv run python scripts/mutate_report.py {{args}}

# Drop the mutmut workspace and results.
mutate-clean:
    rm -rf mutants .mutmut-cache

# Architecture guards (tests/architecture). Run in the pytest suite and CI.
guards:
    uv run pytest tests/architecture -q --no-cov

# Import-linter layering contracts (ADR-0130 §1).
lint-imports:
    uv run lint-imports

# Everything CI runs. Keep deterministic — no network except frankfurter mocks.
ci: lint typecheck test

# --- change-based inner loop (ADR-0108 §3) -----------------------------------
# Not a gate: merges and PRs still need the full `just ci` (ADR-0108 §4).
# BASE is the branch's parent: origin/main for feature branches, the main work
# branch for orchestrator item branches.

# pre-commit hooks over the files changed since the merge-base with BASE.
lint-changed BASE="origin/main":
    SKIP=pytest-fast uv run pre-commit run --from-ref "$(git merge-base HEAD {{BASE}})" --to-ref HEAD

# The one fallback list (ADR-0108 §3): reads paths on stdin, prints those
# testmon cannot see — every non-Python file except docs and Markdown
# (templates, static, SQL and migrations, dependencies, Terraform, scripts, CI
# config, test fixtures), plus any conftest.py.
_unseen-paths:
    @awk '/(^|\/)conftest\.py$/ { print; next } /^docs\// || /\.(py|md)$/ || /^$/ { next } { print }'

# No coverage: testmon does not record under it. Full suite instead when the
# diff against BASE touches a path testmon cannot see.
# Tests affected by changes since the last testmon run (pytest-testmon).
test-changed BASE="origin/main":
    #!/usr/bin/env bash
    set -euo pipefail
    base="$(git merge-base HEAD {{BASE}})"
    unseen="$( { git diff --name-only "$base"; git ls-files --others --exclude-standard; } | sort -u | just _unseen-paths)"
    workers="${PYTEST_WORKERS:-auto}"
    if [ -n "$unseen" ]; then
      echo "[test-changed] change testmon cannot see vs {{BASE}}; running the full suite:"
      printf '%s\n' "$unseen" | sed 's/^/  /'
      exec uv run pytest -n "$workers" --no-cov --testmon-noselect
    fi
    set +e
    uv run pytest -n "$workers" --no-cov --testmon-forceselect
    status=$?
    set -e
    # 5 = nothing selected: no affected tests is a pass.
    if [ "$status" -eq 5 ]; then echo "[test-changed] no affected tests"; exit 0; fi
    exit "$status"

# Fallback: staged files on _unseen-paths run the full default selection.
# Pre-commit pytest hook, the local gate (ADR-0120): testmon-selected tests.
test-fast:
    #!/usr/bin/env bash
    set -euo pipefail
    unseen="$(git diff --cached --name-only | just _unseen-paths)"
    mode="--testmon-forceselect"
    if [ -n "$unseen" ]; then
      echo "[test-fast] staged change testmon cannot see; running the full suite:"
      printf '%s\n' "$unseen" | sed 's/^/  /'
      mode="--testmon-noselect"
    fi
    set +e
    uv run pytest -q -n "${PYTEST_WORKERS:-auto}" --no-cov "$mode"
    status=$?
    set -e
    # 5 = nothing selected: no affected tests is a pass.
    [ "$status" -eq 5 ] && exit 0
    exit "$status"

# Stale data only adds tests, never drops them.
# Seed a new worktree's .testmondata from the main checkout.
worktree-init:
    #!/usr/bin/env bash
    set -euo pipefail
    main="$(cd "$(git rev-parse --git-common-dir)/.." && pwd)"
    if [ "$main" = "$(pwd)" ]; then echo "[worktree-init] already in the main checkout"; exit 0; fi
    if [ -f "$main/.testmondata" ]; then
      cp "$main/.testmondata" .testmondata
      echo "[worktree-init] copied .testmondata from $main"
    else
      echo "[worktree-init] no .testmondata in $main; the first test-changed runs everything"
    fi

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

# T-D77: render the cloud-init user-data offline (real templatefile chain, dummy
# values, no credentials) and lint it: line 1, YAML, cloud-init schema (skipped
# with a message when the binary is missing).
tf-render-check:
    terraform -chdir=terraform init -backend=false -input=false
    terraform -chdir=terraform test
    uv run python terraform/tests/render/render_check.py

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

# --- masked terraform plan (T-D83) -------------------------------------------

# Terraform plan with secret-looking tokens masked (ADR-0098); cloud_init embeds
# secrets and the prior state value can print unmasked. Extra args pass through
# the env's tfvars file selection, e.g. `just tf-plan-safe drill`.
# Usage: just tf-plan-safe drill|prod
tf-plan-safe env:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -f terraform/.env ]; then set -a; source terraform/.env; set +a; fi
    cd terraform
    terraform init -input=false -backend-config=envs/{{env}}/backend.hcl -reconfigure >/dev/null
    terraform plan -no-color -input=false -var-file=envs/{{env}}/terraform.tfvars | python3 scripts/mask_plan.py
