# Rising Dough v3 — Operator (human-only) checklist

> Everything in v3 that an agent cannot do: account sign-ups, payments, credentials, real-device checks, approvals, and decisions that belong to the operator. Runs in parallel with the agent-driven tasks in [`tasks.md`](tasks.md).
>
> Compiled 2026-11-03 from `tasks.md`, the phase files, `runbooks/`, `terraform/variables.tf`, and the secrets referenced by `.github/workflows/*.yml`.
>
> Tick items with `[x]` as they are done. Never write secret values into this file.

---

## A. Do now — accounts, tooling, decisions

### A1. Scaleway

- [x] Account data verified, payment method added, identity verification completed (2026-11-04).
- [x] Dedicated project created (2026-11-04): organization **`mk-personal`**, project **`rising-dough`**. Terraform uses only the IDs.
- [ ] Record the **project ID** and **organization ID** in `terraform/envs/{drill,prod}/terraform.tfvars` (gitignored; already created with `TODO` markers) and in the GitHub secrets `SCW_DEFAULT_PROJECT_ID` / `SCW_DEFAULT_ORG_ID`.
- [x] Stardust availability checked (2026-11-03): **sold out in `PL-WAW-1`, available in `PL-WAW-2`.** See [decision D1](#d1-compute-zone-pl-waw-2) for the follow-up the agent needs to make.
- [ ] Create an **operator API key** (project-admin) for Terraform. Store it in a password manager. It is used locally and as GitHub secrets `SCW_ACCESS_KEY` / `SCW_SECRET_KEY`. Set the key's **preferred Object Storage project to `rising-dough`**. S3 requests carry no project, so buckets land in that project. Then run `scw init` with project `rising-dough`, region `pl-waw`, zone `pl-waw-2`.
- [x] Budget alert created (2026-11-04): budget 10 EUR, threshold 75 % (alerts at 7.50 EUR), delivered by email + SMS.
- [ ] Delivery test (T-D45 acceptance): temporarily lower the threshold so it fires, confirm both email and SMS arrive, then restore it. Expect one false alarm in the month the domain is bought if it is billed through Scaleway.

### A2. Domain and DNS

- [ ] Register the domain. See [decision D2](#d2-domain) for the recommended approach (Scaleway Domains, `managed_dns_zone = true`).
- [ ] Enable WHOIS privacy (automatic for individuals on `.pl`; check for other TLDs).
- [ ] Optional: add a CAA record allowing `letsencrypt.org`.
- [ ] Note that HSTS `includeSubDomains; preload` is served for the app hostname. Nothing under `budget.<domain>` may need plain HTTP.

### A3. GitHub (`mtkublin/budget-planner`)

- [ ] Install `gh` locally (`brew install gh` + `gh auth login`). The runbooks use it.
- [ ] Turn on 2FA on the GitHub account.
- [ ] Create environments **`drill`** and **`prod`**. Add yourself as a required reviewer on `prod`.
  - **Caveat:** on a free account, environment required reviewers only work on **public** repos. A private repo needs GitHub Pro, or the ADR-0037 prod-approval gate is silently absent.
- [ ] Add branch protection on `main`: required status checks, no force-push.
- [ ] Under Settings → Actions, allow workflows to create issues. `restore-drill.yml` opens `restore-drill-failure-YYYY-MM` on failure.
- [ ] Create a GHCR pull token (classic PAT, `read:packages` only) for `GHCR_PULL_PAT` / `TF_VAR_ghcr_pull_pat`. Add a calendar reminder for its expiry.
- [ ] After the first `build.yml` run, check that the GHCR package is linked to the repo and that Actions has access to it.
- [ ] Be aware that cosign keyless signing writes the repo and workflow identity to the public Rekor log, even for a private repo.

### A4. SSH keys

- [ ] Operator key: `ssh-keygen -t ed25519 -C operator@laptop`. The public key goes to `operator_ssh_pubkey` / `OPERATOR_SSH_PUBKEY`.
- [ ] Separate deploy keypair for GitHub Actions. The private key goes to `DEPLOY_SSH_PRIVATE_KEY`; the public key goes to `GITHUB_DEPLOY_PUBKEY`. Keep both in the password manager (the DR runbook assumes it).

### A5. GitHub secrets and variables (pre-apply)

- [ ] Secrets: `SCW_ACCESS_KEY`, `SCW_SECRET_KEY`, `SCW_DEFAULT_PROJECT_ID`, `SCW_DEFAULT_ORG_ID`, `ADMIN_EMAIL`, `APP_DOMAIN`, `OPERATOR_SSH_PUBKEY`, `GITHUB_DEPLOY_PUBKEY`, `GHCR_PULL_PAT`, `DEPLOY_SSH_PRIVATE_KEY`. <!-- pragma: allowlist secret -->
- [ ] Variables: `APP_DOMAIN`, `DRILL_URL`, `PROD_URL`.
- [ ] Duplicate the needed secrets into the **`drill` environment**, because `restore-drill.yml` reads environment-scoped secrets.
- [ ] Optional: `CODEQL_TOKEN`. Without it, the SARIF upload in `security.yml` is skipped.

### A6. Local tooling

- [ ] Terraform **≥ 1.10** (`use_lockfile = true` needs it; on 1.9 there is no state locking).
- [ ] `scw` (then `scw init` with the operator key), `tflint`, `trivy`, `cosign`, `jq`, `sqlite3`.
- [ ] Optional for T-D42: `testssl.sh`, `nikto`.

### A7. Terraform state bootstrap (T-D20)

- [ ] With the operator key exported, run `./terraform/scripts/bootstrap-state.sh` (idempotent).
- [ ] Fill in `terraform/envs/{drill,prod}/terraform.tfvars`. Both were created on 2026-11-04 in the main checkout (gitignored), with the known values (`pl-waw` / `pl-waw-2`, `github_owner = "mtkublin"`) filled in and every remaining field marked `TODO`. `grep -n TODO terraform/envs/*/terraform.tfvars` must print nothing before apply.

### A8. Monitoring account (T-D44)

- [ ] Create an UptimeRobot or Betterstack account. The monitor itself is added after prod exists.

---

## B. Decisions only the operator can make

### D1. Compute zone: `PL-WAW-2`

**Decided 2026-11-03.** Stardust1-S is sold out in `pl-waw-1` and available in `pl-waw-2`. Region stays `pl-waw`, so Object Storage and the state bucket are unaffected (both are regional).

Follow-up for the agent (docs first, per `CLAUDE.md`):

- Amend ADR-0032 (§Decision and "Region / zone", which currently say `pl-waw-1`).
- Change `terraform/variables.tf` (`scaleway_zone` default), both `terraform/envs/*/terraform.tfvars.example`, and `SCW_DEFAULT_ZONE` in `.github/workflows/restore-drill.yml`.
- Stock moves. Re-check availability right before T-D25 and T-D27, and keep the zone overridable through tfvars.

### D2. Domain

**No domain owned yet.** Recommendation:

- **Register it through Scaleway Domains and set `managed_dns_zone = true`.** The reason is automation, not price. Every drill apply gets a new flex IP, and Caddy's ACME HTTP-01 challenge only succeeds once DNS points at that IP. The monthly automated restore drill (T-D41) can only update DNS by itself if Terraform owns the zone. With an external zone, `terraform/modules/dns` creates no records at all, so you would have to edit DNS by hand on every drill and the automated drill would fail.
- **TLD:** pick on **renewal** price, not the first-year promotion. `.com` or `.pl` are sensible. `.pl` gives private-individual WHOIS privacy by default.
- **Name:** something neutral. Hostnames are public (certificate-transparency logs), so avoid encoding anything sensitive.
- **Layout:** `budget.<domain>` for prod and `drill.budget.<domain>` for drill (the current defaults).

Follow-up for the agent (Terraform risk, verify before T-D25):

- `module.dns` creates `scaleway_domain_zone` for the **whole domain** in **each** env's state when `managed_zone = true`. Two states would then own one zone, and `terraform destroy` on drill (T-D26, and every monthly drill) could delete the zone and with it the prod records. The zone should be owned once (e.g. created at bootstrap or in a shared state, or referenced as a data source), with each env managing only its own A/AAAA records.
- A domain registered at Scaleway Domains already comes with its zone, so a `scaleway_domain_zone` with `subdomain = ""` may collide with it. Confirm the behaviour against the provider docs.
- Either fix belongs in an ADR-0035 amendment before code.

### D3. Other operator decisions

- [ ] Bootstrap admin email (`admin_email`).
- [ ] **How existing data reaches prod.** `data/budget.sqlite` holds the real data and no v3 task covers moving it. Choose one:
  - start fresh;
  - upload a migrated copy once before first boot (migrations 0012/0013 run on a copy, then a Litestream replicate);
  - re-enter the data by hand.

  Whichever is chosen likely needs a new task, and possibly an ADR.
- [ ] **Before any migration work, take an offline backup of `data/budget.sqlite`.**
- [ ] **Give your existing local user a login (T-D19, ADR-0069).** Migration 0012 left the pre-v3 user (`id = 1`, name `default`, owner of all your data) with no email, no password and `is_admin = 0`. Once auth lands (T-D02b) you cannot log in as it until you set these. The app will **not** do it at startup on a DB with data. After T-D02b merges and before you rely on login, take an offline backup, then run once against your own DB (you type the password; the agent never runs this on prod):

  ```sh
  cp data/budget.sqlite data/budget.sqlite.bak-$(date +%Y%m%d)
  just migrate                       # only if 0012–0014 are not applied yet
  just set-password --db=data/budget.sqlite --user-id=1 --set-email=<your email> --make-admin
  ```

  Check: `just dev`, log in with that email and password. Do the same for `data/demo.sqlite` if you use `just dev-demo` (e.g. `--set-email=admin@local.test`), or rebuild it after the demo builder learns to set a login.
- [ ] The other users (up to about 10) and how their one-time passwords are delivered out of band.
- [ ] Privacy: hosting others' financial data makes the operator a GDPR controller. Decide on a short privacy note. Hard-delete is out of v3 scope.
- [ ] **Data-protection quick wins (Phase 5, ADR-0078).**
  - [ ] T-D56: generate the Litestream age identity (`age-keygen -o litestream-age.key`), store it in the password manager, set the Terraform sensitive variable. Losing it makes the encrypted replica unrecoverable.
  - [ ] T-D57: confirm the 37-day maximum copy age is acceptable (it bounds how far back a restore can go).
  - [ ] T-D61: review `runbooks/data-inventory.md` and its "what the operator can see" statement; decide whether to share it with users now (recommended) or wait for v4's `/privacy` page.
- [ ] Cost-alert threshold (T-D45) and alert email (T-D44).
- [ ] T-D16 approach preference (the first attempt was reverted in `946330b`).

---

## C. Review and testing alongside the agent

- [ ] Review the security-sensitive merges: CSRF (T-D08/T-D08a), security headers (T-D07), user-id scoping (T-D16), auth (T-D02).
- [ ] Passkeys on real devices once T-D02 lands: Mac Touch ID, iPhone, Android, and your password manager's passkey support.
- [ ] Hands-on check with `just dev-demo` on desktop and phone after the CSRF fix.
- [ ] Run `just test-prod-stack` once on your own Docker setup.
- [ ] Read `runbooks/*.md` as the person following them at 2 a.m. Flag any unclear step.

---

## D. Drill environment (T-D25, T-D26)

- [ ] `terraform apply -var-file=envs/drill/terraform.tfvars`.
- [ ] If the DNS zone is external: add A/AAAA records for `drill.budget.<domain>` pointing at the flex IP.
- [ ] Put the output of `terraform output -raw admin_initial_password` in the password manager. The T-D25 file still says `admin_fallback_password`; that name is stale.
- [ ] Set `DRILL_HOST` and `DEPLOY_SSH_KNOWN_HOSTS_DRILL` (from `ssh-keyscan`; verify the fingerprint against the Scaleway console serial output).
- [ ] Do the seven post-apply checks in T-D25: health/ready, Observatory, `nslookup`, operator and deploy SSH, bucket exists, Litestream generation.
- [ ] Log in as admin, confirm the forced password change, then change the password.
- [ ] Teardown drill (T-D26). Check in the Scaleway console that nothing billable is left.

## E. Prod (T-D27 onward)

- [ ] Prod apply and GitHub approval. DNS, admin password capture, `PROD_HOST`, `DEPLOY_SSH_KNOWN_HOSTS`.
- [ ] Log in, change the password, register a passkey, create at least one non-admin user.
- [ ] Rollback test (T-D33): approve the deliberately broken deploy and watch the auto-rollback. Run `rollback.yml` once by hand.
- [ ] First restore drill (T-D40): create a **read-only** Scaleway key for the prod bucket, record audit counts, restore, add a row to `runbooks/restore-log.md`.
- [ ] Smoke journey (T-D43): run it by hand after the deploy, with a second user and a real passkey.
- [ ] External security scan (T-D42): Observatory, testssl.sh, nikto.
- [ ] Uptime monitor (T-D44) on `/health`. Record its ID in `runbooks/disaster-recovery.md` (currently `<TBD>`).
- [ ] Invite the users and deliver their passwords out of band.

## F. Ongoing operations

- [ ] Keep an offline, encrypted copy of the Terraform state (`terraform-state-YYYYMMDD.tar.gz`), which the DR runbook expects.
- [ ] Keep every operator credential in the password manager: Scaleway operator key, read-only restore key, GHCR PAT, both SSH keypairs, admin password, Litestream age identity (T-D56).
- [ ] Approve prod deploys. Read the monthly `restore-drill` results and handle any failure issues.
- [ ] Rotate on schedule: GHCR PAT before expiry; Scaleway keys and the cookie secret via `terraform apply -replace=...` (see `terraform/README.md`).
