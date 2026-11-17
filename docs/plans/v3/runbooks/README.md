# Runbooks

Operational procedures for v3. Each runbook is a check-list the operator (or an automation) runs when something needs doing. All runbooks are created in Phase 4 (T-D46) and must be re-executed at least once before Phase 4 is marked complete.

| Runbook | Trigger |
|---|---|
| [`deploy.md`](deploy.md) | Standard release of a new version to prod: one approved `terraform apply` (`release.yml`, ADR-0099, ADR-0111). |
| [`rollback.md`](rollback.md) | Release went bad after it converged; swap back to the previous image ref (ADR-0111). |
| [`host-state-migration.md`](host-state-migration.md) | One-time: install the ADR-0111 host agent on the pre-ADR-0111 prod VM and remove the SSH deploy path (T-D129f). |
| [`restore.md`](restore.md) | DB is corrupt / lost; restore from Litestream. |
| [`disaster-recovery.md`](disaster-recovery.md) | Compute instance is gone; full re-provision from zero (includes lost-all-admins recovery). |
| [`restore-log.md`](restore-log.md) | Append-only log of every restore drill (monthly cadence + any ad-hoc). |
| [`tailscale-ssh.md`](tailscale-ssh.md) | Joining the tailnet, pasting the ACL, host keys, break-glass when SSH is unreachable. |
| [`user-admin.md`](user-admin.md) | Add / reset / remove / promote users; enforce last-admin invariant and data-isolation guarantee. |
| [`drill.md`](drill.md) | Deploy a branch to the drill environment: `*-deploy` push, dispatch with TTL, PR gate, sweeper, boot logs. |
| [`break-glass.md`](break-glass.md) | Exception path (ADR-0099 c): org-admin key for a GitHub outage, stuck state lock, or bootstrap roots. |
| [`key-rotation.md`](key-rotation.md) | Rotating the leaked org-admin key and the per-environment CI keys; cadence and expiry alerts (ADR-0100). |
| [`github-settings.md`](github-settings.md) | Manual GitHub environment and branch-protection checklist that enforces ADR-0099 and ADR-0100. |
| [`prod-db-seed.md`](prod-db-seed.md) | One-time copy of the local DB onto prod (ADR-0099 exception d; done 2026-11-07). |
| [`image-retention.md`](image-retention.md) | Weekly GHCR cleanup (keep newest 20 `sha-*`, `main`/`v*`); dry-run first, then enable (T-D126). |
| [`data-inventory.md`](data-inventory.md) | Where every piece of user data and every secret lives, its protection and retention, and what the operator can technically see (T-D61, ADR-0078 §8). |
| [`security-audit-log.md`](security-audit-log.md) | Append-only log of external security scans of prod (Observatory, testssl, nikto, trivy) with findings to act on (T-D42). |
| [`operator-checklist.md`](operator-checklist.md) | Ordered human-only go-live steps as of 2026-11-07 (GitHub, Tailscale, Scaleway, bootstrap). |

Each runbook follows the shape: **Context** · **Preconditions** · **Procedure** · **Verification** · **Troubleshooting** · **Rollback**.

Runbooks live here (not in `../phase-4-validation/`) so they remain visible after Phase 4 is closed.
