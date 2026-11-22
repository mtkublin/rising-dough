-- 0017_user_leading_indexes - T-Q205, Q-034 (C-11).
--
-- Every hot read filters by `user_id` first, but the pre-0012 indexes lead with
-- `operation_date` / `active` and ignore the tenant, so EXPLAIN QUERY PLAN
-- showed full SCANs of the user-scoped tables. Add `user_id`-leading indexes
-- matching the repository predicates. The old indexes stay (other queries
-- still use them). Index-only change: expand-safe, N-1 images keep working.

-- transactions: list / date-range / newest-first (live rows only).
CREATE INDEX ix_transactions_user_live_date
ON transactions (user_id, operation_date)
WHERE deleted_at IS NULL;

-- planned_transactions: list ordered by operation_date (live rows only).
CREATE INDEX ix_planned_user_live_date
ON planned_transactions (user_id, operation_date)
WHERE deleted_at IS NULL;

-- recurring_rules: list per user, optionally active only (live rows only).
CREATE INDEX ix_recurring_user_active
ON recurring_rules (user_id, active)
WHERE deleted_at IS NULL;

-- audit_log: per-user history, newest first.
CREATE INDEX ix_audit_user_id ON audit_log (user_id, id);
