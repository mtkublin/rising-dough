#!/usr/bin/env bash
# shellcheck shell=bash
#
# seed-demo — drill-only helper (T-Q306(c), ADR-0149 Decision section 4).
# Rendered by Terraform and installed ONLY on the `drill` environment at
# /usr/local/bin/seed-demo (see terraform/modules/compute/user_data.tf), like
# restore-from-prod, but without any prod credential: the DB comes from a file the
# workflow copied onto the host, never from a replica.
#
# Called by the drill workflow, after copying the anonymized demo DB
# (data/demo.sqlite from the baseline tag) onto the host over the tailnet:
#   scp data/demo.sqlite operator@<drill-host>:/tmp/seed-demo.sqlite
#   ssh operator@<drill-host> 'sudo /usr/local/bin/seed-demo /tmp/seed-demo.sqlite'
#
# Argument: ONE absolute path to a regular, non-symlink SQLite file (recommended:
# /tmp/seed-demo.sqlite). The source is deleted on success.
#
# What it does:
#   1. stops app + litestream (caddy stays up so /ready is reachable),
#   2. moves the drill host's local DB (db, -wal, -shm, litestream meta dir) aside,
#   3. copies the demo DB to /data/budget.db,
#   4. runs PRAGMA integrity_check (aborts if not "ok"),
#   5. chowns to the app uid 10001,
#   6. starts litestream (new generation of the seeded DB), then app (the image
#      entrypoint applies pending migrations), and waits for /ready to report
#      {"status":"ready","db":"ok"},
#   7. on EXIT deletes the moved-aside copies so the host keeps no extra *.db* files.
#
# SAFETY: this script never reads restore-source.env or the prod age identity and
# never talks to any bucket. The long-running litestream service replicates the seeded
# DB to the DRILL bucket only.
#
# Terraform template variables:
#   ${compose_dir} — dir holding docker-compose.yml (/etc/budget-planner).
#   ${hostname}    — the host's real name (Caddy certificate SNI) for the /ready probe.
#
# Shell-side variables use the `$${…}` escape so Terraform leaves them alone.

set -Eeuo pipefail
IFS=$'\n\t'

readonly PROGNAME='seed-demo'
readonly COMPOSE_DIR='${compose_dir}'
readonly COMPOSE_FILE="$${COMPOSE_DIR}/docker-compose.yml"
readonly DATA_DIR='/data'
readonly DB_PATH="$${DATA_DIR}/budget.db"
readonly APP_UID=10001
readonly READY_HOST='${hostname}'
readonly READY_URL="https://$${READY_HOST}/ready"
readonly READY_RETRIES=24
readonly READY_SLEEP_S=5
SOURCE_DB=''
MOVED_ASIDE_DIR=''

log() { printf '%s: %s\n' "$${PROGNAME}" "$${*}"; }
die() { printf '%s: ERROR: %s\n' "$${PROGNAME}" "$${*}" >&2; exit 1; }

cleanup_copies() {
  local rc=$?
  set +e
  if [[ -n "$${MOVED_ASIDE_DIR}" && -d "$${MOVED_ASIDE_DIR}" ]]; then
    rm -rf -- "$${MOVED_ASIDE_DIR}"
    log "deleted moved-aside copies $${MOVED_ASIDE_DIR}"
  fi
  if [[ "$${rc}" -eq 0 && -n "$${SOURCE_DB}" ]]; then
    rm -f -- "$${SOURCE_DB}"
  fi
  exit "$${rc}"
}

compose() { docker compose -f "$${COMPOSE_FILE}" "$${@}"; }

preflight() {
  [[ "$#" -eq 1 ]] || die "usage: seed-demo <absolute path to the demo sqlite file>"
  SOURCE_DB="$${1}"
  [[ "$(id -u)" -eq 0 ]] || die "must run as root (use sudo)"
  command -v docker >/dev/null || die "docker not found"
  command -v sqlite3 >/dev/null || die "sqlite3 not found"
  command -v jq >/dev/null || die "jq not found"
  [[ -f "$${COMPOSE_FILE}" ]] || die "missing $${COMPOSE_FILE}"
  [[ "$${SOURCE_DB}" == /* ]] || die "demo DB path must be absolute: $${SOURCE_DB}"
  [[ ! -L "$${SOURCE_DB}" && -f "$${SOURCE_DB}" && -s "$${SOURCE_DB}" ]] \
    || die "demo DB is not a non-empty regular file: $${SOURCE_DB}"
  case "$${SOURCE_DB}" in
    "$${DATA_DIR}"/*) die "demo DB must not live under $${DATA_DIR}: $${SOURCE_DB}" ;;
  esac
}

stop_stack() {
  log "stopping app + litestream"
  compose stop app
  # Give litestream a moment to flush the (empty) drill WAL before stopping.
  sleep 5
  compose stop litestream
}

move_local_db_aside() {
  local dest
  dest="$${DATA_DIR}/pre-seed-$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p -- "$${dest}"
  MOVED_ASIDE_DIR="$${dest}"
  find "$${DATA_DIR}" -maxdepth 1 \
    \( -name 'budget.db*' -o -name '.budget.db-litestream' \) \
    -exec mv -t "$${dest}" -- {} +
  log "moved previous local DB files to $${dest}"
}

install_demo_db() {
  cp -- "$${SOURCE_DB}" "$${DB_PATH}"
  log "installed $${SOURCE_DB} as $${DB_PATH}"
}

verify_and_chown() {
  local result
  result="$(sqlite3 "$${DB_PATH}" 'PRAGMA integrity_check;')"
  log "integrity_check=$${result}"
  [[ "$${result}" == "ok" ]] || die "integrity_check failed; leaving stack stopped"
  chown "$${APP_UID}:$${APP_UID}" "$${DATA_DIR}"
  chmod 0700 "$${DATA_DIR}"
  find "$${DATA_DIR}" -maxdepth 1 -name 'budget.db*' -exec chown "$${APP_UID}:$${APP_UID}" {} +
  chmod 0600 "$${DB_PATH}"
}

start_stack_and_wait() {
  log "starting litestream, then app (entrypoint applies pending migrations)"
  compose up -d litestream
  compose up -d app
  local i body status db err
  err="no attempt made"
  for i in $(seq 1 "$${READY_RETRIES}"); do
    if body="$(curl -fsS --max-time 5 --resolve "$${READY_HOST}:443:127.0.0.1" "$${READY_URL}" 2>&1)"; then
      status="$(jq -r '.status // empty' <<<"$${body}" 2>/dev/null || true)"
      db="$(jq -r '.db // empty' <<<"$${body}" 2>/dev/null || true)"
      if [[ "$${status}" == "ready" && "$${db}" == "ok" ]]; then
        log "ready.status=$${status} ready.db=$${db} (attempt $${i})"
        return 0
      fi
      err="unexpected body: $${body:0:200}"
    else
      err="curl: $${body:0:200}"
    fi
    log "ready attempt $${i}/$${READY_RETRIES} failed: $${err}"
    sleep "$${READY_SLEEP_S}"
  done
  die "/ready did not report status=ready db=ok within $((READY_RETRIES * READY_SLEEP_S))s (last: $${err})"
}

main() {
  local started
  started="$(date +%s)"
  trap cleanup_copies EXIT
  preflight "$${@}"
  stop_stack
  move_local_db_aside
  install_demo_db
  verify_and_chown
  start_stack_and_wait
  log "seed complete in $(( $(date +%s) - started ))s"
}

main "$${@}"
