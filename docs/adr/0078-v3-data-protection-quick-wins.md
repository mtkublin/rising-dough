# ADR-0078: v3 Data-Protection Quick Wins — Close Cross-User Leaks, Bound Copies, Encrypt Backups

- **Status**: Proposed
- **Date**: 2026-11-04
- **Amends**: [ADR-0034](0034-v3-sqlite-replication-litestream.md) §3 (replica encryption, retention ceiling), [ADR-0071](0071-production-startup-migrations.md) (pre-migration backup pruning by age). Extends T-D06 structured logging with a redaction processor (§5).
- **Related**: [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) (admin must not see user data), [ADR-0076](0076-session-hardening-absolute-cap-step-up-hashed-ids.md) (session hardening), [ADR-0079](0079-v4-threat-model-and-data-protection-goals.md) (v4 threat model; this ADR is its v3 down-payment)
- **Tasks**: T-D54..T-D61 (`docs/plans/v3/phase-5-data-protection/`)

## Context

The operator wants user data protected even from the admin, with the full design deferred to v4 (ADR-0079..ADR-0083). Before that, a review of the v3 code on 2026-11-04 turned up a set of cheap, low-risk changes. They need no key management and no schema redesign, and each one either closes a real leak or shrinks the places user data can sit unprotected.

Findings that drive this ADR:

1. **Cross-user leak in `/debug/audit-tail` (T-D43).** The route is admin-only and returns the newest audit rows of **all** users, including `prev_json` / `new_json`. Those payloads carry amounts, descriptions, account and category names. That breaks ADR-0061 ("the admin cannot read non-admin users' transactions …"). `_scrub` only redacts secret-looking keys.
2. **Authenticated HTML is cacheable.** Only `/debug/audit-tail` and `/settings/users` send `Cache-Control: no-store`. After logout, the browser back button or the disk cache on a shared machine can still show financial pages.
3. **Backups are plaintext at the application layer.** The Litestream replica in Scaleway Object Storage relies on provider-side SSE only. Anyone holding a bucket credential (or the leaked operator API key) can restore the full DB. Prod pins `litestream/litestream:0.3`. Prod-sim runs `0.5.0` / `0.5.17`, which is an unintended version skew.
4. **No upper bound on copy lifetime.** Litestream `retention: 720h` (30 d), plus bucket `noncurrent_version_expiration` of 30 d, gives a worst case of about 60 d. Pre-migration `VACUUM INTO` backups keep "the newest 3" with no age limit. Drill hosts keep a moved-aside DB. Any future erasure promise (v4 right to be forgotten) needs a known maximum.
5. **Freed pages keep old content.** Without `PRAGMA secure_delete`, deleted and overwritten rows (sessions, rate-limit rows, edited descriptions, future purges) stay readable in free pages of the DB file until reused.
6. **Logs may carry user values.** Structlog has no redaction processor. Caddy's JSON access log records full request URIs, including query strings such as ledger search terms (`?q=`) and filter values.
7. **IP address and user agent are kept forever** in `audit_log` and `sessions` (T-D14). They are personal data with no retention limit.
8. **No written inventory** of where user data lives, or of what the operator can technically see. Users can't be told honestly, and v4 has no baseline to design against.

## Decision

All items are v3 scope, grouped as **Phase 5 — Data-protection quick wins** in `docs/plans/v3/tasks.md`. None of them changes user-visible behaviour except §2 (back-button after logout shows a fresh login instead of cached data).

### 1. Audit tail is owner-scoped (T-D54)

- `/debug/audit-tail` stays admin-only. Each entry carries the existing metadata (`id`, `entity_type`, `entity_id`, `changed_at`, `operation`) plus `user_id`.
- `prev` / `new` payloads are returned **only for rows whose owning user is the caller**. Owner means the row's `user_id`, or for auth/admin events the `actor_user_id`. For every other row both fields are the literal string `"[other-user]"`.
- The T-D43 smoke journey asserts the second user's transaction row **exists** (metadata), not its payload. That's enough to prove the audit write happened, and it now also proves isolation.

### 2. Authenticated responses are `no-store`; logout clears site data (T-D55)

- A middleware sets `Cache-Control: no-store` on every response served to an authenticated session, HTML, HTMX partials and JSON alike. `/static/**`, `/health` and `/ready` are untouched.
- `POST /auth/logout` (and the session-revoke-self path) adds `Clear-Site-Data: "cache", "storage"`. `"cookies"` is deliberately omitted: logout already expires the session cookie, and wiping every cookie would also drop the CSRF cookie mid-flow.
- **Addendum to ADR-0070 §6 (middleware order).** `CacheControlMiddleware` (pure ASGI) slots between `AuthRequired` and `MustChangePassword`. Outermost first: RequestId → SecurityHeaders → AuthRequired → **CacheControl** → MustChangePassword → AdminRequired → CSRF → routers. It must sit inside `AuthRequired` so `request.state.user` is populated, and outside the later guards so their redirects and 404s for authenticated users are also `no-store`.

### 3. Litestream replicas are encrypted with age (T-D56)

- Replica config gains `age.recipients` (public key). The `litestream-restore` service, `restore-from-prod` (drill) and the restore runbook get `age.identities` (private key).
- **Version alignment first.** Prod-sim and prod pin the **same** Litestream image tag. The tag is chosen by verifying age support in the release notes. Litestream 0.3.x supports age replica encryption. Whether 0.5.x does must be verified and recorded in the task handoff, and if it doesn't, both stacks pin the latest 0.3.x.
- The identity is generated by the operator (`age-keygen`) and stored in the operator password manager. It reaches the host through the existing secret path (Terraform sensitive variable → cloud-init file at `0600`, ADR-0035/0069). It ends up in Terraform state, which is accepted because the state bucket is private, versioned and operator-only. The protection gained is against **bucket-only** exposure: a leaked replica credential, a bucket policy mistake, or a provider-side incident.
- Cut-over: start a new Litestream generation with encryption on, run a restore drill against it (T-D40/T-D41 procedure), then delete the unencrypted generations. Bucket versioning keeps noncurrent copies until §4's lifecycle expires them.
- **Addendum (2026-11-06, T-D56 verification).** Age replica encryption does **not** exist in Litestream 0.5.x: it was removed in the LTX storage-layer refactor. v0.5.0 silently ignored an `age:` block; since v0.5.1 ("Reject age encryption configuration until support is restored", PR #791) the daemon refuses to start with `age encryption is not currently supported`; v0.5.3 removed the unused age dependency (PR #870). Evidence: <https://litestream.io/reference/config/> ("Age client-side encryption is unsupported in v0.5.x") and the v0.5.1 / v0.5.3 release notes on GitHub; latest 0.5.x at the time was v0.5.18 (2026-11-03). Client-side encryption in 0.3.x arrived in v0.3.10 (PR #468). **Decision: prod, prod-sim and the drill restore helper all pin `litestream/litestream:0.3.14`** (latest 0.3.x, 2026-03-26, a restore-panic fix). Revisit when 0.5.x re-implements encryption (expected inside LTX); that will need a new ADR because replica formats differ.
- Mechanics: 0.3.x takes age keys inline, not as file paths, and expands `${VAR}` in the config. The replicate config carries only `age.recipients`. A separate restore-only config carries `age.identities: [${LITESTREAM_AGE_IDENTITY}]`; the restore service and `restore-from-prod` export that variable from the `0600` key file (`/etc/budget-planner/litestream-age.key`). Terraform inputs: sensitive `litestream_age_identity` and public `litestream_age_recipient` (Terraform cannot derive the recipient; validated by format). The drill host receives the **prod** identity because it restores the prod replica. Prod-sim uses a committed dev-only identity (`deploy/litestream-age-DEV-ONLY.key`), excluded from `detect-secrets` via `.secrets.baseline` and never used for drill or prod.

### 4. Maximum copy age: 37 days (T-D57)

One documented ceiling, **`backup_max_age_days = 37`**, for every copy of user data outside the live DB:

| Copy | v3 today | After T-D57 |
|---|---|---|
| Litestream generations (prod) | `retention: 720h` | unchanged (30 d) |
| Bucket noncurrent versions | 30 d | **7 d** (`lifecycle_days = 7`) → worst case 30 + 7 = 37 d |
| Pre-migration `VACUUM INTO` backups | newest 3, unbounded age | newest 3 **and** younger than 30 d (prune both rules on every startup) |
| Drill host moved-aside / restored DBs | kept until next drill | deleted at the end of each drill run; drill env is torn down per T-D26 |
| Operator ad-hoc copies | undocumented | forbidden outside `runbooks/` procedures; any copy follows the same 30 d rule |

`docs/requirements.md` §6.5 records the ceiling. v4's right-to-be-forgotten promise (ADR-0083) is stated against it.

### 5. Log hygiene (T-D59)

- A structlog processor redacts values for a deny-list of keys: `amount*`, `description`, `name`, `note*`, `memo`, `formula`, `q`, `search`, `email`, `password*`, `token*`, `secret*`, `*_json`. It's applied in `_processors()` before rendering. Unit-tested.
- Caddy's access log uses the `filter` encoder to strip the query string from `request>uri` (a `regexp` field filter) for app routes. Path, status and timing are kept.
- Host logrotate for `/var/log/caddy/access.log` keeps at most 14 days.
- A regression test performs a ledger search with a sentinel term, then asserts the sentinel appears in no captured app log line.

### 6. `PRAGMA secure_delete = ON` (T-D58)

Set in `db/connection.py` next to the Litestream PRAGMAs (ADR-0034 §2). Deleted content is zeroed on disk. The write cost is negligible at our volume. The existing PRAGMA unit test is extended.

### 7. IP / user-agent retention: 90 days (T-D60)

- `audit_log.ip` and `audit_log.user_agent` are nulled for rows older than 90 days. The rows stay; only the personal-data columns are cleared.
- `sessions` rows that are revoked or expired for more than 90 days are deleted.
- The purge is idempotent. It runs at container start (entrypoint, after `startup_migrate`) and once every 24 h from the app lifespan task. It logs `event="retention_purge"` with counts only.

### 8. Data inventory and operator-visibility statement (T-D61)

New `docs/plans/v3/runbooks/data-inventory.md`. It lists every place user data or secrets live, with retention and protection: live DB and WAL, Litestream bucket, pre-migration backups, drill host, Caddy and app logs, Terraform state (secrets, no user data), cloud-init user-data, and the browser (after §2).

It ends with a plain-language **"what the operator can technically see in v3"** statement, which is honest: the operator with host access can read everything. That statement is the baseline v4 improves on. It's also the text to share with users.

## Consequences

- Closes the one confirmed ADR-0061 violation (§1) and the logged-out cache exposure (§2).
- Backup theft without host or identity access yields only ciphertext (§3).
- Every copy of user data has a known maximum age (§4). That's a prerequisite for v4 erasure.
- **Not achieved, by design:** the operator with root on the host, or with the DB file, can still read all user data. Closing that is v4 (ADR-0079..0083).
- The `lifecycle_days` reduction (30 → 7) shortens how long a deleted Litestream object stays recoverable at the provider. Restore drills remain the guarantee of recoverability, not noncurrent versions.
- The operator must store one more secret (age identity). Losing it makes the encrypted replica unrecoverable. The operator checklist gets an item for it.

## Alternatives considered

- **Bucket SSE-C (customer-provided keys) instead of age.** Rejected. Litestream does not pass SSE-C headers, and the provider still sees the key on every request.
- **SQLCipher full-DB encryption with a server key in v3.** Deferred to ADR-0079's analysis. It needs an image change (SQLCipher build), and Litestream compatibility is unverified. The protection it adds over §3 + host disk access controls is marginal while the key sits on the same host.
- **Dynamic data masking.** Not applicable. SQLite has none, and in engines that have it, privileged DB users bypass it. ADR-0061 authz isolation is already the app-level equivalent.
