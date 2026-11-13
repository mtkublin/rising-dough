# ADR-0032: v3 Remote Deployment — Scaleway Stardust in Warsaw + Scaleway Object Storage

- **Status**: Proposed
- **Date**: 2026-10-27 (renumbered v2 → v3 on 2026-10-28; v2 slot reassigned to the Rising Dough redesign)
- **Related**: ADR-0003 (SQLite only in v1), ADR-0005 (single user, no auth, 127.0.0.1), ADR-0027 (frontend toolchain)
- **Supersedes**: nothing. **Amends**: ADR-0005 (v1 bound to `127.0.0.1`; v3 binds to a container inside a hardened VM behind TLS reverse proxy).
- **Amended by**: [ADR-0084](0084-v3-compute-zone-pl-waw-2-and-ubuntu-noble-image.md) — compute zone is `pl-waw-2` (Stardust sold out in `pl-waw-1`); image slug `ubuntu_noble`.
- **Depends on**: ADR-0033 (auth), ADR-0034 (Litestream replication), ADR-0035 (Terraform IaC), ADR-0036 (Caddy TLS), ADR-0037 (GHA deploy pipeline).

## Context

v1 runs on `127.0.0.1` for a single local user. The next milestone is to make the app reachable from any device the user owns, on the public internet, without turning the project into a scalable multi-tenant product. The research in `local/deployment-options.xlsx` (session 2026-10-27) evaluated 14 compute providers and 8 S3-compatible storage providers against:

- cost (PLN, VAT-aware, Poland FX)
- EU latency from Poland
- SQLite-friendly persistence model (local disk + Litestream to S3)
- deployment ergonomics (IaC maturity, cloud-init, DNS)
- single-user profile (idle most of the day, ~<100 req/day, no autoscaling needed)
- data residency (GDPR, Poland-preferred regions)

The verdict section of that workbook (Scenarios!H12) ranked **Scaleway Stardust in `pl-waw` (Warsaw) + Scaleway Object Storage in `pl-waw`** as the only EU-DC combination that places *both* compute and S3 inside Poland, with mature Terraform support and a 75 GB forever-free object-storage allowance that comfortably covers the SQLite + Litestream snapshot volume.

## Decision

v3 deploys Rising Dough to **one Scaleway Stardust `STARDUST1-S` instance in region `pl-waw` zone `pl-waw-1`** running the app in Docker behind **Caddy** as the TLS-terminating reverse proxy. Durable state (SQLite WAL + snapshots) is **replicated continuously by Litestream** to a **Scaleway Object Storage bucket in `pl-waw`**. All Scaleway resources are provisioned by **Terraform** using the official `scaleway/scaleway` provider.

### 1. Compute

- **Provider / plan**: Scaleway Stardust `STARDUST1-S` (1 shared vCPU, 1 GB RAM, 10 GB local SSD).
- **Region / zone**: `pl-waw` / `pl-waw-1` (Warsaw). *Amended by [ADR-0084](0084-v3-compute-zone-pl-waw-2-and-ubuntu-noble-image.md): zone `pl-waw-2`.*
- **OS**: Ubuntu 24.04 LTS minimal.
- **Addressing**: IPv6 primary; Flex IPv4 attached (ADR-0035 computes the recurring €2.92/mo delta into the cost model).
- **Non-root user**: `app` user owns the app directory; SSH restricted to key auth only; root login disabled.
- **Firewall**: `ufw` default-deny inbound; allow `22/tcp` (SSH, rate-limited by `fail2ban`), `80/tcp` (ACME HTTP-01 challenge), `443/tcp` (HTTPS).
- **Automatic updates**: `unattended-upgrades` enabled for security patches; reboots scheduled 04:00 Europe/Warsaw with Litestream flush hook.

### 2. Application packaging

- **Container image**: multi-stage Dockerfile, non-root `app` user, `python:3.12-slim-bookworm` base (amended by ADR-0102: `python:3.12-slim-trixie`). No shell, no package manager in the final layer.
- **Registry**: GHCR private repository (`ghcr.io/<owner>/budget-planner`). Tagged by git SHA + `vMAJOR.MINOR.PATCH` for releases.
- **Runtime orchestration**: `docker compose` on the host with three services:
  1. `app` — FastAPI/uvicorn container.
  2. `litestream` — official `litestream/litestream:0.3` sidecar replicating `/data/budget.db` to Scaleway Object Storage. See ADR-0034.
  3. `caddy` — reverse proxy, auto-TLS via Let's Encrypt (ACME HTTP-01). See ADR-0036.
- **Shared volume**: `/data` (host-mounted, mode 0700, owned by `app` uid) holds the SQLite file and Litestream metadata. Not an attached Scaleway Block Volume in v3 (10 GB local SSD is sufficient; a Block Volume costs extra and introduces a failure domain that Litestream already covers).

### 3. Durable state (SQLite via Litestream)

- SQLite `budget.db` lives on the host at `/data/budget.db`, WAL mode, `synchronous=NORMAL`, `busy_timeout=5000` (ADR-0029 continues to hold).
- Litestream streams WAL segments to **`s3://budget-planner-prod-pl-waw/db/`** every ~10 s.
- The bucket is created in `pl-waw` with versioning enabled, bucket-level encryption, no public access, and a Scaleway IAM credential scoped read/write to this one bucket (no account-wide key).
- See ADR-0034 for restore procedure and retention policy.

### 4. Reverse proxy & TLS

- Caddy terminates TLS on `:443` for the production hostname (CNAME to be documented in the runbook, e.g. `budget.<user-domain>`).
- Automatic certificate issuance and renewal via Let's Encrypt ACME.
- HTTP/80 is only accepted for the ACME HTTP-01 challenge path; any other request is 308-redirected to HTTPS.
- Security headers injected by Caddy: HSTS (`max-age=31536000; includeSubDomains; preload`), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`, CSP with per-request nonce for scripts.

### 5. Access control

- Internet exposure requires auth. v3 adds **single-user passkey (WebAuthn) authentication** as the primary mechanism, with a **fallback long random password** stored in a password manager for emergency access and WebAuthn credential recovery. See ADR-0033.
- Rate limiting on auth endpoints (`slowapi`) + `fail2ban` jail watching Caddy's access log for repeated auth failures.
- The `user_id = 1` scaffold (ADR-0005) is reused; auth hangs a session on that single user.

### 6. Infrastructure as Code

- **Terraform** (not OpenTofu) with the official `scaleway/scaleway` provider. See ADR-0035.
- Resources managed by Terraform:
  - Scaleway Project + IAM application + IAM policy (least-privilege, scoped to the project).
  - Scaleway Instance (Stardust1-S) + Flex IPv4 + security group.
  - Scaleway Object Storage bucket (`pl-waw`) + bucket policy.
  - Scaleway DNS zone record (A + AAAA for the app subdomain).
  - Cloud-init user-data that bootstraps Docker, Caddy, the `app` user, pulls the latest image, and starts the stack.
- Terraform state stored in a dedicated private Scaleway Object Storage bucket (`budget-planner-tfstate-pl-waw`) with state locking via a DynamoDB-compatible lock table or `use_lockfile = true` (depending on provider version at implementation time; the plan locks this in Phase 2).

### 7. Deployment pipeline

- GitHub Actions:
  - **CI** workflow (existing): `just ci` + build + push image to GHCR tagged by SHA.
  - **CD** workflow (new): on push to `main` with image build success, SSH into the Scaleway VM using a dedicated deploy key, `docker compose pull && docker compose up -d`, run post-deploy health probe, keep previous 2 image tags for one-command rollback.
  - Secrets kept in GitHub Actions encrypted secrets store. The deploy key has `authorized_keys` restricted to `command="/usr/local/bin/deploy-budget-planner"` + `no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty`.
- See ADR-0037 for the pipeline topology and rollback shape.

### 8. Observability (minimal, v3 scope)

- Structured JSON logs on stdout from the app container; captured by `journalctl` + rotated by the host.
- `/health` liveness + `/ready` readiness endpoints (readiness pings the DB).
- External uptime monitor (UptimeRobot or Betterstack free tier) hits `/health` every 5 min; email alert on failure.
- Monthly manual review of Scaleway cost dashboard; soft cost alert configured at 2× expected (PLN) in Scaleway billing.

### 9. Backups and disaster recovery

- Litestream continuous replication is the primary backup.
- A **monthly full-restore drill** restores the database into a scratch VM from the Litestream bucket and verifies row counts + audit log tail against production. First drill is a Phase 4 acceptance gate.
- Full-rebuild RTO target: **< 60 minutes** from a cold `terraform apply` using the current state file + a fresh deploy of the latest image + Litestream restore.
- RPO target: **< 15 seconds** (Litestream default sync cadence).

## Consequences

### Positive

- Both compute and object storage sit in Warsaw → sub-5 ms RTT from Polish ISPs.
- 75 GB object storage free forever covers the SQLite + snapshots indefinitely at this scale.
- Scaleway Terraform provider is mature; the whole stack is reproducible from source.
- Litestream makes the host VM genuinely disposable — the only durable state lives in the bucket.
- Monthly cost at target workload: **~15–20 PLN/mo** (compute ~€3.38 incl. IPv4 + egress inside the 100 Mbps uncapped tier + object storage inside free tier). See `local/deployment-options.xlsx` Scenarios!H12.

### Negative / costs

- Stardust has **no availability SLA** (Scaleway "dev-tier" product). Fine for a single-user personal app; not a product-grade commitment. If the user ever ships this beyond themselves, a tier swap (DEV1-S or PRO2-XXS) is a Terraform variable change.
- Scaleway's IPv4 is attached as a billable **Flex IP** (+€2.92/mo). Without it, we lose compatibility with ISPs that do not route IPv6 reliably.
- One failure domain for compute. Mitigated by Litestream + 60-minute RTO.
- Caddy issues real Let's Encrypt certs during `terraform apply`; rate limits apply (5 duplicate certs / week). The pipeline guards against this by only re-provisioning Caddy's `/data` when the volume is wiped.

### Follow-ups required

- ADR-0033: pin the exact passkey/WebAuthn implementation choice (library + session store).
- ADR-0034: pin Litestream version, retention policy, restore runbook shape.
- ADR-0035: pin Terraform provider version, module layout, state backend configuration.
- ADR-0036: pin Caddy version and Caddyfile shape (headers + ACME storage).
- ADR-0037: pin GitHub Actions workflow + deploy user shell + rollback script contract.

## Alternatives Considered

- **Hetzner Cloud CX22 Nürnberg + Cloudflare R2** — cheapest best-perf combo (research runner-up, Scenarios!H14). Rejected as the top pick because the storage and compute sit in different clouds and Nürnberg is 25 ms vs Warsaw's 5 ms. Kept on the shortlist for a future ADR revisit if Scaleway pricing or availability degrades.
- **Fly.io `waw` region + R2** — Litestream is a first-class Fly pattern. Rejected because the Hobby plan was retired to new signups 2024-10-07; usage-based billing introduces more variance for a personal budget tool whose whole point is predictable costs.
- **Oracle Cloud Always Free Frankfurt + R2** — zero cost. Rejected because the Always Free allowance was halved 2026-06-15 and resources are reclaimed after 7 idle days on free-only accounts; the risk of silently losing the host is unacceptable even with Litestream.
- **GCP Cloud Run Warsaw + GCS** — only hyperscaler PL region. Rejected because Cloud Run has no persistent filesystem; forcing Litestream-on-boot adds 2–10 s cold-start latency and makes the always-on cost pattern messier than keeping a VM.
- **OVH VPS Warsaw + OVH Object Storage** — the only option that invoices with a Polish VAT invoice directly. Kept as a fallback path for the future if the user flips the project under a Polish business entity needing clean invoices; the IaC story in Terraform (`ovh/ovh` provider) is less mature than Scaleway's at the time of this ADR.

## Open Questions

1. Hostname strategy — subdomain of an existing user-owned domain vs a brand-new domain registered through Scaleway Domains. Deferred to the runbook step in Phase 2.
2. Backup bucket geographic redundancy — Scaleway Object Storage in `pl-waw` is already multi-AZ within region. Cross-region replication to `fr-par` adds €0.01/GB storage; defer until data > 10 GB.

## Amendment 2026-11-07 — Sizing note (T-D82)

- **RAM budget.** STARDUST1-S has 1 shared vCPU, 1 GB RAM, 10 GB SSD and no swap. Estimated steady state of the full stack (Ubuntu, Docker, tailscaled, fail2ban, the app with 1 uvicorn worker, Litestream, Caddy) is about 500-800 MB. First boot adds peaks: `package_upgrade: true`, the Docker install, then `docker pull`. On 2026-11-07 the drill VM set its hostname (so cloud-init ran) but stalled for over 18 minutes; OOM is a suspect.
- **Decision.** Add a 1 GiB swapfile (`/swapfile`) created by cloud-init's native `swap:` key (`cc_mounts`, init stage, before package install and `runcmd`), with `vm.swappiness = 10`. It is a peak safety net, not capacity. It costs 1 GB of the 10 GB disk.
- **Measure on drill** with `free -m`, `docker stats --no-stream` and `dmesg | grep -i oom`. Resize to a larger instance type only if steady state exceeds about 700 MB or swap is used continuously.
- **Resizing is manual and incurs downtime** (stop, change type, start; Litestream keeps data safe).
