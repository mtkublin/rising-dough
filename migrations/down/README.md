# migrations/down — forward-smoke-only reverse scripts

Files here are **not** production migrations. The project runner
(`src/budget_planner/db/migrate.py`) does not know about this directory
and will never apply a `_down.sql` on its own.

## Purpose

Each `NNNN_<slug>_down.sql` reverses the matching
`migrations/NNNN_<slug>.sql` to the schema shape it had _immediately
before_ its forward counterpart ran. CI tests pin that behaviour by:

1. Applying every forward migration up to `NNNN`.
2. Snapshotting the schema.
3. Applying `NNNN`.
4. Applying `down/NNNN_<slug>_down.sql`.
5. Diffing step 4 against step 2.

The point of the exercise is to prove the forward migration is
structurally reversible — e.g. the table rebuilds are complete, every
index is restored, every column add has a matching column drop. It
catches "I forgot one of the five indices" bugs during review.

## Scope caveats

- **Data preservation is best-effort.** Forward migrations are the
  canonical path; the down scripts preserve rows that round-trip
  cleanly but will drop or raise on rows that _only_ make sense under
  the new schema (e.g. a user whose `id != 1` after `0012`, or audit
  rows whose `actor_user_id` is set). CI exercises down against a
  freshly-forwarded scratch DB so the data assumptions always hold.
- **Not transactional across files.** Each down file is applied in its
  own BEGIN/COMMIT (via the test harness). If you need to reverse
  multiple migrations in a chain, apply them bottom-up and expect to
  rebuild from source if anything fails.
- **No production runbook.** If a forward migration ever needs to be
  rolled back on a live DB, the operator takes a Litestream restore to
  the prior point-in-time — not these files.

## Adding a new down migration

1. Add `migrations/down/NNNN_<slug>_down.sql` matching the forward
   file name 1:1 (same `NNNN`, same slug).
2. If the forward file requires `PRAGMA foreign_keys = OFF`, the test
   harness must flip the pragma around the down file too.
3. Extend `tests/integration/db/test_migrations.py` with a
   `test_NNNN_down_reverses` that applies forward + down and asserts
   the pre-forward schema is restored.
