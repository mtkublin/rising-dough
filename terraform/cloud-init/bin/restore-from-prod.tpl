#!/usr/bin/env bash
# shellcheck shell=bash
#
# restore-from-prod — restore-drill helper (T-D41a, ADR-0034 §5, ADR-0071).
# Rendered by Terraform and installed ONLY on the `drill` environment at
# /usr/local/bin/restore-from-prod (see terraform/modules/compute/user_data.tf).
# Called by .github/workflows/restore-drill.yml as
#   ssh operator@<drill-host> 'sudo /usr/local/bin/restore-from-prod'
#
# What it does:
#   1. stops app + litestream (caddy stays up so /ready is reachable),
#   2. moves the drill host's local DB (db, -wal, -shm, litestream meta dir) aside,
#   3. `litestream restore`s the latest state of the PROD replica into /data,
#   4. runs PRAGMA integrity_check (aborts if not "ok"),
#   5. chowns to the app uid 10001 (same as the compose litestream-restore service),
#   6. starts litestream + app (the image entrypoint applies pending migrations,
#      ADR-0071) and waits for /ready to report {"status":"ok"}.
#
# PROD SAFETY (the drill host must never write to the prod replica):
#   * The prod replica is only ever referenced in the throw-away config written
#     below, and that config is only passed to `litestream restore`, which is a
#     read-only operation. It is never given to `litestream replicate`.
#   * It uses the dedicated READ-ONLY credential (scw_access_key_restore /
#     scw_secret_key_restore) from ${restore_env_file}, never the drill's own
#     write key from litestream.env.
#   * The long-running litestream service reads /etc/budget-planner/litestream.yml,
#     which targets the DRILL bucket only; after the restore it replicates the
#     restored DB to the drill bucket as a new generation.
#   * The script refuses to run if the source bucket equals the drill bucket or
#     if the read-only key equals the drill's write key.
#
# Terraform template variables:
#   ${compose_dir}      — dir holding docker-compose.yml (/etc/budget-planner).
#   ${restore_env_file} — root-only env file with RESTORE_ACCESS_KEY_ID / RESTORE_SECRET_ACCESS_KEY.
#   ${source_bucket}    — PROD replica bucket (read-only).
#   ${source_path}      — replica path inside the bucket (db).
#   ${source_endpoint}  — S3 endpoint of the prod bucket.
#   ${source_region}    — region of the prod bucket.
#   ${drill_bucket}     — this drill environment's own bucket.
#
# Shell-side variables use the `$${…}` escape so Terraform leaves them alone.

set -Eeuo pipefail
IFS=$'\n\t'

readonly PROGNAME='restore-from-prod'
readonly COMPOSE_DIR='${compose_dir}'
readonly COMPOSE_FILE="$${COMPOSE_DIR}/docker-compose.yml"
readonly RESTORE_ENV_FILE='${restore_env_file}'
readonly WRITE_ENV_FILE="$${COMPOSE_DIR}/litestream.env"
readonly SOURCE_BUCKET='${source_bucket}'
readonly DRILL_BUCKET='${drill_bucket}'
readonly DATA_DIR='/data'
readonly DB_PATH="$${DATA_DIR}/budget.db"
readonly APP_UID=10001
readonly LITESTREAM_IMAGE='litestream/litestream:0.3'
readonly READY_URL='https://localhost/ready'
readonly READY_RETRIES=24
readonly READY_SLEEP_S=5

log() { printf '%s: %s\n' "$${PROGNAME}" "$${*}"; }
die() { printf '%s: ERROR: %s\n' "$${PROGNAME}" "$${*}" >&2; exit 1; }

compose() { docker compose -f "$${COMPOSE_FILE}" "$${@}"; }

preflight() {
  [[ "$(id -u)" -eq 0 ]] || die "must run as root (use sudo)"
  command -v docker >/dev/null || die "docker not found"
  command -v sqlite3 >/dev/null || die "sqlite3 not found"
  command -v jq >/dev/null || die "jq not found"
  [[ -f "$${COMPOSE_FILE}" ]] || die "missing $${COMPOSE_FILE}"
  [[ -r "$${RESTORE_ENV_FILE}" ]] || die "missing $${RESTORE_ENV_FILE}"
  [[ -n "$${SOURCE_BUCKET}" ]] || die "source bucket is empty"
  [[ "$${SOURCE_BUCKET}" != "$${DRILL_BUCKET}" ]] \
    || die "source bucket equals drill bucket ($${SOURCE_BUCKET}); refusing"
}

load_restore_credentials() {
  # shellcheck disable=SC1090
  source "$${RESTORE_ENV_FILE}"
  [[ -n "$${RESTORE_ACCESS_KEY_ID:-}" && -n "$${RESTORE_SECRET_ACCESS_KEY:-}" ]] \
    || die "read-only restore credential is empty in $${RESTORE_ENV_FILE} (set scw_access_key_restore / scw_secret_key_restore)"
  if [[ -r "$${WRITE_ENV_FILE}" ]] \
    && grep -qxF "SCW_ACCESS_KEY=$${RESTORE_ACCESS_KEY_ID}" "$${WRITE_ENV_FILE}"; then
    die "restore key equals the drill write key; use the dedicated read-only prod key"
  fi
  export RESTORE_ACCESS_KEY_ID RESTORE_SECRET_ACCESS_KEY
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
  dest="$${DATA_DIR}/pre-restore-$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p -- "$${dest}"
  # db + -wal + -shm + litestream's local metadata dir (stale generation state).
  find "$${DATA_DIR}" -maxdepth 1 \
    \( -name 'budget.db*' -o -name '.budget.db-litestream' \) \
    -exec mv -t "$${dest}" -- {} +
  log "moved previous local DB files to $${dest}"
}

restore_from_prod() {
  local cfg
  cfg="$(mktemp /run/restore-source.XXXXXX.yml)"
  trap 'rm -f -- "$${cfg}"' RETURN
  # Restore-only config: points at the PROD replica, read-only credential.
  # Never passed to `litestream replicate`. Credentials are expanded by
  # litestream from the container environment, not stored in this file.
  cat > "$${cfg}" <<'CFG'
dbs:
  - path: /data/budget.db
    replicas:
      - type: s3
        endpoint: ${source_endpoint}
        region: ${source_region}
        bucket: ${source_bucket}
        path: ${source_path}
        access-key-id: $${RESTORE_ACCESS_KEY_ID}
        secret-access-key: $${RESTORE_SECRET_ACCESS_KEY}
CFG
  log "restoring from s3://$${SOURCE_BUCKET}/${source_path} (read-only)"
  docker run --rm \
    -v "$${DATA_DIR}:$${DATA_DIR}:rw" \
    -v "$${cfg}:/etc/litestream-restore.yml:ro" \
    -e RESTORE_ACCESS_KEY_ID -e RESTORE_SECRET_ACCESS_KEY \
    "$${LITESTREAM_IMAGE}" \
    restore -config /etc/litestream-restore.yml -o "$${DB_PATH}" "$${DB_PATH}"
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
  log "starting litestream + app (entrypoint applies pending migrations)"
  compose up -d litestream app
  local i body status
  for i in $(seq 1 "$${READY_RETRIES}"); do
    if body="$(curl -fsS --max-time 5 --resolve 'localhost:443:127.0.0.1' -k "$${READY_URL}" 2>/dev/null)"; then
      status="$(jq -r .status <<<"$${body}")"
      if [[ "$${status}" == "ok" ]]; then
        log "ready.status=$${status} (attempt $${i})"
        return 0
      fi
    fi
    sleep "$${READY_SLEEP_S}"
  done
  die "/ready did not report ok within $((READY_RETRIES * READY_SLEEP_S))s"
}

main() {
  local started
  started="$(date +%s)"
  preflight
  load_restore_credentials
  stop_stack
  move_local_db_aside
  restore_from_prod
  verify_and_chown
  start_stack_and_wait
  log "restore complete in $(( $(date +%s) - started ))s"
}

main "$${@}"
