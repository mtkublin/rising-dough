# Runbooks

Operational procedures for v3. Each runbook is a check-list the operator (or an automation) runs when something needs doing. All runbooks are created in Phase 4 (T-D46) and must be re-executed at least once before Phase 4 is marked complete.

| Runbook | Trigger |
|---|---|
| [`deploy.md`](deploy.md) | Standard release of a new SHA to prod. |
| [`rollback.md`](rollback.md) | Deploy went bad; need the previous SHA. |
| [`restore.md`](restore.md) | DB is corrupt / lost; restore from Litestream. |
| [`disaster-recovery.md`](disaster-recovery.md) | Compute instance is gone; full re-provision from zero (includes lost-all-admins recovery). |
| [`restore-log.md`](restore-log.md) | Append-only log of every restore drill (monthly cadence + any ad-hoc). |
| [`tailscale-ssh.md`](tailscale-ssh.md) | Joining the tailnet, pasting the ACL, host keys, break-glass when SSH is unreachable. |
| [`user-admin.md`](user-admin.md) | Add / reset / remove / promote users; enforce last-admin invariant and data-isolation guarantee. |

Each runbook follows the shape: **Context** · **Preconditions** · **Procedure** · **Verification** · **Troubleshooting** · **Rollback**.

Runbooks live here (not in `../phase-4-validation/`) so they remain visible after Phase 4 is closed.
