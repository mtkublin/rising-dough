#!/usr/bin/env bash
# prod_db_seed.sh — ONE-TIME copy of the operator's local DB onto the prod VM.
# ADR-0099 exception (d); runbook: docs/plans/v3/runbooks/prod-db-seed.md (T-D93).
#
# Reads the local source DB (consistent .backup snapshot), ships it over the
# tailnet as operator@<host>, swaps it in on the VM (keeping the old one aside)
# and restarts litestream + app. Rolls back automatically on failure.
set -Eeuo pipefail
IFS=$'\n\t'

readonly PROGNAME='prod_db_seed'
readonly REMOTE_SEED='/tmp/seed.db'
readonly REMOTE_DB='/data/budget.db'
readonly KEY_TABLES=(users accounts categories transactions planned_transactions recurring_rules)
readonly SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)

SOURCE='data/budget.sqlite'
HOST='budget-planner-prod'
FQDN='budget.rising-dough.eu'
CONFIRMED=0
DRY_RUN=0
FORCE=0
TMPDIR_LOCAL=''

log() { printf '%s: %s\n' "${PROGNAME}" "$*"; }
die() { printf '%s: ERROR: %s\n' "${PROGNAME}" "$*" >&2; exit 1; }

usage() {
  cat <<USAGE
Usage: ${PROGNAME}.sh [--source PATH] [--host HOST] --yes-i-own-prod-data [--dry-run] [--force-overwrite]
  --source PATH          local DB to copy (default: ${SOURCE})
  --host HOST            tailnet host of the prod VM (default: ${HOST})
  --fqdn NAME            public site name used for the /ready probe on the VM (default: ${FQDN})
  --yes-i-own-prod-data  required to touch the remote; without it a plan is printed (exit 2)
  --dry-run              local snapshot + checks only; no ssh/scp
  --force-overwrite      proceed even if the remote DB already has user data
USAGE
}

cleanup() {
  local rc=$?
  set +e
  if [[ -n "${TMPDIR_LOCAL}" && -d "${TMPDIR_LOCAL}" ]]; then
    rm -rf -- "${TMPDIR_LOCAL}"
  fi
  exit "${rc}"
}
trap cleanup EXIT

while (($#)); do
  case "$1" in
    --source) SOURCE="${2:?--source needs a value}"; shift 2 ;;
    --host) HOST="${2:?--host needs a value}"; shift 2 ;;
    --fqdn) FQDN="${2:?--fqdn needs a value}"; shift 2 ;;
    --yes-i-own-prod-data) CONFIRMED=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --force-overwrite) FORCE=1; shift ;;
    -h | --help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
done

print_plan() {
  cat <<PLAN
PLAN (one-time prod DB seed, ADR-0099 exception d)
  1. snapshot  ${SOURCE} -> private temp dir (sqlite3 .backup), integrity_check, row counts
  2. refuse if operator@${HOST}:${REMOTE_DB} already holds user data (unless --force-overwrite)
  3. scp snapshot -> operator@${HOST}:${REMOTE_SEED} (0600), verify sha256 remotely
  4. on the VM: stop app+litestream, move ${REMOTE_DB}* aside to /data/pre-seed-<ts>/,
     install seed (uid 10001), start litestream+app, wait for /ready, show litestream generations
  5. any failure after the stop: restore the moved-aside DB and restart services
PLAN
}

if ((CONFIRMED == 0 && DRY_RUN == 0)); then
  print_plan
  echo "Refusing to proceed: pass --yes-i-own-prod-data to confirm (or --dry-run)." >&2
  exit 2
fi

command -v sqlite3 >/dev/null || die "sqlite3 not found"
[[ -f "${SOURCE}" ]] || die "source DB not found: ${SOURCE}"

TMPDIR_LOCAL="$(mktemp -d)"
chmod 0700 "${TMPDIR_LOCAL}"
SNAP="${TMPDIR_LOCAL}/seed.db"

log "snapshotting ${SOURCE}"
sqlite3 -readonly "${SOURCE}" ".backup '${SNAP}'"
chmod 0600 "${SNAP}"

integrity="$(sqlite3 "${SNAP}" 'PRAGMA integrity_check;')"
log "integrity_check=${integrity}"
[[ "${integrity}" == "ok" ]] || die "integrity_check failed on snapshot"

log "user_version=$(sqlite3 "${SNAP}" 'PRAGMA user_version;')"
has_mig="$(sqlite3 "${SNAP}" "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='schema_migrations';")"
if [[ "${has_mig}" == "1" ]]; then
  log "schema_migrations max version=$(sqlite3 "${SNAP}" 'SELECT coalesce(max(version),0) FROM schema_migrations;')"
fi
for t in "${KEY_TABLES[@]}"; do
  exists="$(sqlite3 "${SNAP}" "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='${t}';")"
  if [[ "${exists}" == "1" ]]; then
    log "rows ${t}=$(sqlite3 "${SNAP}" "SELECT count(*) FROM \"${t}\";")"
  fi
done
if command -v sha256sum >/dev/null; then
  SHA="$(sha256sum "${SNAP}" | cut -d' ' -f1)"
else
  SHA="$(shasum -a 256 "${SNAP}" | cut -d' ' -f1)"
fi
log "sha256=${SHA}"

if ((DRY_RUN == 1)); then
  log "dry-run: stopping before any remote action"
  exit 0
fi

REMOTE="operator@${HOST}"

log "checking remote DB for existing user data"
remote_count="$(ssh "${SSH_OPTS[@]}" "${REMOTE}" \
  "if sudo test -f ${REMOTE_DB}; then sudo sqlite3 -readonly ${REMOTE_DB} 'SELECT (SELECT count(*) FROM accounts)+(SELECT count(*) FROM transactions);'; else echo 0; fi")"
remote_count="${remote_count//[[:space:]]/}"
[[ "${remote_count}" =~ ^[0-9]+$ ]] || die "unexpected remote row count: '${remote_count}'"
if ((remote_count > 0)); then
  ((FORCE == 1)) || die "remote DB already has ${remote_count} account/transaction rows; use --force-overwrite to replace"
  log "WARNING: --force-overwrite: replacing remote DB with ${remote_count} rows (kept aside)"
fi

log "transferring snapshot"
scp "${SSH_OPTS[@]}" -q "${SNAP}" "${REMOTE}:${REMOTE_SEED}"

# Runs on the VM as root. $1 = expected sha256, $2 = site FQDN (Caddy only has a cert for it).
read -r -d '' REMOTE_SCRIPT <<'REMOTE' || true
set -Eeuo pipefail
EXPECTED="$1"
FQDN="$2"
SEED=/tmp/seed.db
DATA=/data
DB=/data/budget.db
COMPOSE="docker compose -f /etc/budget-planner/docker-compose.yml"
ASIDE="${DATA}/pre-seed-$(date -u +%Y%m%dT%H%M%SZ)"
STOPPED=0
OK=0
chmod 0600 "$SEED"
actual="$(sha256sum "$SEED" | cut -d' ' -f1)"
[ "$actual" = "$EXPECTED" ] || { echo "sha256 mismatch on VM" >&2; exit 1; }
[ "$(sqlite3 "$SEED" 'PRAGMA integrity_check;')" = ok ] || { echo "remote integrity_check failed" >&2; exit 1; }
echo "remote sha256 verified"
rollback() {
  rc=$?
  set +e
  rm -f "$SEED"
  if [ "$STOPPED" = 1 ] && [ "$OK" != 1 ]; then
    echo "FAILURE: rolling back to moved-aside DB" >&2
    $COMPOSE stop app litestream
    find "$DATA" -maxdepth 1 \( -name 'budget.db*' -o -name '.budget.db-litestream' \) -exec rm -rf -- {} +
    find "$ASIDE" -mindepth 1 -maxdepth 1 -exec mv -t "$DATA" -- {} +
    $COMPOSE up -d litestream app
    echo "rolled back; seed copy discarded" >&2
  fi
  exit "$rc"
}
trap rollback EXIT
$COMPOSE stop app
sleep 5
$COMPOSE stop litestream
STOPPED=1
mkdir -p "$ASIDE"
chmod 0700 "$ASIDE"
find "$DATA" -maxdepth 1 \( -name 'budget.db*' -o -name '.budget.db-litestream' \) -exec mv -t "$ASIDE" -- {} +
echo "moved previous DB aside to $ASIDE"
mv "$SEED" "$DB"
chown 10001:10001 "$DATA" "$DB"
chmod 0700 "$DATA"
chmod 0600 "$DB"
$COMPOSE up -d litestream app
ready=0
ready_re='"status" *: *"(ready|ok)"'
for _ in $(seq 1 36); do
  # Signal 1: public path via the real FQDN pinned to loopback (valid cert, SNI matches).
  if body="$(curl -fsS --max-time 5 --resolve "${FQDN}:443:127.0.0.1" "https://${FQDN}/ready" 2>/dev/null)" \
    && printf '%s' "$body" | grep -Eq "$ready_re"; then
    ready=1
    break
  fi
  # Signal 2: container healthy AND in-container /ready ok (image ships curl).
  if [ "$(docker inspect -f '{{.State.Health.Status}}' budget-planner-app 2>/dev/null)" = healthy ] \
    && body="$(docker exec budget-planner-app curl -fsS --max-time 5 http://127.0.0.1:8000/ready 2>/dev/null)" \
    && printf '%s' "$body" | grep -Eq "$ready_re"; then
    ready=1
    break
  fi
  sleep 5
done
[ "$ready" = 1 ] || { echo "/ready did not report ready within 180s" >&2; exit 1; }
echo "/ready: ready"
OK=1
echo "--- litestream generations (a new generation should appear shortly) ---"
sleep 15
docker exec budget-planner-litestream litestream generations -config /etc/litestream.yml "$DB" || echo "(could not list generations; check manually)"
echo "Moved-aside copy kept at: $ASIDE"
echo "Delete after verification: ssh operator@<host> sudo rm -rf $ASIDE"
REMOTE

log "swapping DB on ${HOST}"
printf '%s\n' "${REMOTE_SCRIPT}" | ssh "${SSH_OPTS[@]}" "${REMOTE}" "sudo bash -s -- ${SHA} ${FQDN}"
log "seed complete. Verify in the app, then delete the moved-aside copy (see output above)."
