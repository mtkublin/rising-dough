# ADR-0069: Admin Bootstrap — Per-Environment Policy, Legacy-Row Adoption, Operator Password CLI

- **Status**: Accepted
- **Date**: 2026-11-03
- **Amends**: [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) §3 (admin bootstrap)
- **Related**: T-D19 (admin bootstrap), T-D02a/T-D02b (auth), T-D17 (admin panel), T-D18 (password change), ADR-0067

## Context

ADR-0061 §3 specifies an idempotent admin bootstrap at startup driven by `BUDGET_PLANNER_ADMIN_EMAIL` and `BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD`. Implementing it exposes questions §3 does not answer:

1. **Legacy row.** Migration `0012_multi_user.sql` carries the pre-v3 `users` row (`id = 1`, `name = 'default'`) forward with `email = NULL`, `password_hash = NULL`, `is_admin = 0`. All existing data is owned by that row. ADR-0061 §2 says the bootstrap "promotes it", but §3 only describes "look up (or create) a user with the given email". Looking up by email never matches a row whose email is `NULL`, so a literal reading creates a second user and leaves the operator's data owned by a user nobody can log in as.
2. **Dev default.** T-D19 asks for a known dev admin (`admin@local.test` / `admin`) when `BUDGET_ENV=dev`. `just dev` without `--db` points at `data/budget.sqlite`, which is the operator's real data. Writing a weak dev credential onto the real data owner at startup, or inserting a throwaway admin next to it (which would then make every later bootstrap a no-op), is not acceptable.
3. **Test env.** Hundreds of tests boot the app through `TestClient`. Several use the default `database_url` without migrating anything. A bootstrap that opens the DB on every startup would touch files the test did not intend to touch, and a fail-fast would break the suite.
4. **Recovery for the existing user.** The legacy row has no password. Once login lands (T-D02b) the operator needs a way to give it one, outside the app, without the in-app reset flow (T-D17), which requires an already-logged-in admin.

## Decision

### 1. Credential resolution per environment

`services.users.resolve_bootstrap_credentials(settings)` is a pure function:

| `BUDGET_ENV` | Both env vars set | Env vars missing |
|---|---|---|
| `production` | env credentials, `must_change_password = 1` | none → fail fast if no live admin |
| `dev` | env credentials, `must_change_password = 1` | dev default `admin@local.test` / `admin`, `must_change_password = 0` |
| `test` | env credentials, `must_change_password = 1` | none → no-op, **DB not opened** |

If exactly one of the two env vars is set, that is a configuration error: when no live admin exists, startup fails fast in every environment.

Fail-fast (`BootstrapAdminMissingEnv` → `SystemExit(1)` from the lifespan) only fires when no live admin exists **and** no credentials resolve. In practice that is production only.

### 2. Target selection when no live admin exists

In order:

1. A live user whose email matches (case-insensitive) → **promote**: `is_admin = 1`, `password_hash = bcrypt(password)`, `must_change_password` per §1.
2. Otherwise the lowest-id live, non-admin user with `email IS NULL` (the pre-v3 legacy row) → **promote** and set its email. Logged with `legacy_adopted = true`. This is how the operator's v2 data becomes the admin's own data, per ADR-0061 §2.
3. Otherwise **create** a new user plus its `Transit` and `Reconciliation` system categories in the same transaction (ADR-0061 §6).

### 3. Dev-default safety guard

Dev-default credentials never adopt a legacy row that owns data. If step 2 would pick a legacy row with at least one account, the bootstrap logs `action = "noop", reason = "legacy_data_present"` at warning level and leaves the DB untouched. Startup continues. `just dev` against `data/budget.sqlite` therefore writes nothing. On a scratch DB (legacy row owns no accounts) the dev default adopts the row so `just seed` data belongs to the dev admin.

Explicit env vars are operator intent and do adopt the legacy row even if it owns data.

The bootstrap never overwrites the password of an existing admin. It never runs when any live admin exists.

### 4. Operator CLI

`python -m budget_planner.cli.set_password --db=<path> (--email=<e> | --user-id=<n>) [--set-email=<e>] [--make-admin] [--must-change-password] [--password-stdin]`, wrapped as `just set-password` which refuses to run without `--db`. It prompts twice via `getpass` (or reads one line from stdin), hashes with bcrypt, updates the row, and writes an `audit_log` row (`entity_type = 'users'`, `operation = 'update'`, password redacted, `actor_user_id = NULL`). It refuses unmigrated DBs, unknown or soft-deleted users, and email collisions. This is the supported path for giving the legacy row of an existing local DB an email, a password and the admin flag.

### 5. Audit and logging

Bootstrap writes one `audit_log` row per mutated `users` row (plus one per seeded category on create), `actor_user_id = NULL`. `prev_json` / `new_json` carry `password_set: true|false`, never the hash or plaintext. The structured log line is `event = "admin_bootstrap"` with `action`, `admin_email`, `user_id`, `source` (`env` / `dev_default`) and, when relevant, `reason` / `legacy_adopted`. The password is never logged.

## Consequences

### Positive

- `just dev` against the real data cannot change it at startup.
- Fresh production DBs and migrated v2 DBs both end up with the existing data owned by the admin.
- Tests keep booting the app without credentials and without touching unintended DB files.
- The operator has a documented, audited, local-only way to set a password on any user.

### Negative

- `just dev-demo` (`data/demo.sqlite`, whose legacy row owns accounts) has no admin until the operator runs `just set-password --db=data/demo.sqlite …` or the demo builder learns to set one.
- The test env never fail-fasts. Lifespan tests exercise fail-fast with `BUDGET_ENV=production`.
- The dev default is a known weak password. It is bound to loopback (ADR-0005) and never applies in production.

## Alternatives considered

- **Literal ADR-0061 §3 (match by email or create).** Leaves the v2 data owned by an unreachable user. Rejected.
- **Dev default always creates `admin@local.test`.** Inserts a junk admin into the real DB and blocks the later real bootstrap. Rejected.
- **Fail fast in test env too, inject credentials in the root conftest.** Every app boot would pay a bcrypt hash and touch whatever DB the test configured. Rejected.
- **Auto-fix the legacy row at startup in dev.** Writes to the real DB without the operator asking. Rejected in favour of the CLI.
