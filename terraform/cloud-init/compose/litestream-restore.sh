#!/bin/sh
# T-D156 / ADR-0122: entrypoint of the one-shot litestream-restore service.
# Written verbatim by the host agent (ADR-0111); no Terraform templating.
#
# Runs before app and litestream (compose depends_on). When the database is
# missing it is restored from the replica. A missing replica is an error unless
# LITESTREAM_ALLOW_EMPTY_DB=true (drill, or a reviewed first-ever prod boot):
# otherwise the app would migrate an empty database and Litestream would
# replicate it as a new generation. Every outcome is written to the report the
# host agent publishes.
set -eu

DATA_DIR="${LITESTREAM_DATA_DIR:-/data}"
DB="$DATA_DIR/budget.db"
CONFIG="${LITESTREAM_CONFIG:-/etc/litestream.yml}"
KEY_FILE="${LITESTREAM_AGE_KEY_FILE:-/run/litestream-age.key}"
REPORT="$DATA_DIR/restore-report.json"
APP_UID="${APP_UID:-10001}"
APP_GID="${APP_GID:-$APP_UID}"
ALLOW_EMPTY_DB="${LITESTREAM_ALLOW_EMPTY_DB:-false}"

log() { echo "litestream-restore: $*" >&2; }

report() {
  # $1 = restored|empty|skipped-db-present, $2 = generation or empty.
  printf '{"result":"%s","generation":"%s","at":"%s"}\n' \
    "$1" "$2" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$REPORT.tmp"
  mv "$REPORT.tmp" "$REPORT"
}

hand_back() {
  chown "$APP_UID:$APP_GID" "$DATA_DIR"
  chmod 0700 "$DATA_DIR"
  find "$DATA_DIR" -maxdepth 1 -name 'budget.db*' -exec chown "$APP_UID:$APP_GID" {} +
}

if [ -e "$DB" ]; then
  log "database present, nothing to restore"
  # Every `compose up` re-runs this service; keep the report of how this
  # host's database came to be (restored or empty) instead of overwriting it.
  [ -e "$REPORT" ] || report skipped-db-present ""
  hand_back
  exit 0
fi

if [ ! -r "$KEY_FILE" ]; then
  log "age identity file $KEY_FILE missing"
  exit 1
fi
LITESTREAM_AGE_IDENTITY="$(grep -m1 '^AGE-SECRET-KEY-' "$KEY_FILE" || true)"
if [ -z "$LITESTREAM_AGE_IDENTITY" ]; then
  log "no AGE-SECRET-KEY line in $KEY_FILE"
  exit 1
fi
export LITESTREAM_AGE_IDENTITY

# Litestream 0.3.14 semantics (checked against its source): `restore` exits
# non-zero when the replica cannot be listed or read, and with "no matching
# backups found" when it has no generation. (`generations` cannot be used here:
# it stats the database first and fails when the file is missing.)
out="$(mktemp)"
trap 'rm -f "$out"' EXIT

if litestream restore -config "$CONFIG" "$DB" > "$out" 2>&1; then
  cat "$out" >&2
  if [ ! -s "$DB" ]; then
    log "restore finished but $DB is missing or empty"
    exit 1
  fi
  generation="$(grep -o 'generation=[0-9a-f]*' "$out" | head -n 1 | cut -d= -f2 || true)"
  log "restored generation ${generation:-unknown}"
  report restored "$generation"
  hand_back
  exit 0
fi

cat "$out" >&2
if grep -q 'no matching backups found' "$out"; then
  if [ "$ALLOW_EMPTY_DB" = "true" ]; then
    log "no replica generation; starting empty (allow_empty_db)"
    report empty ""
    hand_back
    exit 0
  fi
  log "database missing and the replica has no generation; refusing to start empty (set allow_empty_db for a first boot, ADR-0122)"
  exit 1
fi
log "restore failed"
exit 1
