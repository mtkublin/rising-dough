# ADR-0079: v4 Threat Model and Data-Protection Approach

- **Status**: Proposed
- **Date**: 2026-11-04
- **Supersedes**: none. **Amends**: [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) (isolation becomes cryptographic, not only authz), requirements §6.8 non-goals "admin visibility into user data" and "hard-delete flows" (both addressed in v4).
- **Related**: [ADR-0078](0078-v3-data-protection-quick-wins.md) (v3 quick wins, prerequisite), [ADR-0080](0080-v4-envelope-encryption-key-hierarchy-and-sessions.md) (keys), [ADR-0081](0081-v4-field-level-encryption-scope-and-query-model.md) (what is encrypted, how queries work), [ADR-0082](0082-v4-account-lifecycle-recovery-and-migration.md) (lifecycle, recovery, migration), [ADR-0083](0083-v4-right-to-be-forgotten-portability-and-retention.md) (erasure, export, retention)

## Context

v3 isolates users by authorization only (ADR-0061). Anyone with the DB file sees everything: the operator with root, a backup thief, someone holding the restore credential, a future bug that bypasses repository scoping. The operator wants v4 to meet four hard requirements:

- **R1. Good application security.** No regression of the v3 baseline (CSP, CSRF, step-up re-auth, rate limits, hashed session ids), plus defence in depth for the new key material.
- **R2. No breaking of existing functionality**, or an industry-standard workaround documented in the plan.
- **R3. User data is secure and not visible to anyone who is not logged in as that user**, malicious actors included. That covers the operator, the app admin role, and attackers holding the DB, backups or infrastructure credentials.
- **R4. Right to be forgotten.** A user's data can be erased irreversibly, backups included, within a stated bound.

## Adversaries

| # | Adversary | Capability | v4 goal |
|---|---|---|---|
| A1 | Admin role (`is_admin=1`) via the UI | Admin panel, debug routes | **Cannot read** other users' data. |
| A2 | Holder of a DB copy: Litestream bucket, `VACUUM INTO` backup, drill host, stolen disk, leaked Terraform state + bucket key | Offline, unlimited time | **Cannot read** any user's financial data. |
| A3 | Operator or attacker with **passive** host access while no user is logged in: SSH, `sqlite3`, reading files, env and secret files | Reads everything at rest on the host | **Cannot read** data of users without a live session. |
| A4 | Operator or attacker with **active** host control during a user session: memory dumps, patched code, malicious deploy | Arbitrary code inside the trust boundary | **Not fully preventable** server-side (see Residual risks). Raised cost, detectable, limited to users who log in while compromised. |
| A5 | Network attacker | TLS-terminated traffic | Out of reach (TLS, HSTS preload; v3 ADR-0036). |
| A6 | Attacker with a stolen session cookie | Acts as the user | Limited by v3 session hardening (absolute cap, step-up, revocation). v4 adds: revoking the session destroys that session's key copy. |
| A7 | Former user exercising erasure; data subject | Wants their data gone | Erasure is cryptographic and immediate for live data, bounded at 37 d for backups (ADR-0078 §4). |

R3 maps to A1, A2, A3 and A6. A4 is stated honestly as a residual.

## Options evaluated

| Option | A1 | A2 | A3 | A4 | R2 cost | Verdict |
|---|---|---|---|---|---|---|
| **Dynamic data masking** | ✓ (authz already does this) | ✗ | ✗ | ✗ | none | **Rejected.** SQLite has none; elsewhere it's a presentation policy that privileged DB access bypasses. |
| **Full-DB encryption, server-held key** (SQLCipher, LUKS) | ✓ | partial (✓ if the key is off the stolen media) | ✗ (key on host) | ✗ | image change; Litestream compatibility unverified | **Rejected as the primary control.** ADR-0078 §3 already covers backups. |
| **Per-user keys in a gated table** (server-readable) | ✓ | ✗ (table in the same backup) | ✗ | ✗ | moderate | **Rejected.** The gate is authz again. |
| **Per-user envelope encryption, keys wrapped by user-held secrets** (password via Argon2id, passkey PRF, recovery code); field-level AES-GCM; server unwraps only during a session | ✓ | ✓ | ✓ | ✗ | moderate (aggregates move to Python; reset semantics change) | **Chosen.** |
| Same, **per-user SQLCipher files** instead of field-level | ✓ | ✓ | ✓ | ✗ | high: migrations can't run at boot (ADR-0071), dynamic Litestream DB list, SQLCipher + Litestream unverified, connection-per-user plumbing | Rejected for v4. Field-level keeps one DB and the v3 operational model. Revisit if metadata leakage (ADR-0081 §4) becomes unacceptable. |
| **Client-side E2EE** (browser holds keys, zero-knowledge server) | ✓ | ✓ | ✓ | partial (served JS still trusted) | very high: rewrite templates, services and auth into a client app; server can't validate business rules; sync protocol | **Deferred** (candidate v5). Fails R2 without a rewrite. |
| Homomorphic or order-preserving encryption for SQL over ciphertext | — | — | — | — | extreme or leaky | Rejected. |
| Confidential VM (SEV-SNP / TDX) | ✗ vs operator | ✓ | — | ✗ (operator controls the image) | not offered on Stardust | Rejected. |

## Decision

1. v4 implements **per-user envelope encryption with field-level AES-256-GCM**:
   - **Key hierarchy** (ADR-0080). Each user has a random data key. It's stored only in wrapped (encrypted) form, under key-encryption keys derived from secrets only the user holds: their password (Argon2id + server pepper), each PRF-capable passkey, and a one-time recovery code. While a session is live, the data key is wrapped under a per-session key that lives **only in the user's session cookie**.
   - **Encryption scope and queries** (ADR-0081). All user-authored values (amounts, names, descriptions, formulas, preference values, audit payloads) are encrypted. Structural metadata (ids, foreign keys, dates, enums) stays plaintext so SQL can still filter by owner, date and relation. Aggregates, sorting and text search over encrypted fields move to the Python service layer.
   - **Lifecycle** (ADR-0082). Covers onboarding, password change, passkeys, recovery, admin reset, and the one-time migration of existing plaintext data through a server-escrow "claim" step.
   - **Erasure and portability** (ADR-0083). Crypto-shredding plus hard purge, self-service export, retention bounds.
2. Client-side E2EE is recorded as the v5 path if A4 must be closed; it isn't v4 scope.
3. A user-facing **"What the operator can and cannot see"** page ships with v4. It replaces ADR-0078 §8's v3 statement and is kept in sync with this ADR's residual risks.

## Residual risks (accepted, documented to users)

- **A4, active host compromise during a session.** Server-side decryption means code on the server sees plaintext while the user is logged in. An operator who patches the app can capture keys at the next login. Mitigations:
  - Signed images (cosign, ADR-0037) verified by the deploy script.
  - Deploys only through the audited pipeline.
  - Core dumps disabled and no swap (ADR-0080 §8).
  - Key-unwrap events audited.
  - Exposure limited to users who log in during the compromise.
- **Metadata stays plaintext.** Row counts, dates, which account or category a row links to, edit timestamps, and the ciphertext length of names (padded to buckets) remain visible. Amounts, names and descriptions are not. ADR-0081 §4 lists the full set.
- **Backups keep ciphertext and wrapped keys for up to 37 days after erasure.** Unwrapping them needs the user's credentials, and the copies expire on schedule (ADR-0083).
- **Escrow window during migration and onboarding.** Until a user "claims" their key by setting their own password (ADR-0082 §2), their key is escrowed under a server key, which protects only against A2. The window is bounded and visible to the user.
- **Lost credentials mean lost data.** If a user loses their password, all PRF passkeys and the recovery code, no one can recover the data, the admin included. This is the intended property and is stated at enrollment.

## Consequences

- ADR-0061's isolation guarantee becomes cryptographic for A1, A2 and A3.
- Product semantics change in two documented places:
  - Admin password reset no longer preserves data without the user's recovery code or a PRF passkey (ADR-0082 §5).
  - Some jobs that ran without a logged-in user switch to export-based or metadata-only operation (ADR-0083 §6).
- New dependency `argon2-cffi`. `cryptography` is already present (transitive, pinned by ADR-0067). Stack change recorded in requirements §7.
- About 18 SQL aggregate sites in 8 modules move to Python (ADR-0081 §3), bounded by a page-render performance budget.
