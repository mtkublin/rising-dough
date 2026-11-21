# ADR-0061: v3 Multi-User — Admin Bootstrap, User Admin Panel, Per-User Data Isolation

- **Status**: Accepted (2026-11-21; implemented, was Proposed)
- **Date**: 2026-10-30
- **Supersedes**: ADR-0005 (single user, no auth, `user_id` scaffolded). The scaffold is now live; the single-user assumption is dropped.
- **Amends**: ADR-0033 (auth is per-user, not single-user; "fallback password" becomes the per-user password credential). ADR-0022 (repository discipline now requires `user_id` filtering on every query against user-owned tables). ADR-0019 (audit log records the acting `user_id` for every mutation).
- **Related**: ADR-0032 (v3 deployment), ADR-0035 (Terraform generates the admin bootstrap password), ADR-0025 (preferences are per-user), ADR-0026 (FAB visibility is per-user).

## Context

v3 was originally scoped as a single-user remote deployment (ADR-0033). The operator now wants to host for a small group (self + a handful of trusted users, order of magnitude 10) on the same Scaleway Stardust1-S host. Non-goals from v3 §6.8 remain: no autoscaling, no HA, no multi-region, no public sign-up, no external IdP.

The existing schema (ADR-0005) already scaffolds `user_id` on every user-owned table (`accounts`, `categories`, `transactions`, `planned_transactions`, `recurring_rules`, `budget_defaults`, `budget_recurring_overrides`, `budget_one_off_overrides`, `user_preferences`). Repository queries currently ignore the column because there has only ever been one row (`user_id = 1`, name `default`). The physical schema does not need to change for ownership; only the application-side filtering discipline and the identity model do.

Hardware headroom (see v3 README): Stardust1-S supports ~10 concurrent active users comfortably. Postgres migration deferred.

Constraints:

- Exactly one **admin** at any time, bootstrapped by Terraform at first boot. The admin manages the user list but **does not** see other users' data.
- No self-signup. User creation is admin-only.
- Every user authenticates with their own credentials (password + optional passkeys).
- Deleting a user is soft-delete; their data becomes inaccessible to all other principals.
- No forgotten-password email flow. Password recovery = admin triggers a reset.

## Decision

### 1. Role model

Two roles, encoded as a boolean on the `users` row:

- `is_admin = 1` — can enter the admin panel, create/edit/soft-delete users, trigger password resets.
- `is_admin = 0` — regular user. Full access to **own** data only.

Invariants (enforced in the service layer, not merely by convention):

- At least one `is_admin = 1 AND deleted_at IS NULL` user must exist at all times. The service rejects deleting or demoting the last admin.
- The bootstrapped admin is a regular user record; nothing in the schema distinguishes it structurally. Any admin can promote another user to admin (same `is_admin` toggle).
- The admin cannot read non-admin users' transactions, accounts, categories, preferences, snapshots, or budgets. Data isolation applies to the admin too.

Audit log records the acting `user_id` for every mutation (per ADR-0019 + the T-D14 request-context extension).

### 2. Schema change — migration `0012_multi_user.sql`

Extends the existing `users` row:

```sql
ALTER TABLE users ADD COLUMN email TEXT;
ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1));
ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0 CHECK (must_change_password IN (0, 1));
ALTER TABLE users ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
ALTER TABLE users ADD COLUMN deleted_at TIMESTAMP;

-- email is case-insensitive and unique across live rows.
CREATE UNIQUE INDEX ux_users_email_live
    ON users (lower(email))
    WHERE deleted_at IS NULL;

-- Drop the "DEFAULT 1" sentinel on every user-owned table (data-preserving).
-- SQLite requires full table rebuild for DEFAULT drop; migration performs
-- CREATE TABLE _new → INSERT SELECT → DROP → ALTER RENAME per table.
```

The `user_id DEFAULT 1` sentinel on `accounts`, `categories`, `transactions`, `planned_transactions`, `recurring_rules`, `budget_defaults`, `budget_recurring_overrides`, `budget_one_off_overrides`, `user_preferences` is removed. New rows must declare `user_id` explicitly.

**Legacy data**: the pre-existing `user_id = 1 (name='default')` row is renamed to the bootstrapped admin email during the migration if `BUDGET_PLANNER_ADMIN_EMAIL` is set at migration time; otherwise it stays as `default` and the admin bootstrap on first boot promotes it. All existing rows keep `user_id = 1` and become the admin's own historical data. This is deliberate — the operator migrating from v2 does not lose their data.

`account_snapshots` and `recurring_rule_overrides` remain scoped via their parent FK (`account_id` → `accounts.user_id`, `rule_id` → `recurring_rules.user_id`). Queries join through to filter. No schema change there.

`fx_rates` stays global (shared data).

### 3. Admin bootstrap

Terraform generates the admin credential at `apply` time:

```hcl
resource "random_password" "admin_initial_password" {
    length  = 20
    special = true
}
```

Cloud-init renders the compose env with:

```
BUDGET_PLANNER_ADMIN_EMAIL=<operator-provided email, var "admin_email">
BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD=<random_password.admin_initial_password.result>
```

On first boot the app runs an idempotent bootstrap routine (service layer, inside the lifespan startup hook):

1. If any `is_admin = 1 AND deleted_at IS NULL` user exists → no-op.
2. Else, look up (or create) a user with the given email, set `is_admin = 1`, `password_hash = bcrypt(initial_password)`, `must_change_password = 1`.
3. Append an `audit_log` entry (`entity_type='users', operation='create', actor='system-bootstrap'`).

Terraform exposes `admin_initial_password` as a sensitive output. Operator captures it once (`terraform output -raw admin_initial_password`) into a password manager. The env var is only read at bootstrap; it is **not** reconciled continuously — rotating the Terraform variable does not change an existing admin's password.

The ADR-0033 "fallback password" concept is retired. There is no separate `auth_password` row keyed to a fictional single user — passwords are per-user attributes on `users.password_hash`.

### 4. Routes and surfaces

New routes (all under `AuthRequiredMiddleware`; admin routes additionally under an `AdminRequiredMiddleware` that returns 404 to non-admins to avoid admin surface fingerprinting):

| Method | Path | Access | Purpose |
|---|---|---|---|
| GET | `/settings/users` | admin | List live users; "Add user" button; per-row Edit / Reset password / Remove |
| POST | `/settings/users` | admin | Create user with auto-generated password; response renders new password **once** via HTMX swap into a dismiss-only toast |
| GET | `/settings/users/{id}/edit` | admin | Edit form (email, is_admin toggle, name) |
| POST | `/settings/users/{id}` | admin | Save edits |
| POST | `/settings/users/{id}/reset-password` | admin | Auto-generate new password, set `must_change_password = 1`, show once |
| POST | `/settings/users/{id}/delete` | admin | Soft-delete (deleted_at = now()); revokes all their sessions in the same transaction |
| GET | `/settings/password` | all | Form: current + new + confirm |
| POST | `/settings/password` | all | Verify current, hash new, clear `must_change_password`, revoke all other sessions of the same user |

Login flow (`/auth/login`): email + password. The old `/auth/fallback-login` route is removed. `/auth/register` becomes a passkey-registration route for the currently-logged-in user; the per-user `must_change_password` flag forces redirection to `/settings/password` before any other route is served.

The admin panel link appears in the Settings page sidebar only when `request.state.user.is_admin == 1`.

### 5. Repository + service discipline

Amendment to ADR-0022:

- Every repository function against a user-owned table takes `user_id: int` as its first positional argument after `conn`.
- Every SQL in such a repository has `WHERE user_id = :user_id` on the primary table (or joins through the FK to assert it for `account_snapshots` / `recurring_rule_overrides`).
- The service layer passes `request.state.user.id` explicitly. There is no "current user" implicit global.
- A static-analysis test (`tests/architecture/test_user_id_filter.py`) parses each repository module's SQL with `sqlglot` and fails CI if a SELECT/UPDATE/DELETE against a user-owned table lacks a `user_id` predicate (or an equivalent join predicate for the two FK-scoped tables).

Mutations call `write_audit(..., user_id=<acting_user_id>, ...)` where `acting_user_id` is the session user. Admin mutations against user rows (create/delete/reset) record the target user id in `entity_id` and the admin id in a new `actor_user_id` column added to `audit_log` by migration `0007_audit_request_ctx.sql` (T-D14).

### 6. System categories per user

The system seed (migration `0003_seed_system_rows.sql`) currently inserts `Transit` + `Reconciliation` for `user_id = 1`. From now on:

- The seed migration remains (idempotent, keeps the admin's own `user_id = 1` data working).
- `services/users.create_user` seeds the same two system categories for every newly created user, inside the same transaction as the user row, with `is_system = 1`.
- Soft-deleting a user does **not** cascade to their categories — categories remain in the DB but are unreachable by any `user_id` filter because the user row is `deleted_at IS NOT NULL`.

### 7. Session + passkey ownership

ADR-0033 §3 (sessions) and §1 (passkeys) are already keyed by `user_id`. No schema change beyond the one in §2. The only behavioral change: `/auth/register` is now a per-user action available after the user logs in with their password. There is no global "fallback" session that bypasses the user model.

Deleting a user triggers an in-transaction `UPDATE sessions SET revoked_at = now() WHERE user_id = :id AND revoked_at IS NULL`.

### 8. Password auto-generation shape

`secrets.token_urlsafe(16)` → 22-character URL-safe base64 (~128 bits of entropy). Rendered once in a `<pre class="selectable">` block with a copy-to-clipboard button. The server does **not** persist the plaintext anywhere; only the bcrypt hash. If the admin dismisses the toast without copying, they must trigger another reset.

### 9. Non-goals (still)

- No self-signup. No invite emails. No OAuth. No per-user API tokens.
- No per-user quotas, no multi-tenant pricing, no org/team concept.
- No "forgot password" email flow. Admin reset is the only recovery path.
- No row-level encryption at rest. Isolation is enforced in the application, not by the storage layer.
- Admin cannot impersonate another user. There is no "login as" path.

## Consequences

### Positive

- Schema cost is one migration (`0012`) plus a column add on `audit_log`. The existing `user_id` scaffold pays off exactly as ADR-0005 predicted.
- Admin surface is small and explicit — six routes + one middleware. Admin cannot accidentally see user data because the discipline runs in the repository layer.
- Bootstrap is Terraform-native and matches the existing secret-flow pattern (sensitive output, operator captures once).
- Each user's auth is per-user; no shared fallback credential. Deleting a user instantly cuts off their sessions.
- The static-analysis test prevents the biggest regression risk (a repository query shipping without `user_id` filter).

### Negative

- Every existing repository function changes signature (adds `user_id`). Mechanical but touches ~15 modules. Phase 1 absorbs this via T-D16.
- The ADR-0033 fallback-password story is gone; the runbook changes (admin-initial-password instead). Documentation churn across runbooks + T-D27.
- The admin cannot see user data for support. If a user needs help with a bad transaction they must share a screenshot, not grant access.
- SQLite single-writer contention becomes a soft concern at ~10 concurrent writers. Not binding at expected scale; flagged for future ADR if it bites.
- Soft-deleted users' data remains in the DB bytes (reachable via raw SQL only). Operator-level privacy consideration; documented in `docs/plans/v3/runbooks/user-admin.md`.

### Follow-ups

- Add a `/settings/account/export` route per user (JSON dump of own data) once the export plumbing from ADR-0020 lands.
- Add a hard-delete admin flow (removes all rows owned by a user) after the first production privacy request. Not v3 scope.
- Reconsider argon2id vs. bcrypt in a later ADR when `argon2-cffi` becomes a cost-free swap.

## Alternatives Considered

- **Keep single-user and run one instance per user**: multiplies infra cost 10×, blocks shared categories/currencies if ever desired, and makes the admin "the one who SSHes to each VM". Rejected.
- **Row-level security via SQLite views**: SQLite has no native RLS; views would be bypassed by any raw query. Repository-layer filter + static test is simpler and more auditable.
- **External IdP (GitHub/Google OIDC)**: adds a third-party dependency and a per-login external hop for a <= 10 user private app. Rejected per original ADR-0033 rationale, unchanged.
- **Soft-admin / super-admin split**: one admin only, no multi-admin. Rejected because operator wants resilience against losing admin access (promote-a-second-admin should be possible).
- **Admin sees all data**: rejected — the operator explicitly asked for strict isolation.
- **Hard-delete on remove**: rejected for v3; destructive, non-reversible, and conflicts with ADR-0019's soft-delete-everywhere stance. Hard delete lives behind a later admin route.
