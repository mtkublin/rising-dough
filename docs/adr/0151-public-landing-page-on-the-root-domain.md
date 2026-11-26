# ADR-0151: A Public Landing Page on the Root Domain; the App Stays on a Subdomain

- **Status**: Proposed (two open decisions, §6)
- **Date**: 2026-11-26
- **Amends**: none. Leaves [ADR-0101](0101-drill-environment-is-tailnet-only.md) (prod answers on `<subdomain>.<domain>`) and [ADR-0067](0067-auth-backend-sessions-and-passkey-challenges.md) §1 (WebAuthn RP ID = the app hostname) as they are.
- **Related**: [ADR-0035](0035-v3-infrastructure-as-code-terraform.md), [ADR-0036](0036-v3-reverse-proxy-caddy-auto-tls.md), [ADR-0088](0088-dns-zone-not-owned-by-env-state.md), [ADR-0092](0092-drill-in-separate-scaleway-project.md), [ADR-0099](0099-release-and-environment-policy.md), [ADR-0113](0113-csp-compatible-frontend.md); design gate ADR-0154 / ADR-0155 (open PR #59, `chore/designer-handoff`)
- **Requirements**: [`docs/requirements.md` §13](../requirements.md#13-public-landing-page-added-2026-11-26)
- **Tasks**: T-LP01 to T-LP07 (`docs/plans/landing-page/tasks.md`)

> ADR number: 0151 is the next number on `main` (G14 forbids gaps). Open PRs #54, #59 and #60 also claim 0151 and up; whichever merges later renumbers.

## Context

Prod answers on `budget.rising-dough.eu` (`terraform/envs/prod/terraform.tfvars`: `domain = "rising-dough.eu"`, `subdomain_prod = "budget"`, `managed_dns_zone = true`). The root domain `rising-dough.eu` has only its NS records (checked 2026-11-26: no A, AAAA, MX, TXT or CAA), and no other subdomain is in use.

The operator wants a nicer public URL for product and marketing reasons. Two shapes were compared (operator session 2026-11-26):

1. **Move the app to the root domain** (`subdomain_prod = ""`) with a 308 redirect from `budget.`.
2. **Put a static landing page on the root domain** (general product info and a button into the app), and keep the app on a subdomain.

What option 1 costs:

- **Passkeys break.** The WebAuthn RP ID is the hostname (`docker-compose.yml.tpl`: `BUDGET_WEBAUTHN_RP_ID: "${hostname}"`). A passkey for `budget.rising-dough.eu` cannot be used on `rising-dough.eu`, because an RP ID must equal the origin's domain or be a suffix of it. Every passkey has to be registered again. Related-origin requests (WebAuthn L3 `/.well-known/webauthn`) could bridge this, but browser support is uneven.
- **Every user starts over once.** Sessions (host-only cookies), browser storage, the offline cache and home-screen installs all belong to the old origin. Password-manager entries match by hostname.
- **HSTS covers the whole zone.** The app sends `max-age=31536000; includeSubDomains; preload` (Caddyfile and `security_headers.py`). On the root domain that binds every present and future subdomain to HTTPS for a year, and makes the root domain eligible for the browser preload list, which is hard to leave.
- **Root-domain CAA covers the whole zone.** Every name without its own CAA records would be limited to Let's Encrypt and Sectigo.
- **The app takes the brand's front door.** A later landing page, docs or status page needs the root domain, so the app would move a second time, with real users by then.
- **The root domain cannot be a CNAME,** so a later CDN or load balancer depends on apex aliasing support.
- **Prod-only change.** The drill is tailnet-only and creates no public DNS (ADR-0101), so the DNS and certificate path only runs for real on prod.
- **A redirect has to stay up** (old certificate, records, 308 site) for invite links and bookmarks.

With a single user today, the per-user costs are a few clicks. The structural costs (front door, HSTS, CAA, apex hosting) remain.

Option 2 avoids all of them: the app's hostname does not change, and the root domain carries only static content.

## Decision

### 1. The root domain serves a static landing page

`https://rising-dough.eu` serves a static landing page: general product info and a call to action that links to the app's login. No login, no cookies and no app data on the landing origin. Analytics and third-party scripts are out of scope (§5). A cookie consent banner would be needed only once trackers are added.

### 2. The app keeps its own subdomain

The app stays on `<subdomain_prod>.rising-dough.eu`. No Terraform `fqdn` change, no WebAuthn RP ID change, no redirect. Which subdomain is open decision §6.2 (`budget.` today, `app.` proposed). If it changes, that is its own task (T-LP06) with the migration costs listed above, which are small while the operator is the only user.

### 3. Hosting is separate from the app's release pipeline

The landing page is published without a prod Terraform apply. A copy edit must not need the prod approval gate, and an app outage should not take the landing page down. Which host is open decision §6.1.

### 4. DNS, HSTS and CAA on the root domain

- The root domain's records are Terraform-managed in the existing zone (ADR-0088: records only, never the zone; ADR-0092: zone in the prod project). They are a separate resource set from the app's `budget` records, so the app's records never change in a landing-page apply.
- **HSTS on the root domain:** `max-age=31536000; includeSubDomains`, **without `preload`**. There are no other subdomains, so `includeSubDomains` costs nothing today. Submitting to the preload list needs its own ADR. Where the host sets the headers (§6.1), the security headers of the app's Caddyfile apply as far as they fit a static page: `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options DENY`, and a strict CSP with no inline script.
- **CAA on the root domain** lists only the CA the chosen host issues from. Names other than `budget` and the root domain get their own CAA records when they are added.
- `www.rising-dough.eu`: either a 308 redirect to the root domain, or no record. Decided with §6.1.

### 5. Scope

- In scope: one static page (light and dark themes, mobile first, no JS required), the shared product imagery and copy, a short privacy notice (the page collects nothing), and a link to the app.
- Out of scope: signup on the landing page (invites stay in the app, ADR-0134), pricing, blog, docs, analytics, a newsletter form, i18n beyond the app's language.

### 6. Open decisions (operator, tbd)

#### 6.1 Host: Scaleway Object Storage website (preferred) or GitHub Pages

Facts found 2026-11-26 (to recheck at T-LP01):

- **A Scaleway bucket website alone cannot serve `https://rising-dough.eu`.** A custom domain on a bucket website is a CNAME to the bucket endpoint (not possible at the root domain), and HTTPS on a custom domain needs **Scaleway Edge Services**, a paid monthly plan per project. Edge Services takes subdomains only, not a primary domain ([Edge Services custom domain docs](https://www.scaleway.com/en/docs/network/edge-services/how-to/configure-custom-domain), [Edge Services FAQ](https://www.scaleway.com/en/docs/edge-services/faq)). The plan price was not found and is to be checked on the Scaleway pricing page.
- So the Scaleway variants are:
  - **(a) Bucket + Edge Services on `www.`**, with the root domain redirecting to `www.`. The root-domain redirect still needs a host with an A record: either the prod Caddy (couples the root domain to the prod VM again) or a redirect service. Cost: the Edge Services plan, plus storage of a few cents.
  - **(b) Bucket behind the prod Caddy:** a `rising-dough.eu` site block that reverse-proxies the bucket website endpoint. No extra cost, content is published by a bucket upload and not by a release, but the root domain goes down with the VM and the Caddyfile change itself ships in a prod release.
- **GitHub Pages** serves a root domain over HTTPS for free with A/AAAA records to GitHub's addresses and Let's Encrypt certificates. A private repository needs a paid GitHub plan. Content would live in this repo (a Pages workflow) or a separate public repo.

Recommendation for the operator decision: GitHub Pages if a public repo for the landing page is acceptable (free, independent of the VM, real root-domain HTTPS). Otherwise Scaleway (a), once the Edge Services price is known. Option (b) only as a stopgap. Recorded as an amendment to this ADR when decided.

#### 6.2 App subdomain: `budget.` or `app.`

- `app.` is the common SaaS convention next to a landing page and stays true if the product grows past budgeting (goals, starter, fortune tracking). It reads as "the product", where `budget.` reads as one feature.
- `budget.` is descriptive, already live, already on every runbook, and costs nothing.
- The difference is cosmetic. It is worth acting on only together with the landing page launch (so the call to action points at the final name), and while there is one user. Moving later means real users re-register passkeys.
- Recommendation: move to `app.` in the same release window as the landing page, or keep `budget.` for good. Don't move later.

### 7. Design

The landing page is a new screen, so it goes through the design gate: a `/designer` round (light and dark artboards at 375, 1024, 1440), an agreed spec under `docs/design/specs/`, and a package built by `handoff-builder` as an `extension` of the base package using the shared design system (ADR-0154 §3, §6 as amended by ADR-0155 §2). Tokens only, both themes, vendored fonts (no Google Fonts, ADR-0113). The design gate lives on PR #59. The design task (T-LP02) waits until it merges.

## Consequences

- No change to the app, its hostname, passkeys, sessions or the prod release path for the landing page itself (§3). The app stays on its own origin, so any future landing-page scripts never share an origin with the app.
- One more public surface to keep current: copy, a privacy notice, and certificate renewal on the chosen host.
- Root-domain HSTS without `preload` binds future subdomains to HTTPS for a year. That is intended, and it is reversible by lowering `max-age`.
- Option (b) of §6.1 would couple the root domain to the prod VM. That coupling is accepted only as a stopgap.
- If §6.2 picks `app.`, the per-user migration costs from the Context apply once (single user today). Runbooks, `scripts/prod_db_seed.sh` (`FQDN`), its test, and the smoke URLs change with it.

## Alternatives considered

- **Move the app to the root domain** (option 1). Rejected for the reasons in the Context: front door taken, zone-wide HSTS and CAA, apex hosting limits, a second migration later.
- **Landing page served by the app** (a public `/` route). Rejected: `/` is `303 /today` (ADR-0077). It would put marketing content and its release cadence into the app, under the app's CSP and auth middleware.
- **Redirect the root domain to the app only** (no page). Possible as a stopgap until the page ships, but it gives no product information.
