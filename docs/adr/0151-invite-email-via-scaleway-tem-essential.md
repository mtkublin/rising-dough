# ADR-0151: Invite Email Through Scaleway TEM (Essential Plan, HTTPS API)

- **Status**: Proposed
- **Date**: 2026-11-26
- **Amends**: [ADR-0134](0134-redesign-scope-decisions-from-the-designer-change-request.md) section 1 (the switch may be turned on in prod once this plan lands; the 2026-11-25 NO-GO on `ui/sourdough` is superseded)
- **Relates to**: [ADR-0021](0021-functional-style-no-oop.md) (port and adapter), [ADR-0035](0035-v3-infrastructure-as-code-terraform.md), [ADR-0088](0088-dns-zone-not-owned-by-env-state.md) (zone ownership), [ADR-0096](0096-terraform-state-bootstrap-stack.md), [ADR-0099](0099-release-and-environment-policy.md), [ADR-0100](0100-least-privilege-ci-credentials.md), [ADR-0101](0101-drill-environment-is-tailnet-only.md), [ADR-0104](0104-iam-in-local-bootstrap-no-iammanager-for-ci.md), [ADR-0111](0111-terraform-declared-host-state.md), [ADR-0148](0148-redesign-backend-preconditions-released-first.md)
- **Plan**: [docs/plans/invite-email/](../plans/invite-email/implementation_plan.md), tasks T-IE01..T-IE07

## Context

ADR-0134 section 1 put the invite email behind a switch (`BUDGET_INVITE_EMAIL_ENABLED`, default off) and asked for a cost check first (T-UR18). The precondition release (ADR-0148, T-UR31) shipped the `MailSender` port, `MailMessage` (redacted repr), `MailSendError`, the no-op adapter and the invite service call after commit. On 2026-11-25 the operator said NO-GO for v1 and admins copy the link by hand. On 2026-11-26 the operator asked for the real email after all, on the cheapest option.

Cost check (2026-11-26, Scaleway public product catalog API `api.scaleway.com/product-catalog/v2alpha1/public-catalog/products`, EUR excl. VAT; plan limits from the Scaleway TEM docs):

| Item | Price |
|---|---|
| TEM Essential, per email (`/paas/tem/essential_emails/fr-par`) | €0.00025 (€0.25 per 1,000), no plan fee |
| Essential free allowance | 300 emails per month |
| Essential limits | up to 5 domains, 1 webhook per domain, shared IPs, default quota 10,000 emails per month |
| TEM Scale plan (`/paas/tem/scale_plan/fr-par`) | €80 per month (not used) |
| DNS records in the Scaleway-registered zone (`internal zone`) | €0 |
| IAM application and key, GitHub secret | €0 |

Expected use is a few invites a month, so the cost is **€0 per month**. The worst case under the default quota is (10,000 - 300) x €0.00025 = **€2.43 per month**. TEM runs only in `fr-par` (no `pl-waw` SKU in the catalog); that is still in the EU.

Scaleway Instances block outbound SMTP (ports 25, 465, 587, 2465) until the account passes identity verification and the security group enables SMTP. The HTTPS API on port 443 is not blocked: the security group already has `outbound_default_policy = "accept"` (ADR-0145 section 7 relies on the same path).

Polish providers were looked at (EmailLabs and MessageFlow by Vercom, Poznań). They add a vendor, an account and a secret outside Terraform, and have no Terraform provider. Their free tiers could not be confirmed. TEM costs the same (€0), reuses the Scaleway provider, IAM, billing and DNS module, and keeps data in the EU.

## Decision

1. **Provider and plan.** Scaleway Transactional Email, **Essential plan**, region `fr-par`. Terraform never creates a plan subscription, so the project stays on Essential. A move to Scale (€80) needs a new ADR.
2. **Transport: HTTPS API, not SMTP.** `POST https://api.scaleway.com/transactional-email/v1alpha1/regions/fr-par/emails` with `X-Auth-Token`. No security-group change, no SMTP unblock, no KYC request.
3. **Sending domain.** The apex `rising-dough.eu` (registered at Scaleway, zone in the prod project, no existing SPF, DMARC or MX records on 2026-11-26). From: `Rising Dough <no-reply@rising-dough.eu>`. Reply-To: the inviting admin's email, so a reply reaches a person. Plain text only (as `MailMessage` is today).
4. **DNS, prod only.** A new Terraform module `modules/mail` (prod env only, `managed_zone = true`; the drill never touches the prod zone, ADR-0088, ADR-0101) creates:
   - `scaleway_tem_domain` (`accept_tos = true`, region `fr-par`, prod project) and `scaleway_tem_domain_validation`;
   - `scaleway_domain_record` TXT records from the domain's exported attributes: SPF on the apex (`v=spf1 include:_spf.tem.scaleway.com -all`), DKIM at `<project_id>._domainkey`, DMARC at `_dmarc` starting with `p=none`; plus the MX record TEM exports for bounce handling, if the provider exports one.
   - DMARC moves to `p=quarantine` after 30 days of clean TEM reports (T-IE07).
5. **IAM (bootstrap stack, operator applies, ADR-0096, ADR-0104).**
   - `ci_prod` gains the TEM full-access permission set on the prod project, so the prod env stack can manage the TEM domain.
   - A new identity `budget-planner-prod-mail` holds only the send permission set on the prod project (least privilege: it cannot read logs, manage domains or touch storage). Its secret key goes to the GitHub `prod` environment as `MAIL_SCW_SECRET_KEY`. Exact permission-set names are checked against `scw iam permission-set list` during T-IE02.
6. **Secret path (same pattern as `SETUP_TOKEN_HASH`, ADR-0134 amendment 2026-11-25).** `MAIL_SCW_SECRET_KEY` is declared in `tests/architecture/ci_environments.toml` (prod only) and mapped in `scripts/ci/tf_env.py` to the sensitive Terraform variable `mail_secret_key` (default empty). The compose template renders `BUDGET_MAIL_TEM_SECRET_KEY`, `BUDGET_MAIL_TEM_PROJECT_ID`, `BUDGET_MAIL_FROM` and `BUDGET_INVITE_EMAIL_ENABLED=true` **only when the key is non-empty**. Empty key: the switch stays off and the no-op adapter runs (drill, dev, test).
7. **App.**
   - New adapter `adapters/mail/scaleway_tem.py`: one httpx call (httpx is already a dependency), timeout 10 s, no in-request retry. Any transport error or non-2xx answer raises `MailSendError`; the existing service behaviour stands (the invite stays valid, the admin sees that the email failed and can copy the link). The adapter never logs the recipient, subject, body or key; it logs the TEM message id and status.
   - Settings: `mail_tem_secret_key` (secret type), `mail_tem_project_id`, `mail_tem_region` (default `fr-par`), `mail_from`. Startup fails if `invite_email_enabled` is on and the key, project id or sender is missing.
   - The adapter is chosen at the edge (app factory): TEM when the switch is on, `NoopMailSender` otherwise. The canonical "Outbound mail" row in CLAUDE.md and `canonical_modules.toml` names the new adapter.
8. **Abuse and cost guard.** Invite emails are limited per admin: 10 per hour and 30 per day, through `services/rate_limit.py` (create and resend both count). Over the limit the invite is still created or renewed and the email is skipped; the admin is told to copy the link. The TEM monthly quota (10,000) is the backstop, capping the bill at about €2.43.
9. **Scope.** Invite emails only. Password reset by email stays out of scope (requirements §6.8). No webhooks, no tracking pixels, no marketing mail.
10. **Release.** Prod goes through the normal pipeline (ADR-0099). The operator applies the bootstrap stack, adds the secret, releases, then sends one invite to their own address as the smoke test (T-IE06). Drills keep the no-op adapter.

## Consequences

- Admins no longer need to pass the invite link by hand; the copy-link flow stays as the fallback when the email fails or the limit is hit.
- One more prod secret and one more IAM identity; both live in the bootstrap stack and the GitHub `prod` environment like the existing ones.
- Invite emails (recipient address, subject, body with a 7-day link) pass through Scaleway TEM in `fr-par` and stay in TEM's logs for its retention period. Scaleway TEM is listed as a place user data passes through in `docs/plans/v3/runbooks/data-inventory.md` (T-IE04).
- Expected infra cost €0 per month; hard worst case about €2.43 per month at the default quota.
- Implementation lands after `ui/sourdough` (PR #54) merges, because the invite pages, the users router and the `SETUP_TOKEN_HASH` secret plumbing this reuses are on that branch.
