# Rising Dough v3 — Operator (human-only) checklist

> Everything in v3 that an agent cannot do: account sign-ups, payments, credentials, real-device checks, approvals, and decisions that belong to the operator. Runs in parallel with the agent-driven tasks in [`tasks.md`](tasks.md).
>
> Compiled 2026-11-03, re-checked against merged work 2026-11-04, from `tasks.md`, the phase files, `runbooks/`, `terraform/variables.tf`, and the secrets referenced by `.github/workflows/*.yml`.
>
> Tick items with `[x]` as they are done. Never write secret values into this file.

---

## A. Do now — accounts, tooling, decisions

### A1. Scaleway

- [x] Account data verified, payment method added, identity verification completed (2026-11-04).
- [x] Dedicated project created (2026-11-04): organization **`mk-personal`**, project **`rising-dough`**. Terraform uses only the IDs.
- [x] (2026-11-06, ADR-0092) Second project **`rising-dough-drill`** created for the drill env, id `f2facf0d-f2c9-40cc-8bcb-5b212dc44648`. Prod stays in `rising-dough` (`53175dd0-b944-489b-b05d-3f55d65d79af`), which also owns the DNS zone and the state bucket.
- [ ] Record the **project ID** and **organization ID** in `terraform/envs/{drill,prod}/terraform.tfvars` (gitignored; drill = drill project id, prod = `rising-dough`; both set `dns_zone_project_id` = prod project) and in the GitHub secrets `SCW_DEFAULT_PROJECT_ID` (repo = prod) / `SCW_DEFAULT_ORG_ID`.
- [x] Stardust availability checked (2026-11-03): **sold out in `PL-WAW-1`, available in `PL-WAW-2`.** See [decision D1](#d1-compute-zone-pl-waw-2) for the follow-up the agent needs to make.
- [x] (2026-11-04) Create an **operator API key** (project-admin) for Terraform. Store it in a password manager. It is used locally and as GitHub secrets `SCW_ACCESS_KEY` / `SCW_SECRET_KEY`. Set the key's **preferred Object Storage project to `rising-dough`**. S3 requests carry no project, so buckets land in that project. Done: preferred project set. Keys are stored locally in `terraform/.env` (gitignored, mode 600). They were pasted into an agent chat, so rotate before prod. Then run `scw init` with project `rising-dough`, region `pl-waw`, zone `pl-waw-2`.
- [x] Budget alert created (2026-11-04): budget 10 EUR, threshold 75 % (alerts at 7.50 EUR), delivered by email + SMS.
- [ ] Delivery test (T-D45 acceptance): temporarily lower the threshold so it fires, confirm both email and SMS arrive, then restore it. Expect one false alarm in the month the domain is bought if it is billed through Scaleway.

### A2. Domain and DNS

- [x] Domain registered (2026-11-04): **`rising-dough.eu`**. Hostnames: `budget.rising-dough.eu` (prod) and `drill.budget.rising-dough.eu` (drill). Set as `domain` in both `terraform.tfvars`. `managed_dns_zone` can be set to `true` since the D2 zone-ownership fix landed (T-D63, ADR-0088). See [decision D2](#d2-domain).
- [ ] WHOIS privacy: for `.eu`, EURid hides a private registrant's personal data by default. Confirm with a public WHOIS lookup of `rising-dough.eu`.
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

- [ ] Create GitHub environments `drill`, `prod` (required reviewers, ADR-0037) and `prod-plan` (**no** reviewers; holds the prod values for the PR plan job, ADR-0093). CI never reads a tfvars file; every Terraform input is a secret below. Local runs keep using the gitignored `terraform/envs/<env>/terraform.tfvars`.
- [ ] Add these secrets (S = sensitive). Environment-scoped secrets use the **same name** in each environment; where the scope is "drill / prod / prod-plan", add it to each of the three (`prod-plan` = copy of `prod`).

| Secret | Scope | Terraform var | S | Value comes from |
|---|---|---|---|---|
| `SCW_ACCESS_KEY` | repo | (provider auth, `AWS_ACCESS_KEY_ID`) | yes | Operator IAM API key (access part) |
| `SCW_SECRET_KEY` | repo | (provider auth, `AWS_SECRET_ACCESS_KEY`) | yes | Operator IAM API key (secret part) |
| `SCW_DEFAULT_ORG_ID` | repo | `scaleway_organization_id` | no | `scaleway_organization_id` in local tfvars |
| `SCW_DEFAULT_PROJECT_ID` | drill / prod / prod-plan | `scaleway_project_id` | no | drill: `rising-dough-drill` id; prod and prod-plan: `rising-dough` id (local tfvars) |
| `ADMIN_EMAIL` | repo | `admin_email` | no | local tfvars |
| `APP_DOMAIN` | repo | `domain` | no | local tfvars (`rising-dough.eu`) |
| `OPERATOR_SSH_PUBKEY` | repo | `operator_ssh_pubkey` | yes | local tfvars (public key, treated as sensitive by Terraform) |
| `GITHUB_DEPLOY_PUBKEY` | repo | `github_deploy_pubkey` | yes | public half of the deploy keypair (A4) |
| `GHCR_PULL_PAT` | repo | `ghcr_pull_pat` | yes | read-only GHCR PAT (A3) |
| `LITESTREAM_AGE_IDENTITY` | repo | `litestream_age_identity` | yes | `age-keygen -o litestream-age.key` (whole file or the `AGE-SECRET-KEY-1...` line); same PROD identity for drill |
| `LITESTREAM_AGE_RECIPIENT` | repo | `litestream_age_recipient` | no | `age-keygen -y litestream-age.key` (was a variable; now a secret) |
| `MANAGED_DNS_ZONE` | drill / prod / prod-plan | `managed_dns_zone` | no | `true` or `false`, as in local tfvars (unset = `false`) |
| `BUCKET_ADMIN_PRINCIPALS` | drill / prod / prod-plan | `bucket_admin_principals` | no | HCL/JSON list string, e.g. `["user_id:<uuid>"]` (`scw iam user list`); unset = `[]` |
| `BUCKET_READONLY_PRINCIPALS` | prod / prod-plan | `bucket_readonly_principals` | no | optional list string, e.g. `["application_id:<uuid>"]`; unset = `[]` |
| `PROD_REPLICA_RO_ACCESS_KEY` | drill | `scw_access_key_restore` | yes | `terraform output -raw restore_reader_access_key` (prod state, after the first prod apply) |
| `PROD_REPLICA_RO_SECRET_KEY` | drill | `scw_secret_key_restore` | yes | `terraform output -raw restore_reader_secret_key` (prod state) |
| `DEPLOY_SSH_PRIVATE_KEY` | repo | (not Terraform) | yes | private half of the deploy keypair (A4) |
| `DEPLOY_SSH_KNOWN_HOSTS_DRILL` | drill | (not Terraform) | no | pinned `known_hosts` line of the drill host |

- [ ] List inputs are strings: paste them exactly as HCL/JSON (`["user_id:00000000-0000-0000-0000-000000000000"]`, double quotes). A malformed value fails `terraform plan`.
- [ ] Not secrets (set by the workflow): `TF_VAR_env`, `TF_VAR_github_owner` (repo owner). Defaulted: region, zone, subdomains, `dns_zone_project_id`, `app_image_tag`.
- [ ] The guard `terraform/scripts/check_tf_vars.py` names any missing required secret as `TF_VAR_<name> is empty`.
- [ ] Remove the obsolete repo secret `SCW_DRILL_PROJECT_ID` and variable `LITESTREAM_AGE_RECIPIENT` if you created them (T-D69 / T-D56 scheme).
- [ ] Variables: `DRILL_URL`, `PROD_URL`.
- [ ] Prod must be applied before the first automated restore drill (the `PROD_REPLICA_RO_*` values come from its outputs); the manual T-D25 drill apply can run first without a restore.
- [ ] Optional: `CODEQL_TOKEN`. Without it, the SARIF upload in `security.yml` is skipped.

### A6. Local tooling

- [ ] Terraform **≥ 1.10** (`use_lockfile = true` needs it; on 1.9 there is no state locking).
- [ ] `scw` (then `scw init` with the operator key), `tflint`, `trivy`, `cosign`, `jq`, `sqlite3`.
- [ ] Optional for T-D42: `testssl.sh`, `nikto`.

### A7. Terraform state bootstrap (T-D20)

- [ ] With the operator key exported, run `./terraform/scripts/bootstrap-state.sh` (idempotent).
- [ ] Fill in `terraform/envs/{drill,prod}/terraform.tfvars`. Both were created on 2026-11-04 in the main checkout (gitignored), with the known values (`pl-waw` / `pl-waw-2`, `github_owner = "mtkublin"`) filled in and every remaining field marked `TODO`. `grep -n TODO terraform/envs/*/terraform.tfvars` must print nothing before apply. Still open as of 2026-11-04 (both envs): `admin_email`, `scaleway_project_id`, `scaleway_organization_id`, `operator_ssh_pubkey`, `github_deploy_pubkey`, and `managed_dns_zone` (waits on D2).

### A8. Monitoring account (T-D44)

- [ ] Create an UptimeRobot or Betterstack account. The monitor itself is added after prod exists.

---

### A9. Tailscale (T-D67, ADR-0094)

SSH to the VMs is only possible over the tailnet; port 22 is closed publicly. The app stays public on 80/443 and users never need Tailscale.

- [ ] Create a Tailscale account (Personal plan, free) and install the app on your laptop (and phone). Keep MagicDNS enabled (default).
- [ ] Admin console, Access controls: paste `docs/plans/v3/runbooks/tailscale-acl.hujson` (replace the placeholder owner email with yours). Details in `runbooks/tailscale-ssh.md`.
- [ ] Settings, OAuth clients: create one client with scope **Auth Keys: write** and tags `tag:prod`, `tag:drill`, `tag:ci`. Store the client ID and secret in the password manager.
- [ ] GitHub secrets `TS_OAUTH_CLIENT_ID` and `TS_OAUTH_SECRET`: repo level (used by `terraform.yml`, `deploy.yml`, `rollback.yml`) and in the `drill` environment (used by `restore-drill.yml`); also in the `prod` environment if secrets are environment-scoped.
- [ ] Update secrets `DRILL_HOST` = `budget-planner-drill` and `PROD_HOST` = `budget-planner-prod` (tailnet MagicDNS names, no longer public hostnames). Public `/ready` probes keep using `DRILL_URL` / `PROD_URL`.
- [ ] Local Terraform runs: `export TF_VAR_tailscale_oauth_client_id=...` and `TF_VAR_tailscale_oauth_client_secret=...` (never in tfvars).
- [ ] After the first prod apply, from your laptop on the tailnet: `ssh-keyscan -t ed25519,ecdsa,rsa budget-planner-prod` into the secret `DEPLOY_SSH_KNOWN_HOSTS` (the drill host is scanned at runtime; `DEPLOY_SSH_KNOWN_HOSTS_DRILL` is obsolete).
- [ ] Optional: enable Tailnet Lock (Settings, Device management).

## B. Decisions only the operator can make

### D1. Compute zone: `PL-WAW-2`

**Decided 2026-11-03.** Stardust1-S is sold out in `pl-waw-1` and available in `pl-waw-2`. Region stays `pl-waw`, so Object Storage and the state bucket are unaffected (both are regional).

Follow-up for the agent (docs first, per `CLAUDE.md`). **Done in T-D62 (ADR-0084, 2026-11-04)**, which also fixed the compute image default `ubuntu_jammy` → `ubuntu_noble`:

- Amend ADR-0032 (§Decision and "Region / zone", which currently say `pl-waw-1`).
- Change `terraform/variables.tf` (`scaleway_zone` default), both `terraform/envs/*/terraform.tfvars.example`, and `SCW_DEFAULT_ZONE` in `.github/workflows/restore-drill.yml`.
- Stock moves. Re-check availability right before T-D25 and T-D27, and keep the zone overridable through tfvars.

### D2. Domain

**Bought 2026-11-04 via Scaleway Domains: `rising-dough.eu`.** Its zone already exists at Scaleway, so the second agent follow-up below (collision with an existing zone) applies. The original recommendation follows:

- **Register it through Scaleway Domains and set `managed_dns_zone = true`.** The reason is automation, not price. Every drill apply gets a new flex IP, and Caddy's ACME HTTP-01 challenge only succeeds once DNS points at that IP. The monthly automated restore drill (T-D41) can only update DNS by itself if Terraform owns the zone. With an external zone, `terraform/modules/dns` creates no records at all, so you would have to edit DNS by hand on every drill and the automated drill would fail.
- **TLD:** pick on **renewal** price, not the first-year promotion. `.com` or `.pl` are sensible. `.pl` gives private-individual WHOIS privacy by default.
- **Name:** something neutral. Hostnames are public (certificate-transparency logs), so avoid encoding anything sensitive.
- **Layout:** `budget.<domain>` for prod and `drill.budget.<domain>` for drill (the current defaults).

Follow-up for the agent (Terraform risk, verify before T-D25). **Status 2026-11-06: fix landed in T-D63 ([ADR-0088](../../adr/0088-dns-zone-not-owned-by-env-state.md)).** `module.dns` no longer creates the zone and references the existing Scaleway Domains zone by name, each env managing only its own A/AAAA records. You can set `managed_dns_zone = true` in both `terraform.tfvars`. No import step is needed. If a same-name record was created by hand in the console, delete it before the first apply. The original risk analysis follows:

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
- [x] (done by 2026-11-04: user 1 has email + password + `is_admin`; migrations applied through 0014) **Give your existing local user a login (T-D19, ADR-0069).** Migration 0012 left the pre-v3 user (`id = 1`, name `default`, owner of all your data) with no email, no password and `is_admin = 0`. Once auth lands (T-D02b) you cannot log in as it until you set these. The app will **not** do it at startup on a DB with data. After T-D02b merges and before you rely on login, take an offline backup, then run once against your own DB (you type the password; the agent never runs this on prod):

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
    - Recipient: `age-keygen -y litestream-age.key` (prints `age1...`).
    - Pass both to Terraform as `TF_VAR_litestream_age_identity` (contents of the key file, sensitive) and `TF_VAR_litestream_age_recipient` (public), or in the gitignored `envs/<env>/terraform.tfvars`. Both are required (no defaults) for prod and drill; the drill env uses the **prod** identity.
    - GitHub: add secret `LITESTREAM_AGE_IDENTITY` and variable `LITESTREAM_AGE_RECIPIENT` (used by `terraform.yml` and `restore-drill.yml`).
    - After the first apply follow the cut-over section of `runbooks/restore.md`, then delete the plaintext generations.
  - [ ] T-D57: confirm the 37-day maximum copy age is acceptable (it bounds how far back a restore can go).
  - [ ] T-D61: review `runbooks/data-inventory.md` and its "what the operator can see" statement; decide whether to share it with users now (recommended) or wait for v4's `/privacy` page.
- [x] Cost-alert threshold (T-D45): 10 EUR / 75 %, email + SMS (see A1).
- [ ] Alert email for the uptime monitor (T-D44).
- [x] ~~T-D16 approach preference~~: no longer needed; T-D16 landed (`d2caa91`).

---

## C. Review and testing alongside the agent

- [ ] Review the security-sensitive merges (all landed by 2026-11-04): CSRF (T-D08/T-D08a), security headers (T-D07), user-id scoping (T-D16, ADR-0068), auth backend + web layer (T-D02a/b, ADR-0067/0070), rate limits (T-D09/T-D18a, ADR-0072), admin panel (T-D17, ADR-0073), password policy (T-D18, ADR-0074), session hardening (T-D53, ADR-0076).
- [ ] Passkeys on real devices (T-D02 has landed; ADR-0075 says real-device checks are a human step):
  - [ ] Now, locally: Mac Touch ID and your password manager's passkey support, via `just dev` at `http://localhost:<port>` (not `127.0.0.1`; IP literals are refused).
  - [ ] After drill exists (needs an HTTPS hostname): iPhone and Android against `drill.budget.rising-dough.eu`.
- [ ] Hands-on check with `just dev-demo` on desktop and phone after the CSRF fix.
- [ ] Run `just test-prod-stack` once on your own Docker setup.
- [ ] Read `runbooks/*.md` as the person following them at 2 a.m. Flag any unclear step.

---

## D. Drill environment (T-D25, T-D26)

- [ ] Before the first apply (T-D68, ADR-0091): in both `envs/*/terraform.tfvars` set `bucket_admin_principals = ["user_id:<your user id>"]` (`scw iam user list`). Without it Terraform and you get 403 on the bucket unless you are the Organization owner.
- [x] Prod read-only restore principal is now created by Terraform (`restore-reader`, ADR-0092) and added to the bucket policy automatically; `bucket_readonly_principals` stays empty unless you need extras.
- [ ] `terraform apply -var-file=envs/drill/terraform.tfvars`.
- [ ] If the DNS zone is external: add A/AAAA records for `drill.budget.<domain>` pointing at the flex IP.
- [ ] Put the output of `terraform output -raw admin_initial_password` in the password manager. The T-D25 file still says `admin_fallback_password`; that name is stale.
- [ ] Set `DRILL_HOST` = `budget-planner-drill` (A9). SSH works over the tailnet only; host keys via `ssh-keyscan budget-planner-drill` from your laptop (optionally compare with the Scaleway console serial output).
- [ ] Do the seven post-apply checks in T-D25: health/ready, Observatory, `nslookup`, operator and deploy SSH, bucket exists, Litestream generation.
- [ ] Log in as admin, confirm the forced password change, then change the password.
- [ ] Teardown drill (T-D26). Check in the Scaleway console that nothing billable is left.

## E. Prod (T-D27 onward)

- [ ] Prod apply and GitHub approval. DNS, admin password capture, `PROD_HOST`, `DEPLOY_SSH_KNOWN_HOSTS`.
- [ ] Log in, change the password, register a passkey, create at least one non-admin user.
- [ ] Rollback test (T-D33): approve the deliberately broken deploy and watch the auto-rollback. Run `rollback.yml` once by hand.
- [ ] First restore drill (T-D40): use the prod `restore-reader` key (ADR-0092, from prod Terraform outputs), record audit counts, restore, add a row to `runbooks/restore-log.md`.
- [ ] Smoke journey (T-D43): run it by hand after the deploy, with a second user and a real passkey.
- [ ] External security scan (T-D42): Observatory, testssl.sh, nikto.
- [ ] Uptime monitor (T-D44) on `/health`. Record its ID in `runbooks/disaster-recovery.md` (currently `<TBD>`).
- [ ] Invite the users and deliver their passwords out of band.

## F. Ongoing operations

- [ ] Keep an offline, encrypted copy of the Terraform state (`terraform-state-YYYYMMDD.tar.gz`), which the DR runbook expects.
- [ ] Keep every operator credential in the password manager: Scaleway operator key, read-only restore key, GHCR PAT, both SSH keypairs, admin password, Litestream age identity (T-D56).
- [ ] Approve prod deploys. Read the monthly `restore-drill` results and handle any failure issues.
- [ ] Rotate on schedule: GHCR PAT before expiry; Scaleway keys and the cookie secret via `terraform apply -replace=...` (see `terraform/README.md`).
