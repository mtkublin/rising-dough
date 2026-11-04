# Rising Dough v3 — Implementation Plan

> Companion to `tasks.md`. Describes order, phasing, acceptance criteria, and handoff shape so subsequent agents can pick up work without re-deriving context.

---

## Guiding Principles

1. **Docs first.** Every v3 change already has an ADR (0032–0037 + 0061). Any surprise during implementation that would deviate from those ADRs stops the task until the ADR is amended.
2. **One operator, few users.** Scope is a handful of users (order of magnitude 10) running on a single VM in Warsaw, administered by one bootstrapped admin. No multi-region, no HA, no self-signup, no admin impersonation. Admin manages the user list; admin does **not** see user data (ADR-0061).
3. **Disposable host.** Durable state lives in the Scaleway Object Storage bucket (ADR-0034). Rebuilding the VM must be a routine operation, not a disaster.
4. **Secrets live in infrastructure, not in git.** Terraform generates and injects secrets via cloud-init (admin bootstrap password included); the operator captures them to a password manager at provisioning time.
5. **The pipeline is the only path to production.** No manual deploys. No manual Terraform apply from a developer laptop except for the explicit bootstrap step (ADR-0035 §4).
6. **Automate the drill.** The monthly restore drill is a scheduled GitHub Actions job, not a calendar reminder.
7. **Isolation is enforced in the repository layer.** Every repository function against a user-owned table takes `user_id` and filters on it; a static-analysis test guards against regression (ADR-0061 §5).

---

## Architecture overview (v3)

```
                            Internet
                               │
                        HTTPS (443) only
                               │
┌──────────────────────────────▼──────────────────────────────┐
│  Scaleway Stardust1-S  (Ubuntu 24.04, pl-waw-1, Warsaw)      │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  docker compose stack                                    │ │
│  │  ┌──────────┐  ┌─────────────┐  ┌───────────────────┐    │ │
│  │  │ caddy    │─▶│ app         │  │ litestream        │    │ │
│  │  │ TLS +    │  │ FastAPI     │  │ sidecar           │    │ │
│  │  │ headers  │  │ /data mount │  │ reads /data WAL   │    │ │
│  │  └──────────┘  └─────────────┘  └─────────┬─────────┘    │ │
│  └────────────────────────────────────────────│──────────────┘ │
│      Caddy data volume (certs + ACME storage) │                │
│      /data host volume (SQLite + WAL)         │                │
└───────────────────────────────────────────────│────────────────┘
                                                │
                                   WAL stream (≤10 s cadence)
                                                │
                                                ▼
┌──────────────────────────────────────────────────────────────┐
│  Scaleway Object Storage  —  budget-planner-prod-pl-waw       │
│  (pl-waw, versioning on, IAM-scoped, 30-day retention)        │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  Terraform state bucket  —  budget-planner-tfstate-pl-waw     │
│  (one-shot bootstrap, out-of-band)                            │
└──────────────────────────────────────────────────────────────┘
```

GitHub Actions pipeline (ADR-0037): CI → build (image push + cosign) → manual env approval → SSH deploy → `/ready` probe → auto-rollback on failure.

---

## Phased delivery

### Phase 1 — App prerequisites (T-D01..T-D19)

Goal: the application container is production-shaped — auth (per-user, admin-bootstrapped), config, SQLite PRAGMAs, security headers, Docker build, local docker-compose smoke, repository-layer `user_id` discipline — before any Scaleway resource is created.

Everything here is testable locally with `just test-prod-stack` (new recipe added in T-D11), which boots the full three-container stack (`app` + `litestream` to a MinIO sidecar + `caddy` on a self-signed cert), seeds a dev admin via env vars, and runs a Playwright smoke journey against it.

Entry: v1 CI green on `main`.

Exit criteria:
- `just test` passes; new modules ≥ 90% coverage.
- `just test-prod-stack` passes (local full-stack docker-compose smoke).
- `/health` and `/ready` endpoints respond correctly, including DB-down readiness failure.
- The admin-bootstrap + login + password-rotation + passkey-registration + user-admin-panel flows work end-to-end against the local stack.
- Security headers (HSTS, CSP with nonce, X-Frame-Options, Referrer-Policy, Permissions-Policy) assert correctly in integration tests.
- `pip-audit` + `trivy` on the built image emit no HIGH/CRITICAL findings.
- The repository `user_id`-filter static-analysis test (`tests/architecture/test_user_id_filter.py`) passes against every repository module.
- `just ci` extended to include `test-prod-stack`.

### Phase 2 — Infrastructure (T-D20..T-D28)

Goal: a single `terraform apply` in the `drill` environment stands up the VM, the object storage bucket, the IAM credential, the DNS records, and the running app stack, reachable at the drill hostname with a valid Let's Encrypt certificate.

Entry: Phase 1 exit criteria met. Operator has a Scaleway account with a project and billing attached.

Order within phase:
1. Bootstrap state bucket (one-shot `scw object bucket create`).
2. `terraform/providers.tf` + `versions.tf` + `backend.tf`.
3. `modules/iam` + `modules/storage` (bucket + IAM app + policy + key).
4. `modules/dns` (zone + records).
5. `modules/compute` (instance + flex IP + security group + cloud-init render).
6. Cloud-init templates (`bootstrap.yaml.tpl`, `docker-compose.yml.tpl`, `Caddyfile.tpl`, `litestream.yml.tpl`) — compose env now carries `BUDGET_PLANNER_ADMIN_EMAIL` + `BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD` (ADR-0061 §3).
7. `envs/drill/` wiring + first `terraform apply -var-file=envs/drill/terraform.tfvars` — operator supplies `admin_email` input variable; Terraform generates `admin_initial_password` via `random_password` and surfaces it as a sensitive output.

Exit criteria:
- `terraform plan` emits zero changes after a clean apply.
- The `drill` host serves `/health` 200 via HTTPS with a Let's Encrypt cert (Observatory grade ≥ A).
- Litestream in the drill environment writes to `budget-planner-drill-pl-waw` on a cadence confirmed by `aws s3 ls --endpoint-url …` (or `scw object`) showing a new generation ≤ 15 s after a write.
- `ufw status` on the VM confirms deny-by-default + three allowed ports.
- `fail2ban-client status` shows the `sshd` + `caddy-auth` jails active.
- `cosign verify` succeeds against the deployed image.
- Full tear-down (`terraform destroy -var-file=envs/drill/terraform.tfvars`) completes without manual cleanup.

### Phase 3 — Deployment pipeline (T-D30..T-D34)

Goal: a push to `main` lands a cosign-signed image on the drill host via SSH, with a `/ready` probe and automatic rollback on probe failure. Rollback is one SSH call.

Entry: Phase 2 exit criteria met.

Exit criteria:
- `.github/workflows/ci.yml`, `build.yml`, `deploy.yml`, `rollback.yml` committed and green.
- Deploying to `prod` requires explicit environment approval; deploying to `drill` is automatic.
- A deliberate "break" (push an image that returns 500 on `/ready`) triggers automatic rollback.
- `ssh deploy@<drill-host> "rollback"` restores the previous SHA within 30 s.
- The deploy user cannot run any shell command outside `/usr/local/bin/deploy-budget-planner` (verified by audit).

### Phase 4 — Validation and operations (T-D40..T-D46)

Goal: evidence that the deployment is reliable (backup actually restores), secure (external security scan passes), observable (uptime monitor active), and recoverable (runbooks exist and have been executed at least once).

Entry: Phase 3 exit criteria met.

Exit criteria (per task; a dated runbook entry for each):
- **Backup restore drill** — pulled from the prod bucket into a fresh `drill` environment; `PRAGMA integrity_check = ok`; audit log tail matches pre-destroy snapshot; admin + second user accounts restored intact. First drill is this acceptance gate; monthly automated drill scheduled.
- **Security scan** — `trivy` on the deployed image, `nikto` + `testssl.sh` against the public hostname, Mozilla Observatory grade A+. HIGH/CRITICAL findings resolved or ADR'd.
- **Smoke journey** — Playwright test against the production hostname: admin logs in with the Terraform-captured password → rotates it → creates a second non-admin user via `/settings/users` → logs out → second user logs in with the one-shot auto-generated password → rotates it → registers a passkey → adds a transaction → verifies the admin cannot see that transaction (data isolation assertion) → verifies audit log row.
- **Uptime monitor** — UptimeRobot (or Betterstack free) pings `/health` every 5 min; alert configured to email the operator.
- **Cost alert** — Scaleway budget alert set to 2× expected (PLN) and verified by cutting the threshold to 0.01 PLN temporarily and confirming the email.
- **Runbooks committed**:
  - `docs/plans/v3/runbooks/deploy.md`
  - `docs/plans/v3/runbooks/rollback.md`
  - `docs/plans/v3/runbooks/restore.md`
  - `docs/plans/v3/runbooks/disaster-recovery.md` (full re-provision from zero)
  - `docs/plans/v3/runbooks/restore-log.md` (append-only drill log)
  - `docs/plans/v3/runbooks/user-admin.md` (add user / reset password / remove user / promote-admin / last-admin invariant — ADR-0061)
- **Production go-live** — swap DNS from the drill hostname to the prod hostname; monitor for 48 h; declare live by appending a `## 20YY-MM-DD` entry to `docs/CHANGELOG.md`.

### Phase 5 — Data-protection quick wins (T-D54..T-D61, added 2026-11-04)

Goal: close the cross-user leaks and unbounded copies found in the 2026-11-04 data-protection review, without key management (ADR-0078). Down-payment on v4 (`docs/plans/v4/`).

Entry: Phase 1 complete (app tasks); T-D56/T-D57 need Phase 2 modules (T-D21, T-D23) and the drill restore helper (T-D41a).

Exit criteria:
- Admin's `/debug/audit-tail` shows no other user's payloads (T-D54).
- Authenticated responses `no-store`; back-after-logout shows no data (T-D55).
- Litestream replica age-encrypted; one restore drill against it logged (T-D56).
- Every copy of user data ≤ 37 days old (T-D57); `secure_delete` on (T-D58).
- Sentinel test proves no user values in app or Caddy logs (T-D59); IP/UA purged after 90 d (T-D60).
- `runbooks/data-inventory.md` committed and reviewed by the operator (T-D61).

---

## Rollout order and dependencies (compressed)

```
Phase 1  (parallel-safe within unless marked [S]):
   T-D01  health endpoints
   T-D02  auth (per-user; depends on T-D16a)       — amended by ADR-0061
   T-D03  config env surface
   T-D04  db/litestream config surface
   T-D05  SQLite PRAGMAs (blocks T-D23 in Phase 2)
   T-D06  structured logging
   T-D07  security headers middleware
   T-D08  CSRF
   T-D09  auth rate limit
   T-D10  Dockerfile
   T-D11  docker-compose (blocks T-D21 in Phase 2)
   T-D12  uv.lock reproducibility
   T-D13  CI security scans
   T-D14  audit log client-IP + user + actor_user_id
   T-D15  graceful shutdown
   T-D16a [S] multi-user migration 0012 (blocks T-D02, T-D16, T-D19)
   T-D16  [S] repository user_id scoping sweep + static-analysis test
   T-D17  [S] user admin panel (/settings/users)   — depends on T-D02 + T-D16
   T-D18  [P] password change (/settings/password) — depends on T-D02
   T-D19  [S] admin bootstrap on startup           — depends on T-D02 + T-D16a
   T-D53  [S] session hardening (ADR-0076)         — depends on T-D02, T-D09, T-D18; before T-D27
            │
            ▼
Phase 2  (sequential within):
   bootstrap state bucket → providers → iam → storage → dns → compute →
   cloud-init (now injects ADMIN_EMAIL + ADMIN_INITIAL_PASSWORD) →
   apply(drill) → operator captures admin_initial_password output
            │
            ▼
Phase 3:
   build.yml → deploy.yml (drill) → rollback.yml → promote prod env approval
            │
            ▼
Phase 4:
   restore drill → security scan → smoke (now exercises admin + second user) →
   monitoring → runbooks (now include user-admin.md) → go-live
            │
            ▼
Phase 5  (app items parallel; infra items after Phase 2):
   T-D54 audit-tail scoping · T-D55 no-store · T-D58 secure_delete ·
   T-D59 log hygiene · T-D60 IP/UA purge  [P]
   T-D56 age-encrypted replica → T-D57 37-day ceiling  [S]
   T-D61 data inventory (last)
```

---

## Handoff shape (per task)

Each task file in `phase-N-*/T-Dxx-*.md` MUST declare:

1. **Context** — one paragraph: why this task exists, which ADR drives it.
2. **Deliverables** — concrete file paths, config keys, test names.
3. **Acceptance criteria** — observable signals that make the task "✅".
4. **Dependencies** — explicit `→ T-Dxx` arrows for upstream work.
5. **Validation hook** — the command the next agent (or human) runs to confirm.

The flat index in `tasks.md` is the quick-reference view; detail lives in the task files.

---

## Guardrails

- **Do not** touch `src/budget_planner/` business logic in Phase 1 beyond what the task files prescribe. If a task would require it, stop and add an ADR.
- **Do not** run `terraform apply` outside of CI except for the explicit bootstrap step in `terraform/README.md`.
- **Do not** share secrets through chat, PR descriptions, or commit messages. Secrets flow Terraform → cloud-init → disk only.
- **Do** write a dated line in `docs/CHANGELOG.md` after each merged task, prefixed with the task id.
- **Do** mark the task line in `docs/plans/v3/tasks.md` with `✅` on completion.
