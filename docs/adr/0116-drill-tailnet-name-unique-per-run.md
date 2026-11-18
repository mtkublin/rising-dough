# ADR-0116: The Drill's Tailnet Name Is Unique Per Run

- **Status**: Accepted
- **Date**: 2026-11-18
- **Amends**: ADR-0101 (tailnet-only drill)
- **Relates to**: ADR-0094, ADR-0099
- **Task**: T-D139

## Context

The drill serves `https://budget-planner-drill.<tailnet>.ts.net` and Caddy gets its certificate from the local `tailscaled`, which orders it from Let's Encrypt. Every drill VM is new and holds no certificate, so every drill orders one for the same name. Let's Encrypt allows 5 certificates per exact identifier set per 168 h. After the fifth drill of the week, tailscaled answers `429 rateLimited ... retry after <next day>`, Caddy's TLS handshake blocks until its 60 s deadline, and `/ready` times out. Gate run 44304732854 failed this way (smoke: `curl: (28)`, port 443 accepts TCP, no ServerHello). It was not a code regression; the same commit would pass the next day.

## Decision

1. New Terraform variable `drill_run_id` (digits only, empty on prod). When set on the drill, `tailscale_hostname` is `budget-planner-drill-<id>` and the served name is `budget-planner-drill-<id>.<tailnet>`.
2. `terraform.yml` and `restore-drill.yml` pass `github.run_id`; `drill.yml` and `restore-drill.yml` derive the smoke/SSH names from `github.run_id`. A re-run attempt keeps the name; it never reuses it across runs.
3. The name matches the existing cleanup pattern `budget-planner-drill(-[0-9]+)?` (ADR-0101 node cleanup, sweeper, drill-lock), so stale nodes are still deleted.
4. Without a run id (local use) the fixed name stays.

## Consequences

- Each drill costs one certificate, but under a name never used before, so the per-name limit no longer applies. The remaining ceiling is 50 certificates per week for the tailnet domain (`ts.net` is on the Public Suffix List).
- The operator SSH name of an explore drill is `budget-planner-drill-<run id>` (printed by the workflow, also the `tailscale_hostname` output).
- Rejected: persisting the certificate across drills (private key material outside the VM, new moving parts); a self-signed or `tls internal` drill certificate (the smoke would stop testing the real TLS path).
