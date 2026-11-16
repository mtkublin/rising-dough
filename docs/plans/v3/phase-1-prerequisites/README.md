# Phase 1 — App Prerequisites

Work on the application itself before any Scaleway resource exists. Everything here is testable with a local `docker compose` stack and MinIO. Phase 2 cannot start until the Phase 1 exit criteria from [`../implementation_plan.md`](../implementation_plan.md) are met.

## Tasks

- [T-D01](T-D01-health-endpoints.md) — Health & readiness endpoints.
- [T-D02](T-D02-auth-webauthn.md) — WebAuthn + fallback password auth.
- [T-D03](T-D03-config-surface.md) — Config surface for production.
- [T-D04](T-D04-db-config.md) — Litestream-friendly DB config.
- [T-D05](T-D05-sqlite-pragmas.md) — SQLite PRAGMAs for Litestream.
- [T-D06](T-D06-structured-logging.md) — Structured JSON logging + request ID.
- [T-D07](T-D07-security-headers.md) — Security headers middleware.
- [T-D08](T-D08-csrf.md) — CSRF protection.
- [T-D09](T-D09-auth-rate-limit.md) — Rate limit on auth routes.
- [T-D10](T-D10-dockerfile.md) — Dockerfile (multi-stage, non-root).
- [T-D11](T-D11-docker-compose.md) — docker-compose.yml for prod-sim.
- [T-D12](T-D12-reproducible-lock.md) — Reproducible dependency lock.
- [T-D13](T-D13-ci-security-scans.md) — CI security scans.
- [T-D14](T-D14-audit-request-ctx.md) — Audit log carries client IP + session user.
- [T-D15](T-D15-graceful-shutdown.md) — Graceful shutdown handling.
- [T-D53](T-D53-session-hardening.md) — Session hardening: absolute cap, step-up re-auth, hashed ids.
