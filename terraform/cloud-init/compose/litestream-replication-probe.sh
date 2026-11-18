#!/bin/sh
# T-D144 / ADR-0119: replication freshness probe (service litestream-probe).
# Written verbatim by the host agent (ADR-0111); no Terraform templating.
#
# Every PROBE_INTERVAL seconds: list the replica with `litestream generations`
# (an S3 LIST, so it proves objects reached the bucket), take the newest `end`
# timestamp over all generations, and write a status file the app serves at
# /health/replication. No secrets go into the file.
#
# Status file: {"checked_at","newest_object_at","generation","error"}.
# `litestream generations` prints: name generation lag start end (header first);
# `end` is the last column, an RFC 3339 UTC timestamp.
set -eu

KEY_FILE="${LITESTREAM_AGE_KEY_FILE:-/run/litestream-age.key}"
CONFIG="${PROBE_CONFIG:-/etc/litestream.yml}"
STATUS_DIR="${PROBE_STATUS_DIR:-/status}"
INTERVAL="${PROBE_INTERVAL:-300}"
ONCE="${PROBE_ONCE:-0}"

# The config expands $LITESTREAM_AGE_IDENTITY; listing needs no decryption, but
# the config must load.
LITESTREAM_AGE_IDENTITY="$(grep -m1 '^AGE-SECRET-KEY-' "$KEY_FILE" || true)"
export LITESTREAM_AGE_IDENTITY

write_status() { # $1=newest|"" $2=generation|"" $3=error|""
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  q() { if [ -n "$1" ]; then printf '"%s"' "$1"; else printf 'null'; fi; }
  tmp="$STATUS_DIR/.status.json.tmp"
  printf '{"checked_at":"%s","newest_object_at":%s,"generation":%s,"error":%s}\n' \
    "$now" "$(q "$1")" "$(q "$2")" "$(q "$3")" > "$tmp"
  chmod 0644 "$tmp"
  mv "$tmp" "$STATUS_DIR/status.json"
}

probe_once() {
  if ! out="$(litestream generations -config "$CONFIG" "${PROBE_DB:-/data/budget.db}" 2>/dev/null)"; then
    write_status "" "" "generations_failed"
    return 0
  fi
  # Newest row by the end timestamp (ISO strings sort chronologically).
  best="$(printf '%s\n' "$out" | awk 'NR > 1 && NF >= 5 && $NF ~ /^[0-9][0-9][0-9][0-9]-/ { print $NF " " $2 }' | sort | tail -n 1)"
  if [ -z "$best" ]; then
    write_status "" "" ""
    return 0
  fi
  newest="${best%% *}"
  generation="${best#* }"
  case "$generation" in *[!0-9a-f]*) generation="" ;; esac
  write_status "$newest" "$generation" ""
}

mkdir -p "$STATUS_DIR"
while :; do
  probe_once
  [ "$ONCE" = "1" ] && exit 0
  sleep "$INTERVAL"
done
