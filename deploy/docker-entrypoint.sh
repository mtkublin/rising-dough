#!/bin/sh
# Rising Dough v3 — app container entrypoint (T-D19a, ADR-0071).
#
# 1. Apply pending DB migrations (idempotent; pre-migration backup under
#    <db dir>/backups when an existing DB is upgraded). A non-zero exit
#    aborts the start, so uvicorn never serves a half-migrated schema.
# 2. exec the CMD so uvicorn is PID 1 and receives SIGTERM directly
#    (graceful shutdown, T-D15 / ADR-0034 §6).
set -eu

python -m budget_planner.db.startup_migrate

exec "$@"
