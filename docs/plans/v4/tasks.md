# v4 — Data Protection Tasks

> Each task carries its full specification inline. If a task grows during pickup, split it into `phase-N-*/T-Exx-*.md` and keep the summary here.
> Legend: `[P]` parallel-safe within its phase, `[S]` sequential, `→ T-xx` depends on upstream task.
> Acceptance = ADR referenced + tests + validation hook passes + `✅` prefix added here. Templates, CSS or HTMX swaps changed → `frontend-visual-audit` at 1440 / 1024 / 375 before ✅ (CLAUDE.md).
> **Prod DB rule** (CLAUDE.md): every task works on scratch DBs or `data/demo.sqlite`. Only T-E24 and T-E25 touch prod, and only through the deploy pipeline with operator approval.

---

## Phase 0 — Preconditions

### ◻ T-E00 [S] Preconditions gate
- v3 Phase 5 complete (T-D54..T-D61, ADR-0078). In particular the age-encrypted replica, the 37-day ceiling, `secure_delete` and log redaction.
- T-D53 merged (ADR-0076: hashed session ids, step-up re-auth, id rotation). v4 builds on all three.
- T-D50's ADR renumbered off 0076 (now owned by T-D53).
- The operator reviews ADR-0079..0083 and flips them to Accepted.
- Post-v3 code-quality audit complete (`docs/plans/quality-audit/`, T-Q01..T-Q17 ✅, requirements §8).
- Before Phase 3 (not Phase 0) starts: every quality-audit remediation task tagged `[pre-v4-P3]` is ✅.

---

## Phase 1 — Crypto core and secrets (no behaviour change)

### ◻ T-E01 [P] `budget_planner.crypto` module → T-E00
- **Deliverables**:
  - `src/budget_planner/crypto/` as pure functions: `aead.py` (envelope encode/decode, `encrypt_field`, `decrypt_field`, AAD builder), `kdf.py` (Argon2id KEK, HKDF subkeys), `blind_index.py`, `padding.py` (32-byte buckets, length prefix), `errors.py` (`DecryptionError`, `KeyUnavailableError`), `types.py` (`UserKeys` frozen dataclass).
  - `pyproject.toml`: add `argon2-cffi`, and make `cryptography` a direct dependency within the ADR-0067 pin range. Regenerate `uv.lock`.
- **Acceptance**:
  - Hypothesis round-trip tests for int64 (incl. negatives), Unicode text, empty and maximum-length strings, JSON.
  - AAD tamper tests: different user, column or table → `DecryptionError`.
  - Envelope version and `dek_version` parsed.
  - Argon2 params read from the stored JSON.
  - 100% branch coverage of `crypto/`.
- **Validation**: `just test tests/unit/crypto/`
- References: ADR-0080 §1, §2, §5, §6; ADR-0081 §4.

### ◻ T-E02 [P] Server secrets: settings, loader, CLI → T-E00
- **Deliverables**:
  - Settings `pepper` and `escrow_master` (32 bytes, base64), with a loader from a Secret Manager path or from file paths `BUDGET_PEPPER_FILE` / `BUDGET_ESCROW_MASTER_FILE`.
  - Production fails startup when either is missing (same mechanism as `cookie_secret`, T-D03).
  - Dev and test get deterministic per-env values.
  - `pepper_version` support (current + previous).
  - CLI `python -m budget_planner.cli.secrets generate|upload`.
  - `.env.example` updated.
- **Acceptance**: unit tests for missing, short or malformed secrets; dev defaults never accepted when `env=production`; the CLI never prints secrets to stdout unless `--reveal`.
- **Validation**: `just test tests/unit/test_config_secrets.py`
- References: ADR-0080 §3.

### ◻ T-E03 [S] Infra: Secret Manager, IAM, host hygiene → T-E02
- **Deliverables**:
  - Verify Scaleway Secret Manager in `pl-waw` and record the result in the handoff.
  - Terraform creates the secret containers (no versions) and a read-only IAM application and policy scoped to them.
  - cloud-init fetches the secrets at boot into tmpfs `/run/budget-planner/secrets/` at `0400`, owned by uid 10001. Fallback, if Secret Manager is unavailable: sensitive variables written by cloud-init at `0600`, trade-off recorded.
  - Assert no swap (or encrypted swap).
  - Container `ulimit -c 0`.
  - Runbooks: `deploy.md`, `disaster-recovery.md` (secrets restore order: secrets before app start), and operator checklist.
- **Acceptance**: `terraform plan` on drill is clean apart from the new resources; the drill host boots, the app reads the secrets, and `/ready` is 200; `terraform show` contains no secret values.
- **Validation**: drill apply plus `ssh drill 'test ! -s /proc/swaps || swapon --show'` (the host check is recorded in the handoff).
- References: ADR-0080 §3, §8.

### ◻ T-E04 [P] Key-wrap schema (expand) → T-E00
- **Deliverables**:
  - Migration `00NN_v4_keys.sql` (+ down): table `user_key_wraps` (ADR-0080 §2 columns); `sessions.wrapped_umk BLOB NULL`; `users.key_state TEXT NOT NULL DEFAULT 'plaintext' CHECK (...)`; `users.erased_at TIMESTAMP NULL`; `users.data_migration_version INTEGER NOT NULL DEFAULT 0`. Expand-only (N-1 safe, ADR-0071).
  - `repositories/key_wraps.py`: insert, list by user, hard delete, delete all for user. Every write emits a metadata-only audit row. Add to the ADR-0068 allowlist with justification (hard delete).
  - Domain enum `KeyState` and transition validator (ADR-0082 §1).
- **Acceptance**: migration up/down on a scratch DB; invalid transitions rejected; audit rows carry no key bytes (test greps the payloads).
- **Validation**: `just migrate --db=/tmp/scratch.sqlite && just test tests/unit/repositories/test_key_wraps.py`
- References: ADR-0080 §2, ADR-0082 §1.

---

## Phase 2 — Session binding and unlock

### ◻ T-E05 [S] Keys from login; cookie-held session key; locked sessions → T-E01, T-E04, T-E00
- **Deliverables**:
  - `services/keys.py`, the unlock functions:
    - `unlock_with_password(conn, user, password, secrets)`
    - `unlock_with_prf(conn, user, credential_id, prf_output)`
    - `unlock_with_recovery(conn, user, code)`

    Each returns `UserKeys` or raises.
  - Login sets `sessions.wrapped_umk` and the cookie value `<session_id>.<swk>` (ADR-0070 §2 amended).
  - Middleware resolves the session, then unwraps the UMK and the DEK into `request.state.keys`. Dependency `current_keys`.
  - `LockedSessionMiddleware` behaviour for data routes: 303 / `HX-Redirect` / 403 JSON `unlock_required`.
  - `/auth/unlock` (password or recovery code).
  - Session-id rotation (ADR-0076) re-wraps the UMK; revoke deletes the wrap.
  - Rate-limit scope `unlock`.
  - Argon2 semaphore (max 2; 5 s wait → 503).
  - Pre-v4 users (`plaintext` / `escrowed`) keep working through escrow or no-key paths until T-E07 and T-E12.
- **Acceptance**:
  - Cookie tampering (wrong SWK) gives the locked/unauthenticated behaviour, not a 500.
  - The DB alone (no cookie) can't unwrap: unit test with a real DB file.
  - A revoked session's cookie unwraps nothing.
  - Middleware order documented (ADR-0070 §6 addendum).
  - Rate limit enforced.
  - Login p95 ≤ 700 ms on the perf container.
- **Validation**: `just test tests/unit/services/test_keys.py tests/integration/web/test_unlock.py`
- References: ADR-0080 §4, §9.

### ◻ T-E06 [S] Passkey PRF wraps → T-E05
- **Deliverables**:
  - `static/js/passkeys.js`: request the `prf` extension on `create()`. If it's absent or empty, follow with one `get()` using `prf.eval.first = "bp/prf/v1"`, then send the PRF output alongside the assertion. Login sends the PRF output when present.
  - Server creates and deletes `passkey_prf` wraps, verifying that the PRF output arrives with a successfully verified assertion.
  - Labels: "Signs in and unlocks data" / "Sign-in only".
  - "Unlock with passkey" on `/auth/unlock` and `/auth/recover`.
- **Acceptance**: Playwright virtual authenticator with `hasPrf: true` → passkey login gives an unlocked session; with `hasPrf: false` → locked session, then unlock with password; revoking the passkey deletes its wrap. **frontend-visual-audit** on `/settings/security` and `/auth/unlock`.
- **Validation**: `just test tests/e2e/test_passkey_prf.py`
- References: ADR-0082 §4.

### ◻ T-E07 [S] Claim flow and recovery code → T-E05
- **Deliverables**:
  - Middleware: `escrowed` users go to `/auth/protect` ("Protect your data") before any data route (HTMX and JSON variants as in ADR-0070 §4).
  - The claim service creates the password wrap, generates the recovery code (8×4 Crockford base32) and creates its wrap. It requires confirmation of the last group, offers a text download, deletes the escrow wrap, sets `claimed`, and audits `escrow_claimed`.
  - Forced rotation for `pending` users (ADR-0074) becomes the key-creation point (UMK + DEK_1 + wraps + recovery code).
  - Passkey-only `escrowed` users claim through PRF, or must set a password first.
- **Acceptance**:
  - After claim no `escrow` wrap exists.
  - The recovery code is shown exactly once (a reload shows "already shown").
  - Wrong confirmation is rejected.
  - Unlock with the recovery code works and forces a password set plus a new code.
  - frontend-visual-audit on `/auth/protect`.
- **Validation**: `just test tests/integration/web/test_claim.py tests/e2e/test_claim_journey.py`
- References: ADR-0082 §2–§4.

---

## Phase 3 — Field encryption

### ◻ T-E08 [S] Expand migration for encrypted columns → T-E04
- **Deliverables**:
  - Migration `00NN_v4_encrypted_columns.sql` (+ down): `<col>_ct BLOB` for every column in ADR-0081 §1; `name_bidx BLOB` on `accounts` and `categories`. Plaintext columns become nullable through the ADR-0061 table-rebuild pattern. `ux_*_user_name_live` is rebuilt on `(user_id, name_bidx)`, with a transitional partial index keeping the plaintext uniqueness for rows where `name_bidx IS NULL`.
  - `audit_log.payload_owner_user_id` (the user whose DEK encrypts the payloads), `prev_json_ct`, `new_json_ct`.
- **Acceptance**: migration up/down on a copy of `data/demo.sqlite` (never prod); the N-1 image still reads and writes (run the previous image's test suite against the migrated scratch DB).
- **Validation**: `just migrate --db=/tmp/scratch.sqlite`; N-1 compatibility script from ADR-0071.
- References: ADR-0081 §1, §5.

### ◻ T-E09a..e [P] Repository sweep: ciphertext in and out, domain types unchanged → T-E08, T-E05
- Split for parallel worktrees (orchestrator-mode, ADR-0066):
  - **T-E09a** `accounts`, `snapshots`
  - **T-E09b** `categories`, `budgets`
  - **T-E09c** `transactions`, `planned`
  - **T-E09d** `recurring` (+ rule overrides, formula)
  - **T-E09e** `preferences`, `webauthn` label, audit writer and reader (`_shared.write_audit` encrypts payloads of user entities under the owner's keys; auth/admin events stay plaintext)
- **Deliverables** (each item): repository functions take `keys: UserKeys`; writes fill `_ct` (+ `name_bidx`) and leave plaintext `NULL`; reads use `_ct` when non-null, else plaintext (dual-read during transition); routers pass `current_keys`. Domain dataclasses are unchanged.
- **Acceptance**: the existing tests of the touched modules pass **unchanged** apart from fixture plumbing (`keys` fixture); new tests show a freshly written row has a `NULL` plaintext column and a non-null `_ct`; `mypy --strict` passes.
- **Validation**: `just test tests/unit/repositories tests/integration`
- References: ADR-0081 §2.

### ◻ T-E10 [P] Aggregates, sorting and search move to Python → T-E09a..e
- **Deliverables**:
  - Rewrite every SQL aggregate on an encrypted column. Inventory as of 2026-11-04: `repositories/transactions.py`, services `accounts` (2), `analytics` (2), `balance` (1), `budget` (5), `categories` (1), `forecast` (3), `recurring_formula` (1). Re-grep at pickup.
  - Pure helpers in `domain/money.py` (`sum_minor`, `sum_by`, `net_by_day`).
  - `description LIKE` becomes an SQL pre-filter plus a casefolded substring match in Python.
  - `ORDER BY name/amount` moves to `sorted()`.
- **Acceptance**: the whole existing test suite passes unchanged, which is the R2 regression net; T-D48 (ledger day net) and T-D51/T-D52 behaviours are explicitly re-asserted.
- **Validation**: `just test`
- References: ADR-0081 §2, §7.

### ◻ T-E11 [P] Static check: encrypted columns and crypto imports → T-E08
- **Deliverables**: extend the ADR-0068 SQL parser test. Fail if an encrypted column appears in `WHERE`, `ORDER BY`, `GROUP BY`, `HAVING`, an aggregate or `LIKE`; fail if `cryptography` or `argon2` is imported outside `budget_planner.crypto`. Document the allowlist policy.
- **Acceptance**: seeded violations fail the test; the current tree passes after T-E10.
- **Validation**: `just test tests/static/`
- References: ADR-0081 §6.

### ◻ T-E12 [S] Escrow backfill CLI → T-E09a..e, T-E02
- **Deliverables**:
  - `python -m budget_planner.cli.encrypt_backfill [--db=…] [--dry-run]`. For each `plaintext` user, in one transaction: generate UMK and DEK_1, create the escrow wrap, encrypt all values into `_ct` and `name_bidx`, `NULL` the plaintext, set `escrowed`. It also covers `audit_log` payloads owned by the user.
  - Idempotent and resumable; logs counts only.
  - Entrypoint runs it after `startup_migrate`, gated by a setting `encryption_backfill_enabled` (default on in v4.0).
  - Takes a `VACUUM INTO` pre-backfill backup (ADR-0071 style, pruned by T-D57 rules).
- **Acceptance**:
  - On a copy of `data/demo.sqlite`, page-level snapshot tests (key pages' HTML) are identical before and after the backfill.
  - A re-run is a no-op.
  - A crash mid-user rolls back that user only.
  - A restore drill on the backfilled drill DB passes.
- **Validation**: `just test tests/integration/cli/test_encrypt_backfill.py`; drill rehearsal logged in the v3 `runbooks/restore-log.md`.
- References: ADR-0082 §2, ADR-0081 §5.

### ◻ T-E13 [P] Performance budget → T-E10
- **Deliverables**: synthetic user generator (20 000 transactions, 30 accounts, 60 categories) and `tests/perf/test_encrypted_render_budget.py` (marker `perf`, `just ci-perf`) measuring p95 for `/today`, `/ledger`, `/budget`, `/overview`, `/accounts`, `/forecast` against a recorded v3 baseline. If the budget is exceeded, add a request-scoped decrypted-row memo (no cross-request cache).
- **Acceptance**: ≤ +50 ms p95 on every listed page; results recorded in the handoff.
- **Validation**: `just ci-perf`
- References: ADR-0081 §3.

### ◻ T-E14 [P] No-plaintext-at-rest and tamper suite → T-E09a..e
- **Deliverables**: an e2e journey on a scratch DB with sentinel strings and amounts, then a byte-scan of `*.db`, `*-wal` and the pre-migration backups; AAD swap tests across users, columns and tables at the SQL level.
- **Acceptance**: no sentinel found after the journey (live writes encrypted); swapped ciphertexts give a `DecryptionError` page, not wrong data.
- **Validation**: `just test tests/security/`
- References: ADR-0081 §6.

---

## Phase 4 — Lifecycle and Security tab

### ◻ T-E15 [S] Password change re-wrap; admin reset → recover; operator CLI → T-E07
- **Deliverables**:
  - `password_change` re-wraps (new wrap, old wrap deleted, same transaction).
  - Admin "Reset password" and `cli/set_password.py` restore sign-in only: they set `must_change_password` and a recovery-required flag.
  - `/auth/recover`: recovery code or PRF passkey → unlock → set password → new recovery code. **Start fresh**: typed email plus confirmation, erases the data rows (T-E18 service, data-only mode), new UMK, default categories re-seeded.
  - Admin dialog copy per ADR-0082 §5.
  - `runbooks/user-admin.md` updated.
- **Acceptance**:
  - The integration matrix covers: reset + recovery code, reset + PRF passkey, reset + neither → locked until Start fresh.
  - An admin can't observe any data across the flow.
  - frontend-visual-audit on `/auth/recover` and the `/settings/users` dialog.
- **Validation**: `just test tests/integration/web/test_recover.py tests/e2e/test_admin_reset_journey.py`
- References: ADR-0082 §4–§5.

### ◻ T-E16 [S] Security → Data protection section → T-E15
- **Deliverables**: in `/settings/security`, show key state and the credentials that unlock data. Actions: regenerate the recovery code (step-up), reset encryption keys (UMK rotation: re-wrap DEKs, re-enter password, new code, PRF passkeys downgraded, other sessions revoked), rotate the data key (DEK v+1, re-encrypt, step-up). Links to export, delete account and `/privacy`.
- **Acceptance**: after UMK rotation old wraps are gone and data still reads; after DEK rotation no `_ct` value carries the old `dek_version`; step-up enforced; frontend-visual-audit.
- **Validation**: `just test tests/integration/web/test_data_protection_tab.py`
- References: ADR-0082 §6–§7, ADR-0080 §7.

### ◻ T-E17 [P] Key hygiene → T-E05
- **Deliverables**: `prctl(PR_SET_DUMPABLE, 0)` at startup (best effort, logged); entrypoint `ulimit -c 0`; extend the redaction deny-list (`umk`, `dek`, `kek`, `swk`, `k_enc`, `k_bidx`, `wrapped*`); a log-sweep test that fails on key-sized base64 runs in captured logs over a full journey.
- **Acceptance**: tests green; `cat /proc/<pid>/status` on prod-sim shows non-dumpable (recorded in the handoff).
- **Validation**: `just test tests/security/test_key_hygiene.py`
- References: ADR-0080 §8.

---

## Phase 5 — Erasure, export, retention

### ◻ T-E18 [S] Erasure service, self-service, admin Erase, deactivation auto-erase → T-E09a..e, T-E16
- **Deliverables**:
  - `services/erasure.py`, implementing ADR-0083 §3 steps 1–7 in one transaction. Modes: `full` and `data_only` (for Start fresh).
  - Self-service "Delete my account and data" (step-up + typed email + export offer).
  - Admin "Erase user…" (step-up + typed email); "Remove" renamed to "Deactivate".
  - Auto-erase 90 days after deactivation, using the T-D60 retention runner.
  - Erasure receipt page.
  - The last-admin invariant is respected.
- **Acceptance**:
  - After erasure no row of the user exists in any user-owned table.
  - Auth audit rows are pseudonymized: no email, IP or user agent.
  - The `users` row is a tombstone.
  - Re-running returns the same receipt.
  - frontend-visual-audit on the confirmation and receipt pages and `/settings/users`.
- **Validation**: `just test tests/integration/services/test_erasure.py tests/e2e/test_erasure_journey.py`
- References: ADR-0083 §1–§3.

### ◻ T-E19 [S] Erasure ledger and replay after restore → T-E18, T-D56
- **Deliverables**:
  - `/data/erasure_ledger.db` (`user_id`, `erased_at`) as a second Litestream DB in both compose stacks, age-encrypted, unbounded retention.
  - The erasure service appends to it in the same request (two-DB write ordered ledger-first; on failure the erasure aborts).
  - `cli/replay_erasures.py`; `/ready` is 503 while unapplied entries exist.
  - Wired into `litestream-restore`, `restore-from-prod.tpl`, `runbooks/restore.md` and `disaster-recovery.md`.
- **Acceptance**: drill scenario — erase a user, restore a pre-erasure point in time, start the app → the replay runs, the user is gone, `/ready` is 200.
- **Validation**: `just test tests/integration/cli/test_replay_erasures.py`; drill run logged.
- References: ADR-0083 §4.

### ◻ T-E20 [P] Export bundle `budget-planner-export/v1` → T-E09a..e
- **Deliverables**: `services/export_bundle.py` and route `GET /settings/security/export` producing JSON (schema version, `exported_at`, `exported_by` email, every user-owned entity decrypted, preferences, own audit history). JSON Schema committed under `docs/schemas/export-v1.json`. Rate limit scope `export` (5/h); audited.
- **Acceptance**: the bundle validates against the schema; a round-trip property holds (every entity on the user's pages appears in the bundle); no other user's data is present.
- **Validation**: `just test tests/integration/web/test_export_bundle.py`
- References: ADR-0083 §5.

### ◻ T-E21 [P] Demo builder from an export bundle → T-E20
- **Deliverables**: `data/scripts/build_demo_db.py --from-export <bundle.json> --to data/demo.sqlite`. Anonymization logic reused. It refuses unless the bundle schema is valid and `exported_by` matches `--expect-email`. It no longer opens any `budget.sqlite`. The tripwire is replaced by the schema and owner check. `just demo-build` and the docs are updated.
- **Acceptance**: the demo build from a fixture bundle passes the existing demo tests; the script has no code path that opens `data/budget.sqlite` (test greps the source).
- **Validation**: `just demo-build-from-export <fixture>` + `just test tests/unit/scripts/test_build_demo_db.py`
- References: ADR-0083 §6.

### ◻ T-E22 [P] `/privacy` page + doc-sync test → T-E18
- **Deliverables**: a public static route `/privacy` (auth-exempt, CSP-compliant) linked from the login page and Data protection. Content per ADR-0083 §8 and ADR-0079 residual risks. A doc-sync test asserts the retention numbers on the page equal the settings defaults.
- **Acceptance**: the page reads correctly logged out and logged in; the test fails when a value diverges; frontend-visual-audit at 1440 / 1024 / 375.
- **Validation**: `just test tests/integration/web/test_privacy_page.py`
- References: ADR-0083 §8.

---

## Phase 6 — Rollout and contract

### ◻ T-E23 [S] Smoke journey v4 + restore-drill decrypt canary → T-E07..T-E22
- **Deliverables**:
  - `tests/smoke/test_prod_smoke.py` gains the claim, recovery-code and unlock steps, and the isolation assertion via the audit tail (metadata only).
  - Canary user `canary@<domain>` with synthetic data. Its credentials are a GitHub environment secret.
  - `restore-drill.yml` signs in as the canary after restore and asserts a sentinel transaction decrypts.
- **Acceptance**: the smoke run against drill is green; the drill run is green with the canary.
- **Validation**: `gh workflow run restore-drill.yml`
- References: ADR-0083 §6.

### ◻ T-E24 [S] Prod rollout v4.0 (expand + backfill) → T-E23 — **human-gated**
- **Deliverables**:
  - Operator approval.
  - Offline backup per the v3 operator checklist.
  - Deploy through the pipeline; the entrypoint runs migrations and then the backfill.
  - Verify: zero `plaintext` users, `/ready` 200, smoke green.
  - Users notified (operator-checklist template).
  - Claim progress tracked weekly in the admin panel; target 30 days.
- **Acceptance**: dated CHANGELOG entry; restore drill against post-backfill prod data green.
- References: ADR-0082 §2.

### ◻ T-E25 [S] Contract migration release → T-E24
- **Deliverables**:
  - Migration dropping the plaintext columns and renaming `_ct` to the original names. Gated: refuses to run when any user is `plaintext`.
  - Remove the dual-read code and the transitional unique indexes.
  - Post-migrate `VACUUM` (with `secure_delete`), a fresh Litestream generation, and a byte-scan on the drill restore of prod.
  - Per ADR-0071 this release breaks N-1 compatibility: rollback is by restore, flagged in the CHANGELOG.
- **Acceptance**: the byte-scan of the restored prod copy finds no known plaintext pattern (sampled from the operator's own export); full suite green.
- References: ADR-0081 §5.

### ◻ T-E26 [P] Security review + external scans → T-E25
- **Deliverables**:
  - `security-reviewer` agent pass over `crypto/`, `services/keys.py`, the auth flows, erasure and export.
  - Re-run T-D42 scans (trivy, testssl, nikto, Observatory).
  - Threat-model re-check against ADR-0079, plus a findings table in the handoff.
  - `/privacy` reviewed by the operator.
- **Acceptance**: no HIGH or CRITICAL findings open; Observatory ≥ A+; ADR-0079 residual-risk list unchanged or amended by a new ADR.
- References: ADR-0079.
