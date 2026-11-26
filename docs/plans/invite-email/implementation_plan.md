# Invite Email — Implementation Plan

> Decision: [ADR-0151](../../adr/0151-invite-email-via-scaleway-tem-essential.md) (amends [ADR-0134](../../adr/0134-redesign-scope-decisions-from-the-designer-change-request.md) section 1). Requirements: [`docs/requirements.md` §6.2](../../requirements.md). Tasks: [`tasks.md`](tasks.md).

## Goal

Invites created or resent on `/settings/users` are emailed to the invitee through Scaleway Transactional Email (Essential plan, `fr-par`, HTTPS API). Copy link stays as the fallback. Expected infra cost €0 per month (300 free emails, then €0.25 per 1,000; worst case about €2.43 at the default 10,000 quota).

## Preconditions

All must hold before the task they gate starts. "Check" is how to confirm it.

| # | Precondition | Owner | Gates | Check |
|---|---|---|---|---|
| P1 | ADR-0151 accepted (Proposed → Accepted) and this PR merged; ADR number free on `main` (PRs #54, #59, #60 also use 0151: whichever merges later renumbers) | operator | all | `tests/architecture/test_adr_index.py` green on `main` |
| P2 | `ui/sourdough` (PR #54) merged to `main`: invite pages, users router (`settings_users.py` create and resend), `SETUP_TOKEN_HASH` secret plumbing (`tf_env.py` prod-only entry, compose conditional) that T-IE03 copies | operator | T-IE03..T-IE06 | sourdough merge in `git log main`; `rg SETUP_TOKEN_HASH scripts/ci/tf_env.py` |
| P3 | Already on `main` (ADR-0148, T-UR31): `MailSender`, `MailMessage`, `MailSendError` in `domain/ports.py`; `adapters/mail/noop.py`; `Settings.invite_email_enabled`; `services/invites.py` sends after commit and survives `MailSendError` | — | T-IE04 | present at `4baabf1f` |
| P4 | Scaleway organisation has a payment method and billing in good standing (TEM bills overage even on Essential); operator accepts the TEM terms (Terraform's `accept_tos = true` is that acceptance) | operator | T-IE03 | console, Billing; confirmed in the T-IE02 PR |
| P5 | TEM quota left at the default 10,000 emails/month (the cost cap in ADR-0151 section 8) | operator | T-IE03 | console, TEM quotas |
| P6 | Zone `rising-dough.eu` hosted at Scaleway DNS in the prod project (`managed_dns_zone = true`, `dns_zone_project_id` = prod) | — | T-IE03 | `terraform/envs/prod/terraform.tfvars` |
| P7 | No other service sends mail as `rising-dough.eu`, none planned soon. One SPF record per name: a later sender joins the same record | operator | T-IE03 | `dig +short TXT rising-dough.eu` empty on 2026-11-26; recheck at T-IE03 |
| P8 | Pinned Scaleway provider (`~> 2.46`) has `scaleway_tem_domain` and `scaleway_tem_domain_validation` and exports the SPF, DKIM, DMARC (and MX, if any) values | implementer | T-IE03 | `terraform providers schema -json` |
| P9 | Exact IAM permission-set names for TEM full access and TEM send only | implementer | T-IE02 | `scw iam permission-set list`; recorded in ADR-0151 section 5 |
| P10 | Operator can apply the bootstrap stack locally (ADR-0096 credentials and state access) | operator | T-IE02 | `terraform -chdir=terraform/bootstrap/ci plan` runs |
| P11 | Operator go for the new `ci_environments.toml` prod secret, and adds `MAIL_SCW_SECRET_KEY` to the GitHub `prod` environment (CLAUDE.md, releases) | operator | T-IE02, T-IE03 | `gh secret list --env prod` |
| P12 | httpx is already a runtime dependency (no new dependency) | — | T-IE04 | `pyproject.toml` |
| P13 | Test mailboxes the operator controls at Gmail, Outlook.com, WP.pl, Onet.pl and Interia.pl, plus a mail-tester.com address on the day | operator | T-IE06 | listed in the T-IE06 run doc |
| P14 | DMARC report destination chosen (a mailbox, which needs an MX and mail host, or a free report service) | operator | T-IE07 only | decision noted in T-IE07 |

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
  compose env   : BUDGET_MAIL_TEM_SECRET_KEY, BUDGET_MAIL_TEM_PROJECT_ID, BUDGET_MAIL_FROM (invite@rising-dough.eu),
                  BUDGET_INVITE_EMAIL_ENABLED=true   (only when mail_secret_key != "")
GitHub prod env : MAIL_SCW_SECRET_KEY → tf_env.py → TF_VAR_mail_secret_key
```

## Phases

1. **Docs** (T-IE01, this change): ADR-0151, ADR-0134 amendment, requirements §6.2 and §6.3, this plan and tasks.
2. **Infra, operator-gated** (T-IE02, T-IE03):
   - The operator applies the bootstrap stack locally (ADR-0096 exception) and adds the `MAIL_SCW_SECRET_KEY` secret to the GitHub `prod` environment.
   - The env stack change (module, variable, compose, `tf_env.py`, `ci_environments.toml`) lands by PR. With an empty key it changes nothing on the host, so the PR is safe to release before the app code.
3. **App** (T-IE04, T-IE05): the adapter, settings, wiring and send limit. These are unit-tested with a mocked transport; the default stays off, so no behaviour changes until the key is set.
4. **Release and enable** (T-IE06): release through the normal pipeline with the key empty, then set the key and release again. The operator confirms the TEM domain shows as verified, then runs the deliverability check (below).
5. **Harden** (T-IE07): choose a DMARC report destination; after 30 clean days move to `p=quarantine`.

## Deliverability

Spam placement is managed, not solved by one setting (ADR-0151 section 9).

| Lever | Where |
|---|---|
| SPF, DKIM signed for `rising-dough.eu`, DMARC aligned | T-IE03 |
| From `invite@rising-dough.eu`, Reply-To the inviting admin | T-IE03, T-IE04 |
| Only link on `budget.rising-dough.eu`; no shortener, tracking, images or attachments | T-IE04 |
| Personal subject and body; plain text plus HTML with the same text | T-IE04 |
| Per-admin limit (no bursts) | T-IE05 |
| "Ask them to check spam and mark it not spam" hint to the admin | T-IE05 |
| mail-tester ≥ 9/10; inbox at Gmail, Outlook.com, WP.pl, Onet.pl, Interia.pl with spf/dkim/dmarc pass | T-IE06 |
| TEM dashboard (bounces, complaints, blocklist) and DMARC `rua` reports; `p=quarantine` after 30 clean days | T-IE07 |

Accepted risks: shared IP pool (Essential), young domain (bought 2026-11-04). Not done: BIMI, List-Unsubscribe, Google Postmaster Tools. If a provider still junks the invite, copy link stays the path while content or reputation is fixed; a dedicated IP needs a new ADR.

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
