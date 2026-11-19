-- 0016_audit_backfill_owner — T-D145, ADR-0122.
--
-- Domain audit rows written before the T-D145 fix have user_id NULL (the
-- repositories never passed the owner). Fill user_id from the owning row of
-- the audited entity so audit_tail shows users their own history.
--
-- * Only rows with user_id IS NULL are touched; existing values are kept.
-- * actor_user_id is NOT backfilled: who acted is not recoverable from data.
--   audit_tail ownership uses user_id first, so a NULL actor is harmless.
-- * Rows whose entity row no longer exists (hard-deleted recurring_override
--   rows) and fx_rate rows (global) stay NULL.
-- * Data-only; schema unchanged, so N-1 images keep running.

UPDATE audit_log
SET user_id = e.user_id
FROM accounts AS e
WHERE
    audit_log.user_id IS NULL
    AND audit_log.entity_type = 'account'
    AND e.id = audit_log.entity_id;

UPDATE audit_log
SET user_id = e.user_id
FROM categories AS e
WHERE
    audit_log.user_id IS NULL
    AND audit_log.entity_type = 'category'
    AND e.id = audit_log.entity_id;

UPDATE audit_log
SET user_id = e.user_id
FROM transactions AS e
WHERE
    audit_log.user_id IS NULL
    AND audit_log.entity_type = 'transaction'
    AND e.id = audit_log.entity_id;

UPDATE audit_log
SET user_id = e.user_id
FROM planned_transactions AS e
WHERE
    audit_log.user_id IS NULL
    AND audit_log.entity_type = 'planned_transaction'
    AND e.id = audit_log.entity_id;

UPDATE audit_log
SET user_id = e.user_id
FROM recurring_rules AS e
WHERE
    audit_log.user_id IS NULL
    AND audit_log.entity_type = 'recurring_rule'
    AND e.id = audit_log.entity_id;

UPDATE audit_log
SET user_id = e.user_id
FROM budget_defaults AS e
WHERE
    audit_log.user_id IS NULL
    AND audit_log.entity_type = 'budget_default'
    AND e.id = audit_log.entity_id;

UPDATE audit_log
SET user_id = e.user_id
FROM budget_recurring_overrides AS e
WHERE
    audit_log.user_id IS NULL
    AND audit_log.entity_type = 'budget_recurring_override'
    AND e.id = audit_log.entity_id;

UPDATE audit_log
SET user_id = e.user_id
FROM budget_one_off_overrides AS e
WHERE
    audit_log.user_id IS NULL
    AND audit_log.entity_type = 'budget_one_off_override'
    AND e.id = audit_log.entity_id;

UPDATE audit_log
SET user_id = r.user_id
FROM recurring_rule_overrides AS o
INNER JOIN recurring_rules AS r ON o.rule_id = r.id
WHERE
    audit_log.user_id IS NULL
    AND audit_log.entity_type = 'recurring_override'
    AND o.id = audit_log.entity_id;

UPDATE audit_log
SET user_id = a.user_id
FROM account_snapshots AS s
INNER JOIN accounts AS a ON s.account_id = a.id
WHERE
    audit_log.user_id IS NULL
    AND audit_log.entity_type = 'snapshot'
    AND s.id = audit_log.entity_id;
