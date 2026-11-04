# T-D58 — `PRAGMA secure_delete = ON`

- **Phase**: 5 — Data-protection quick wins
- **Parallel-safe**: yes
- **Depends on**: T-D05
- **References**: [ADR-0078](../../../adr/0078-v3-data-protection-quick-wins.md) §6, [ADR-0034](../../../adr/0034-v3-sqlite-replication-litestream.md) §2

## Context

Deleted/overwritten rows (sessions, rate-limit counters, edited descriptions, future purges) remain readable in free pages until reused.

## Deliverables

1. `db/connection.py`: `PRAGMA secure_delete = ON;` applied on every connection next to the existing PRAGMAs; docstring updated.
2. Extend the PRAGMA unit test.

## Acceptance criteria

- Unit: fresh connection reports `secure_delete = 1`.
- Test: insert a row with a sentinel string, delete it, checkpoint on a scratch DB, byte-scan the file → sentinel absent.
- `just ci` green; no measurable regression in `tests/perf` if present.

## Validation hook

```sh
just test tests/unit/db/test_connection.py
```
