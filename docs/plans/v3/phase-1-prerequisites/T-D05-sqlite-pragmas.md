# T-D05 — Centralise SQLite PRAGMAs for Litestream

- **Phase**: 1 — App Prerequisites
- **Parallel-safe**: no (sequential — all later tasks depend on correct PRAGMAs)
- **Depends on**: nothing
- **Blocks**: T-D04 (startup assertion), T-D23 (cloud-init expects a connection factory that already sets `wal_autocheckpoint = 0`)
- **References**: ADR-0034 §2

## Context

ADR-0034 §2 fixes four PRAGMAs on every SQLite connection:

- `journal_mode = WAL` — required by Litestream.
- `synchronous = NORMAL` — safe with WAL mode.
- `wal_autocheckpoint = 0` — Litestream owns checkpoint cadence.
- `busy_timeout = 5000` — tolerates sidecar read bursts.

`foreign_keys = ON` stays separate (correctness, not durability).

v1 wires `foreign_keys`, `journal_mode`, and `synchronous` in `get_connection`. The remaining two PRAGMAs (`wal_autocheckpoint`, `busy_timeout`) are missing. Bypassing `get_connection` to open ad-hoc connections risks corrupting the Litestream invariant.

## Deliverables

1. `src/budget_planner/db/connection.py`:
   - Extract `_apply_pragmas(conn)` that executes the four Litestream PRAGMAs. `foreign_keys` stays in `get_connection` (separate concern).
   - Expand the module-level docstring: "Bypassing `get_connection` is a bug — Litestream requires `wal_autocheckpoint = 0`, see ADR-0034."
2. `tests/unit/db/test_connection_pragmas.py` asserts each PRAGMA plus `foreign_keys` on a fresh connection.

## Acceptance criteria

- All four Litestream PRAGMAs plus `foreign_keys` observable via `PRAGMA <name>` on a fresh connection.
- `grep -nR "sqlite3.connect(" src tests` reveals no new call sites that bypass `get_connection`.

## Validation hook

```sh
just test tests/unit/db/test_connection_pragmas.py
```
