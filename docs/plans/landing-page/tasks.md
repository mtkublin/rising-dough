# Public Landing Page — Tasks

> Plan: [README.md](README.md). Decision: [ADR-0151](../../adr/0151-public-landing-page-on-the-root-domain.md). Requirements: [§13](../../requirements.md#13-public-landing-page-added-2026-11-26).
> Legend: `[P]` parallel-safe, `[S]` sequential, `→ T-LPxx` depends on upstream task.

---

### T-LP01 [P] Hosting facts for decision D1
- **Deliverables**: in `README.md`, a table per host option (GitHub Pages; Scaleway bucket + Edge Services on `www.`; Scaleway bucket behind the prod Caddy) with: root-domain HTTPS (yes/no, how), monthly cost (Edge Services plan price from the Scaleway pricing page), who issues the certificate (for CAA), security headers settable (HSTS, CSP, `X-Frame-Options`), deploy path (workflow, credentials, which GitHub environment), Terraform support for the records and the bucket.
- **Acceptance**: every cell has a source link or a tested result; the operator records D1 as an ADR-0151 amendment.
- **Validation**: review.

### T-LP02 [S] Design round → PR #59 merged
- **Deliverables**: `/designer` round for the landing page and the privacy notice: canvas with light and dark artboards at 375, 1024, 1440; agreed spec `docs/design/specs/landing-page.md`; copy deck; package `docs/design/rising-dough-landing/` (`kind = "extension"`) built by `handoff-builder`.
- **Acceptance**: `just check-handoff docs/design/rising-dough-landing --render --parity <refs> --write-manifest` passes; operator agreed the canvas.
- **Validation**: `just check-handoff …`; UI review per the design gate.

### T-LP03 [S] Landing page source and publish workflow → T-LP02, D1
- **Deliverables**: the static site built from the T-LP02 package (vendored fonts, tokens only, no JS needed, no outside requests); a publish workflow for the chosen host that runs without the `prod` environment's Terraform apply; security headers where the host allows them (ADR-0151 §4).
- **Acceptance**: the frontend visual audit at 375/1024/1440 in both themes shows 0 horizontal scroll, 0 console errors and 0 failed or outside requests; the call to action links to the app's login URL.
- **Validation**: `frontend-visual-audit` record under `docs/audits/`; the workflow run on a branch.

### T-LP04 [S] Root-domain DNS, CAA and certificate → T-LP03
- **Deliverables**: Terraform resources for the root-domain records (A/AAAA or the host's targets, CAA for the host's CA, optional `www`), separate from `module.dns` so an apply never changes the `budget` records; `tfvars.example` and `terraform/README.md` updated; unit or `terraform test` coverage that the app records are unchanged.
- **Acceptance**: `terraform plan` on prod shows only root-domain record additions; after the approved apply, `https://rising-dough.eu` serves the page with a valid certificate and HSTS without `preload`.
- **Validation**: plan output in the PR; `curl -fsSI https://rising-dough.eu/` checked.

### T-LP05 [S] Launch → T-LP04
- **Deliverables**: runbook `docs/plans/v3/runbooks/landing-page.md` (publish, roll back, renew); the external monitor (ADR-0146) checks the root domain; the app's login page links back to the landing page only if the design asks for it.
- **Acceptance**: monitor green 24 h after launch.
- **Validation**: monitor history.

### T-LP06 [S] App subdomain `budget.` → `app.` (only if D2 = `app.`)
- **Deliverables**: ADR-0151 amendment; `subdomain_prod = "app"`; Caddy site `budget.rising-dough.eu` with a 308 redirect to `app.` and records + CAA kept for it; WebAuthn RP ID and origin, trusted hosts follow `hostname` (no code change); `scripts/prod_db_seed.sh` `FQDN` and its test; runbooks and smoke URLs; operator re-registers passkeys.
- **Acceptance**: login with password and a newly registered passkey on `app.`; `budget.` answers 308 to the same path on `app.`; the landing page's call to action points at `app.`.
- **Validation**: prod plan output; post-release checks from the deploy runbook against `app.`.

### T-LP07 [S] Close-out → T-LP05 (and T-LP06 if run)
- **Deliverables**: ADR-0151 status to Accepted (with decided D1/D2); `docs/CHANGELOG.md`; run log.
- **Acceptance**: every task above ✅ or dropped with a reason.
- **Validation**: review.
