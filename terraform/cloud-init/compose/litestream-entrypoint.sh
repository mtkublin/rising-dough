#!/bin/sh
# T-D136 / ADR-0114: entrypoint of the litestream service (replicate).
# Written verbatim by the host agent (ADR-0111); no Terraform templating.
#
# 1. Export the age identity so litestream.yml can read it. Litestream 0.3.14
#    decrypts the last WAL segment on every start (calcPos) only when
#    age.identities is set.
# 2. Once per host, forget the local generation so the next start opens a new
#    one. Older generations may hold plaintext segments that the identity
#    cannot decrypt. Only Litestream's meta dir is removed; the SQLite
#    database and WAL are never touched.
set -eu

DATA_DIR="${LITESTREAM_DATA_DIR:-/data}"
KEY_FILE="${LITESTREAM_AGE_KEY_FILE:-/run/litestream-age.key}"
META_DIR="$DATA_DIR/.budget.db-litestream"
MARKER="$DATA_DIR/.litestream-age-generation"

if [ ! -r "$KEY_FILE" ]; then
  echo "litestream-entrypoint: age identity file $KEY_FILE missing" >&2
  exit 1
fi
LITESTREAM_AGE_IDENTITY="$(grep -m1 '^AGE-SECRET-KEY-' "$KEY_FILE" || true)"
if [ -z "$LITESTREAM_AGE_IDENTITY" ]; then
  echo "litestream-entrypoint: no AGE-SECRET-KEY line in $KEY_FILE" >&2
  exit 1
fi
export LITESTREAM_AGE_IDENTITY

if [ "${1:-}" = "replicate" ] && [ ! -e "$MARKER" ]; then
  echo "litestream-entrypoint: forcing a new generation (one-time, ADR-0114)"
  rm -rf "$META_DIR"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$MARKER"
fi

exec litestream "$@"
