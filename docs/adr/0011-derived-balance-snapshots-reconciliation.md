# ADR-0011: Derived Balance, Manual Snapshots, Reconciliation

- **Status**: Accepted
- **Date**: 2026-10-23

## Decision

### Balance derivation
Account balance is **derived**, not stored:

```
balance(account, as_of) = opening_balance + Σ signed_amount(txn)
   for txn in transactions
   where txn.account_id == account OR txn.dest_account_id == account
     AND txn.operation_date <= as_of
     AND txn.deleted_at IS NULL
```

### Snapshots
A separate `account_snapshots(id, account_id, taken_at, balance, note)` table records **manual** balance snapshots. Users click "take snapshot" to append a row.

Snapshots are a pure audit record — they do **not** alter the derived balance. They enable:
- "What did I think the balance was on 2026-01-05?"
- Drift detection vs the derived balance over time.

### Reconciliation
When the user notices the derived balance disagrees with their real bank balance, they click "reconcile" and enter the true balance. The system:

1. Computes `delta = actual - derived`.
2. Inserts a transaction with `category = Reconciliation` (direction = `adjustment`), `amount = delta` (signed; ADR-0008 exception), `description = "auto-reconciliation {today}"`, `operation_date = today`, `account_id` set, `dest_account_id = NULL`.
3. Derived balance now equals `actual`.

The adjustment is excluded from income/expense statistics (same mechanism as transit).

## Consequences

- Single source of truth: the transaction log.
- No reconciliation drift from edits/deletes.
- Audit trail of real-world balance checks via snapshots.
- Reconciliation keeps books honest without hiding the correction (it is a visible adjustment txn).

## Alternatives Considered

- **Stored balance updated per txn**: fast reads but reconciliation nightmare on edits/deletes.
- **Stored month-end snapshots**: premature optimisation; add if slow.
- **Silent reconciliation (no adjustment txn)**: hides the correction; the sum of inflows + outflows would no longer match the balance.

## Amendment (T-D52)

For liability accounts that have a `credit_limit_minor`, the reconcile dialog takes the user-observed **available** credit (what the bank app shows). The service converts it to the target derived balance: `used = credit_limit - available`, `target = -used` (liabilities store owed amounts as negative balances). The existing flow then applies unchanged: `delta = target - derived`, a signed `adjustment` transaction (ADR-0008 exception). `available` must satisfy `0 <= available <= credit_limit`; values outside are rejected (422) because a positive (overpaid) balance would be displayed with available clamped to the limit. Liabilities without a limit and asset accounts continue to enter the balance directly. Conversion is a pure function `available_to_target_balance` in `services/reconciliation.py`.
