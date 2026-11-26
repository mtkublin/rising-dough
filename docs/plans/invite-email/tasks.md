# Invite Email — Tasks

> Plan: [implementation_plan.md](implementation_plan.md). Decision: [ADR-0151](../../adr/0151-invite-email-via-scaleway-tem-essential.md).
> Legend: `[P]` parallel-safe, `[S]` sequential, `→ T-IExx` depends on upstream task. Every implementation task waits for `ui/sourdough` (PR #54) to merge.

---

### ✅ T-IE01 [S] Document the plan
- **Deliverables**: ADR-0151 (incl. section 9 deliverability); ADR-0134 amendment; `docs/requirements.md` §6.2 (invite email on, via TEM) and §6.3 (TEM domain in Terraform); this plan; CHANGELOG line.
- **Acceptance**: `just guards` green (ADR index, links).

### ◻ T-IE02 [S] Bootstrap IAM for mail (operator applies) → T-IE01
- **Deliverables**:
  - `terraform/bootstrap/ci/main.tf`: `ci_prod` policy adds the TEM full-access permission set on the prod project.
  - `terraform/bootstrap/ci/app_iam.tf`: a new identity `budget-planner-prod-mail` (application, policy with only the TEM send permission set on the prod project, API key) and a sensitive output for its secret key.
  - Exact permission-set names checked with `scw iam permission-set list` and written into ADR-0151 section 5.
  - Operator steps doc: apply the bootstrap stack, then add `MAIL_SCW_SECRET_KEY` to the GitHub `prod` environment.
- **Acceptance**: `terraform validate` and the bootstrap `tftest` pass; the mail identity has no permission outside TEM send.
- **Validation**: operator `terraform plan` in `terraform/bootstrap/ci` shows only the added policy rule and the new identity.

### ◻ T-IE03 [S] TEM domain, DNS records and secret plumbing → T-IE02
- **Deliverables**:
  - `terraform/modules/mail/`: `scaleway_tem_domain` (`rising-dough.eu`, `fr-par`, `accept_tos = true`), `scaleway_tem_domain_validation`, and `scaleway_domain_record` TXT records for SPF, DKIM and DMARC (`p=none`), plus MX if the resource exports one. Values come from the domain's exported attributes. Called from `terraform/main.tf` with `count = var.env == "prod" && var.managed_dns_zone ? 1 : 0`.
  - `terraform/variables.tf`: sensitive `mail_secret_key` (default `""`) and `mail_from` (default `Rising Dough <invite@rising-dough.eu>`).
  - Compose template: `BUDGET_MAIL_TEM_SECRET_KEY`, `BUDGET_MAIL_TEM_PROJECT_ID`, `BUDGET_MAIL_FROM`, `BUDGET_INVITE_EMAIL_ENABLED=true` rendered only when `mail_secret_key != ""`.
  - `scripts/ci/tf_env.py`: `Entry("mail_secret_key", "secret", "MAIL_SCW_SECRET_KEY", default="", only_env="prod")`.
  - `tests/architecture/ci_environments.toml`: `MAIL_SCW_SECRET_KEY` in the prod secrets.
- **Acceptance**:
  - The render tests (`terraform/tests/render.tftest.hcl`) assert that an empty key renders no mail env and a set key renders all four variables.
  - A drill plan creates no TEM or DNS resource.
  - `test_workflow_secrets.py` is green.
- **Validation**: `terraform test`; `just guards`; the drill gate on the PR.

### ◻ T-IE04 [P] Scaleway TEM adapter, settings and wiring → T-IE01
- **Deliverables**:
  - `adapters/mail/scaleway_tem.py` `ScalewayTemMailSender` (frozen dataclass, injected httpx client): `POST /transactional-email/v1alpha1/regions/{region}/emails` with `from`, `to`, `reply_to`, `subject`, `text`, `project_id`; timeout 10 s; transport error or non-2xx → `MailSendError`; logs the message id and status only.
  - `MailMessage` gains optional `reply_to` (the inviting admin's email) and `html`, both set by `services/invites.py`; the adapter sends the plain-text and HTML parts.
  - Invite email content (ADR-0151 section 9): subject `<Inviter name> invited you to Rising Dough`; body names the inviter, one sentence on the app, the link `https://budget.rising-dough.eu/invite/<token>` written out, the 7-day expiry, "ignore this email if you did not expect it". No images, no shortener, no tracking; same text in both parts. HTML part built with autoescaping (no user text unescaped).
  - `config.py`: `mail_tem_secret_key` (`SecretStr`), `mail_tem_project_id`, `mail_tem_region` (default `fr-par`), `mail_from`. Startup validation fails when the switch is on and any of them is missing.
  - The adapter is picked in the app factory (TEM when the switch is on, `NoopMailSender` otherwise).
  - The "Outbound mail" row in CLAUDE.md and `canonical_modules.toml` names the adapter.
  - `docs/plans/v3/runbooks/data-inventory.md` lists Scaleway TEM (recipient, subject, body with link; TEM log retention).
- **Acceptance**:
  - The adapter tests use a mock transport and assert the exact URL, headers and JSON body. They also assert that 4xx, 5xx and a timeout each raise `MailSendError`, and that the key, recipient and body never appear in captured logs.
  - The config tests assert startup refusal for each missing field.
  - The service test asserts `reply_to` is the actor's email, the exact subject and both bodies, and that the only URL in either part is the invite link on the app host.
- **Validation**: `just test-changed main`; `just guards`.

### ◻ T-IE05 [P] Per-admin invite-email limit → T-IE01
- **Deliverables**:
  - Invite-email rules in `services/rate_limit.py` callers: 10 per hour and 30 per day per admin. Create and resend both count.
  - Over the limit, the invite is created or renewed, the email is skipped, and the admin sees a message telling them to copy the link.
  - The "invite sent" message tells the admin to ask the invitee to check spam and mark the first email "not spam" (ADR-0151 section 9).
- **Acceptance**:
  - Tests assert the 11th send in an hour is skipped while the invite row is written with its token and expiry.
  - A second admin's sends are not counted against the first.
  - HTTP tests assert the body shows the copy-link message.
- **Validation**: `just test-changed main`; frontend-visual-audit only if the message changes a template.

### ◻ T-IE06 [S] Release and enable (operator) → T-IE03, T-IE04, T-IE05
- **Deliverables**:
  - Release through the pipeline (ADR-0099).
  - The operator checks the TEM domain status (verified, SPF, DKIM, DMARC OK) in the console.
  - First release with the key still empty (switch off) and green; then the operator adds the key and releases again.
  - Deliverability check (ADR-0151 section 9): one invite to a mail-tester.com address (score ≥ 9/10; fix and resend until it passes), then one each to Gmail, Outlook.com, WP.pl, Onet.pl and Interia.pl test mailboxes. Each lands in the inbox, not spam, and shows `spf=pass`, `dkim=pass`, `dmarc=pass` in `Authentication-Results`. Results table committed to `docs/runs/<date>-invite-email-deliverability.md`.
  - If a provider puts it in spam: record it, adjust content (T-IE04) or wait for reputation, and keep copy link as the fallback; no move to the Scale plan without a new ADR.
  - Result noted in `docs/CHANGELOG.md`.
- **Acceptance**: mail-tester ≥ 9/10; inbox at all five providers with SPF, DKIM and DMARC pass; the accept link from one of them works end to end.
- **Rollback**: empty `MAIL_SCW_SECRET_KEY` and release (plan, Rollback).

### ◻ T-IE07 [S] Tighten DMARC → T-IE06 (+30 days)
- **Deliverables**:
  - Choose the DMARC report destination (a mailbox on the domain, which needs an MX and mail host decision, or a free DMARC report service) and add `rua=` to the record.
  - After 30 days with no SPF or DKIM failures in the reports and no complaints in the TEM dashboard, DMARC goes to `p=quarantine` in `modules/mail`.
- **Acceptance**: `dig TXT _dmarc.rising-dough.eu` shows `p=quarantine`; one more invite delivered.
