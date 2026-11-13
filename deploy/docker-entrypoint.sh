#!/bin/sh
# Rising Dough v3 — app container entrypoint (T-D19a, ADR-0071).
#
# 1. Apply pending DB migrations (idempotent; pre-migration backup under
#    <db dir>/backups when an existing DB is upgraded). A non-zero exit
#    aborts the start, so uvicorn never serves a half-migrated schema.
# 2. Run the retention purge (T-D60; non-fatal).
# 3. exec the CMD so uvicorn is PID 1 and receives SIGTERM directly
#    (graceful shutdown, T-D15 / ADR-0034 §6).
set -eu

python -m budget_planner.db.startup_migrate

# T-D60 / ADR-0078 §7: purge IP / user-agent data past retention. Non-fatal:
# a failure is logged by the module and the app still starts.
python -m budget_planner.db.retention || echo "retention purge failed (non-fatal)" >&2

exec "$@"
