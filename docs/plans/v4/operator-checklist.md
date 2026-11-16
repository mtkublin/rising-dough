# v4 — Operator (human-only) checklist

> Everything in v4 that an agent can't do. Never write secret values into this file.

## A. Before Phase 1

- [ ] Review ADR-0079..ADR-0083 and set them to Accepted (or request changes).
- [ ] Confirm the residual risks in ADR-0079 are acceptable to state publicly on `/privacy`.
- [ ] Confirm the **admin-reset semantics change** (ADR-0082 §5): a reset no longer restores data without the user's recovery code or PRF passkey.
- [ ] Confirm the retention schedule (ADR-0083 §7): deactivated users auto-erased after 90 d; backups ≤ 37 d; logs 14 d; IP/UA 90 d.

## B. Secrets (T-E02, T-E03)

- [ ] Run `python -m budget_planner.cli.secrets generate` locally and store `PEPPER` and `ESCROW_MASTER` in the password manager.
- [ ] Upload the secret versions to Scaleway Secret Manager (`... secrets upload`) for drill and prod separately. Never reuse drill values in prod.
- [ ] Record in `runbooks/disaster-recovery.md`: losing `ESCROW_MASTER` during the claim window loses unclaimed users' data; losing `PEPPER` forces password users onto passkey or recovery unlock.

## C. Canary (T-E23)

- [ ] Create the `canary@` user on prod with synthetic data only; store its credentials as a GitHub environment secret.

## D. Rollout (T-E24)

- [ ] Offline backup of prod (`VACUUM INTO` via the runbook) before approving the v4.0 deploy.
- [ ] Approve the prod deploy.
- [ ] Notify users. Suggested text:

  > *"Your data is now encrypted. Next time you sign in you'll be asked to finish protecting it and to save a recovery code. Keep that code safe: if you lose your password, your passkeys and the code, nobody — including me — can recover your data. Details: /privacy."*

- [ ] Weekly, until every active user is `claimed` (target 30 days): check claim status in `/settings/users` and nudge users who haven't claimed.

## E. Contract release (T-E25)

- [ ] Confirm zero `plaintext` users and approve the v4.1 deploy. Note it can't be rolled back without a restore.

## F. Ongoing

- [ ] Monthly: read the restore-drill result, including the decrypt canary.
- [ ] Handle erasure requests through the self-service path or `/settings/users` → Erase. Never by hand-editing the DB.
- [ ] Pepper rotation (optional, yearly): `secrets generate --pepper`, upload as a new version, keep the previous version 90 days.
