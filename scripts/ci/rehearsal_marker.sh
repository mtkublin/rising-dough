#!/bin/sh
# ADR-0121 §7 (replace-rehearsal.yml): marker rows on the drill host. Runs as root
# over SSH (`ssh operator@host 'sudo sh -s -- <cmd> ...' < this file`). Rows are
# written through the app container, as the app writes them, so a write counts
# only while the app is running.
#
#   init            create the marker table
#   write N         insert rows 1..N
#   writer FROM     insert FROM, FROM+1, ... one per second until the app container
#                   stops; a failed insert is retried while it still runs. Prints
#                   "committed <seq>" after each commit and "writer stopped: app gone"
#                   at the end
#   stats           print "<max seq>|<row count>" (read-only)
set -eu

APP=budget-planner-app
DB="${REHEARSAL_DB:-/data/budget.db}"
PY_INIT='import sqlite3; c = sqlite3.connect("/data/budget.db", timeout=5); c.execute("CREATE TABLE IF NOT EXISTS t_d155_marker (seq INTEGER PRIMARY KEY, at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"); c.commit()'
PY_INSERT='import sqlite3, sys; c = sqlite3.connect("/data/budget.db", timeout=5); c.execute("INSERT INTO t_d155_marker (seq) VALUES (?)", (int(sys.argv[1]),)); c.commit()'

insert() {
  docker exec "$APP" python -c "$PY_INSERT" "$1"
}

case "${1:-}" in
  init)
    docker exec "$APP" python -c "$PY_INIT"
    ;;
  write)
    seq=1
    while [ "$seq" -le "$2" ]; do
      insert "$seq"
      seq=$((seq + 1))
    done
    echo "wrote 1..$2"
    ;;
  writer)
    seq="$2"
    while :; do
      if insert "$seq" 2>/dev/null; then
        echo "committed $seq"
        seq=$((seq + 1))
      elif [ "$(docker inspect -f '{{.State.Running}}' "$APP" 2>/dev/null || true)" != true ]; then
        break
      fi
      sleep 1
    done
    echo "writer stopped: app gone before $seq"
    ;;
  stats)
    sqlite3 -readonly -separator '|' "$DB" 'SELECT coalesce(max(seq), 0), count(*) FROM t_d155_marker;'
    ;;
  *)
    echo "usage: $0 init | write N | writer FROM | stats" >&2
    exit 2
    ;;
esac
