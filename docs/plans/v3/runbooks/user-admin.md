# Runbook — User Administration

Add / reset / remove / promote users. Enforce the last-admin invariant. Honor the data-isolation guarantee.

## Context

v3 is multi-user by admin provisioning only (ADR-0061). There is no self-signup, no email flow, and no external IdP. The admin creates users through `/settings/users`; each user gets a one-shot auto-generated password that is shown exactly once and then only the bcrypt hash is kept. All data is owned per-user and the admin **cannot** read non-admin data (ADR-0061 §1 "Admin cannot read non-admin users' transactions, accounts, categories, preferences, snapshots, or budgets. Data isolation applies to the admin too.").

Four invariants the admin surface enforces (service layer, not UX):

1. At least one `is_admin = 1 AND deleted_at IS NULL` user must exist. Deleting or demoting the last admin is rejected (`409 Conflict`).
2. Every user authenticates with their own credentials. There is no fallback user and no "login as" path.
3. Admin-triggered password reset generates a new password **once**. The server never persists plaintext.
4. Soft-deleting a user revokes all their live sessions in the same transaction and makes their data unreachable to every principal (including the admin) via the `user_id` filter.

Audit log entries written by admin actions carry `actor_user_id = <admin id>` and `entity_id = <target user id>` (ADR-0019 + T-D14 extension cited in ADR-0061 §5).

## Preconditions

- Operator is logged in as an admin at `https://<prod-host>/`.
- Admin's own password has already been rotated (never leave the Terraform-generated bootstrap password in use beyond the first login — ADR-0061 §3).
- 2FA / passkey is registered for the admin's own account (optional but strongly recommended).

## Procedure — Add a user

1. Admin opens `GET /settings/users`.
2. Click "Add user". Fill: `email` (case-insensitive unique), `name`, `is_admin` toggle (off by default).
3. `POST /settings/users`.
4. The response renders the one-shot auto-generated password (`secrets.token_urlsafe(16)`, ADR-0061 §8) via HTMX swap into a dismissible toast containing a `<pre class="selectable">` block + copy-to-clipboard button.
5. Send the password to the user through a channel the admin controls (password manager share, encrypted messenger — **not** email in plaintext).
6. On first login the user is forced to `/settings/password` because `must_change_password = 1`.

### Verification (add)

```sh
# Row exists, live, and has the expected is_admin flag.
ssh app@<prod-host> \
  "sqlite3 /data/budget.db \"SELECT id, email, is_admin, must_change_password, deleted_at FROM users WHERE lower(email) = lower('<new-email>');\""

# Audit entry present.
curl -fsS -b <admin-session-cookie-jar> "https://<prod-host>/debug/audit-tail?entity_type=users&limit=5" | jq .

# System categories were seeded for the new user (ADR-0061 §6).
ssh app@<prod-host> \
  "sqlite3 /data/budget.db \"SELECT count(*) FROM categories WHERE user_id = <new-user-id> AND is_system = 1;\""
# Expect: 2 (Transit + Reconciliation).
```

## Procedure — Reset a user's password

1. Admin opens `GET /settings/users`.
2. Click "Reset password" on the target row.
3. `POST /settings/users/{id}/reset-password`.
4. Server generates a new password, hashes it, sets `must_change_password = 1`, revokes all other sessions of the target user (same transaction), and renders the new password **once** in a dismissible toast.
5. Admin shares the new password with the user via a controlled channel; user rotates on first login.

### Verification (reset)

- User's existing sessions are revoked:
  ```sh
  ssh app@<prod-host> \
    "sqlite3 /data/budget.db \"SELECT count(*) FROM sessions WHERE user_id = <target-id> AND revoked_at IS NULL;\""
  # Expect: 0 immediately after reset. (The user's next login creates a fresh session.)
  ```
- Audit log carries the reset entry:
  ```sh
  curl -fsS -b <admin-cookie-jar> "https://<prod-host>/debug/audit-tail?entity_type=users&operation=reset_password&limit=5"
  ```

## Procedure — Remove a user (soft delete)

1. Admin opens `GET /settings/users`.
2. Click "Remove" on the target row. Confirm.
3. `POST /settings/users/{id}/delete`.
4. Server sets `deleted_at = now()`, revokes all live sessions of the target in the same transaction, and writes an audit entry.
5. The user's data (accounts, categories, transactions, planned, recurring, budgets, snapshots) remains in the DB bytes but is unreachable through any `user_id` filter because the user row is now `deleted_at IS NOT NULL` (ADR-0061 §5). Hard-delete is deliberately **not** in v3 (follow-up ADR territory).

### Verification (remove)

```sh
# User is soft-deleted and sessions are gone.
ssh app@<prod-host> \
  "sqlite3 /data/budget.db \"SELECT id, email, deleted_at FROM users WHERE id = <target-id>;\""
ssh app@<prod-host> \
  "sqlite3 /data/budget.db \"SELECT count(*) FROM sessions WHERE user_id = <target-id> AND revoked_at IS NULL;\""
# Expect: deleted_at IS NOT NULL, sessions count = 0.

# Target can no longer log in.
curl -fsS -o /dev/null -w '%{http_code}\n' \
  -c /tmp/jar -b /tmp/jar \
  -X POST "https://<prod-host>/auth/login" \
  --data-urlencode "email=<removed-email>" \
  --data-urlencode "password=<their-old-password>"
# Expect: 401.
```

Document the removal in the operator's own notes if a hard-delete request is anticipated (GDPR deletion request flow is a follow-up ADR, not v3).

## Procedure — Promote a user to admin

1. Admin opens `GET /settings/users`.
2. Click "Edit" on the target row.
3. Toggle `is_admin = 1`.
4. `POST /settings/users/{id}`.
5. Target user's next page load picks up the admin surface in the Settings sidebar.

### Verification (promote)

```sh
ssh app@<prod-host> \
  "sqlite3 /data/budget.db \"SELECT id, email, is_admin FROM users WHERE id = <target-id>;\""
# Expect: is_admin = 1.
```

Promote a second admin **before** going on vacation. The last-admin invariant means a single-admin deployment cannot be rescued from inside the app if that admin loses credentials — recovery then requires the DR runbook's §5 lost-all-admins sub-flow.

## Procedure — Demote an admin

Mirror of promote: toggle `is_admin = 0` on `/settings/users/{id}/edit` and `POST`. The service rejects demoting the only live admin.

### Last-admin invariant check

The invariant lives in `services/users.py` (per ADR-0061 §1) and is enforced server-side. Verify defensively:

```sh
# How many live admins currently exist?
ssh app@<prod-host> \
  "sqlite3 /data/budget.db \"SELECT count(*) FROM users WHERE is_admin = 1 AND deleted_at IS NULL;\""
# If this returns 1, do NOT demote or delete that user. Promote a second admin first.
```

A demotion attempt against the last admin returns `409 Conflict` with an error-flash explaining the invariant.

## Data-isolation note (ADR-0061)

The admin surface deliberately does **not** read other users' data. The repository layer requires `user_id` on every query against user-owned tables (`accounts`, `categories`, `transactions`, `planned_transactions`, `recurring_rules`, `budget_defaults`, `budget_recurring_overrides`, `budget_one_off_overrides`, `user_preferences`, plus FK-scoped `account_snapshots` and `recurring_rule_overrides`). A static-analysis test (`tests/architecture/test_user_id_filter.py`) parses each repository module's SQL with `sqlglot` and fails CI if a user-owned table is queried without a `user_id` predicate.

Consequences the operator must honor:

- Troubleshooting a user's data requires a screenshot or an operator-run `sqlite3` session against `/data/budget.db` — the UI will not render another user's rows for the admin.
- Any `sqlite3`-level read of another user's data must be justified (support request, forensic, DR verification) and recorded in the operator's own ops notes. Treat it as sensitive.
- Soft-deleted user data remains in the DB bytes (reachable only via raw SQL). The forthcoming hard-delete flow (ADR-TBD) is the correct answer for a GDPR deletion request; do not improvise by `UPDATE`-ing deleted_at + manually deleting rows.

## Troubleshooting

- **"Add user" form rejects an email that was previously removed**: the `ux_users_email_live` unique index covers live rows only (ADR-0061 §2). If the index is still complaining, the soft-deleted row has `deleted_at IS NULL` by accident — inspect and fix via `sqlite3` with a dated audit note.
- **New admin's first login succeeds but admin menu is missing**: browser cached the pre-promote session. User logs out + back in. Confirm the session carries the fresh `is_admin` claim (`SELECT ... FROM sessions WHERE user_id = <id> AND revoked_at IS NULL`).
- **Password toast dismissed before copying**: no recovery of plaintext — admin re-triggers reset-password. This is a feature, not a bug.
- **"last admin" error on demote even though two live admins appear in the UI**: refresh and re-check — a parallel admin tab may have soft-deleted or demoted the "other" admin a moment ago. Repeat the invariant query above.
- **Admin cannot delete themselves**: the invariant blocks deleting the last admin, but admin **can** delete themselves if another live admin exists. Confirm count ≥ 2 before attempting self-removal.
- **Soft-deleted user's rows still appear in a report**: a repository function somewhere is missing the `user_id` filter or the `deleted_at` filter on `users`. File a CRITICAL bug; the static-analysis test should have caught it in CI.

## Rollback

- **Accidental reset**: the previous password is irrecoverable (only the bcrypt hash was stored, and it has been overwritten). The user must take the newly generated password.
- **Accidental soft-delete**: restore the user by `UPDATE users SET deleted_at = NULL WHERE id = <target-id>;` executed by the operator via `sqlite3 /data/budget.db`. Audit the correction with a dated note. Sessions remain revoked — the user re-logs in. Prefer this over anything that touches other tables.
- **Accidental promote-to-admin**: edit → toggle `is_admin = 0` → save, subject to the last-admin invariant.
- **Need to roll back an entire user admin change set across many users**: do not script it. Walk through each user record in `sqlite3`, honour the last-admin invariant, and record every change in the operator's ops notes.
