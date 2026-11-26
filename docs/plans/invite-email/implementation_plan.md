# Invite Email — Implementation Plan

> Decision: [ADR-0151](../../adr/0151-invite-email-via-scaleway-tem-essential.md) (amends [ADR-0134](../../adr/0134-redesign-scope-decisions-from-the-designer-change-request.md) section 1). Requirements: [`docs/requirements.md` §6.2](../../requirements.md). Tasks: [`tasks.md`](tasks.md).

## Goal

Invites created or resent on `/settings/users` are emailed to the invitee through Scaleway Transactional Email (Essential plan, `fr-par`, HTTPS API). Copy link stays as the fallback. Expected infra cost €0 per month (300 free emails, then €0.25 per 1,000; worst case about €2.43 at the default 10,000 quota).

## Preconditions

- `ui/sourdough` (PR #54) is merged to `main`. It carries the invite pages, the users router (`settings_users.py` create and resend) and the `SETUP_TOKEN_HASH` secret plumbing (`tf_env.py` prod-only entry, compose conditional) that T-IE03 copies.
- Already on `main` (precondition release, ADR-0148, T-UR31): `domain/ports.py` `MailSender`, `MailMessage`, `MailSendError`; `adapters/mail/noop.py`; `Settings.invite_email_enabled`; `services/invites.py` sends after commit and survives `MailSendError`.

## Architecture delta

```
admin ──POST /settings/users/invites[/{id}/resend]──▶ router
        └─▶ services/invites.create_invite | resend_invite   (commit first)
              └─▶ invite-email limit (services/rate_limit, per admin 10/h, 30/day)
              └─▶ MailSender.send(MailMessage)                 (after commit)
                    ├─ ScalewayTemMailSender  (switch on, prod)
                    │    POST https://api.scaleway.com/transactional-email/v1alpha1/regions/fr-par/emails
                    │    X-Auth-Token: <budget-planner-prod-mail key>
                    └─ NoopMailSender          (switch off: drill, dev, test)

Terraform (prod only)
  bootstrap/ci  : ci_prod += TEM full access; new app identity budget-planner-prod-mail (send only)
  modules/mail  : scaleway_tem_domain rising-dough.eu + validation
  modules/mail  : TXT SPF (apex), DKIM (<project>._domainkey), DMARC (_dmarc, p=none), MX if exported
  compose env   : BUDGET_MAIL_TEM_SECRET_KEY, BUDGET_MAIL_TEM_PROJECT_ID, BUDGET_MAIL_FROM,
                  BUDGET_INVITE_EMAIL_ENABLED=true   (only when mail_secret_key != "")
GitHub prod env : MAIL_SCW_SECRET_KEY → tf_env.py → TF_VAR_mail_secret_key
```

## Phases

1. **Docs** (T-IE01, this change): ADR-0151, ADR-0134 amendment, requirements §6.2 and §6.3, this plan and tasks.
2. **Infra, operator-gated** (T-IE02, T-IE03):
   - The operator applies the bootstrap stack locally (ADR-0096 exception) and adds the `MAIL_SCW_SECRET_KEY` secret to the GitHub `prod` environment.
   - The env stack change (module, variable, compose, `tf_env.py`, `ci_environments.toml`) lands by PR. With an empty key it changes nothing on the host, so the PR is safe to release before the app code.
3. **App** (T-IE04, T-IE05): the adapter, settings, wiring and send limit. These are unit-tested with a mocked transport; the default stays off, so no behaviour changes until the key is set.
4. **Release and enable** (T-IE06): release through the normal pipeline. The operator confirms the TEM domain shows as verified, then sends one invite to their own address. Check that SPF, DKIM and DMARC all pass in the received headers.
5. **Harden** (T-IE07): after 30 days of clean DMARC results, move to `p=quarantine`.

## Guardrails

- **Prod DB hands-off** (CLAUDE.md). No step needs a prod DB write; the smoke invite goes through the UI after release.
- **No SMTP.** Port 25/465/587 stay blocked; no KYC unblock request.
- **No plan subscription in Terraform.** The project stays on Essential. A Scale plan (€80/month) needs a new ADR.
- **Drill never owns prod-zone records** (ADR-0088, ADR-0101). The `modules/mail` count is `env == "prod" && managed_zone`.
- **Secrets.** The key is never logged, never in tfvars files, and never in job summaries (public repo, ADR-0134 amendment 2026-11-26). `MailMessage.__repr__` stays redacted; the adapter logs only the TEM message id and HTTP status.
- **Guards.** New adapter is network at the edge (allowed in `adapters/`, ADR-0021). No new allowlist entry is expected; if one is needed, it comes with an ADR-0130 amendment.

## Cost

| Item | Monthly |
|---|---|
| TEM Essential, ≤300 emails | €0 |
| TEM Essential, per extra 1,000 | €0.25 |
| DNS records (internal zone) | €0 |
| IAM identity, API key, GitHub secret | €0 |
| **Expected** | **€0** |
| Worst case at the 10,000 default quota | €2.43 |

Prices: Scaleway public product catalog API, 2026-11-26, EUR excl. VAT. Free allowance and quota: Scaleway TEM docs (concepts, FAQ, capabilities and limits).

## Rollback

Set `MAIL_SCW_SECRET_KEY` to empty (or delete it) and release: the compose drops the mail env, the switch is off and the no-op adapter runs, so copy link is the only path again. The TEM domain and DNS records can stay; they cost nothing.
