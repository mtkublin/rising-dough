# Phase 3 — Deployment pipeline

GitHub Actions deploys cosign-signed images to the Scaleway VM via SSH to a tightly-caged `deploy` user (ADR-0037).

- [T-D30](T-D30-build-workflow.md) — Build workflow (image + cosign).
- [T-D31](T-D31-deploy-workflow.md) — Deploy workflow (detailed here).
- T-D32 — Deploy user command restriction + script. See `../tasks.md`.
- T-D33 — Deliberate-break rollback test.
- T-D34 — Manual rollback workflow.

**Startup / migrations (T-D19a, ADR-0071).** Neither the deploy workflow nor the shim runs migrations. The image entrypoint does that on every container start, before uvicorn. Compose waits for the one-shot `litestream-restore` service (restore only when the DB is missing) before it starts `app` or `litestream`. Rollbacks depend on every migration staying N-1 compatible. A release that cannot meet that is flagged "rollback requires restore" in `docs/CHANGELOG.md`.
