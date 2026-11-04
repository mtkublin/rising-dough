# ADR-0082: v4 Account Lifecycle Under Encryption — Onboarding, Credentials, Recovery, Migration

- **Status**: Proposed
- **Date**: 2026-11-04
- **Amends**:
  - [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) §Context ("password recovery = admin triggers a reset" now restores sign-in, not data access)
  - [ADR-0073](0073-user-admin-panel-guard-and-one-shot-password.md) (the one-shot password wraps no key)
  - [ADR-0074](0074-password-change-policy-and-forced-rotation.md) (password change re-wraps the key; forced rotation becomes the claim point)
  - [ADR-0069](0069-admin-bootstrap-env-policy-and-operator-cli.md) (operator `set_password` CLI semantics)
  - [ADR-0075](0075-security-controls-live-in-settings.md) (Security tab gains a Data protection section)
- **Related**: [ADR-0080](0080-v4-envelope-encryption-key-hierarchy-and-sessions.md), [ADR-0081](0081-v4-field-level-encryption-scope-and-query-model.md), [ADR-0083](0083-v4-right-to-be-forgotten-portability-and-retention.md), ADR-0076 (step-up re-auth)

## Context

Once the user's credentials are the only path to their key (ADR-0080), every account operation has to be re-examined: create, first login, password change, passkeys, admin reset, lost credentials. So does the move of existing v3 plaintext data into ciphertext.

The industry pattern for "the provider can't read it, so the provider can't restore it" is the same across Bitwarden, 1Password (Emergency Kit), Proton (recovery phrase) and Apple Advanced Data Protection (recovery key). It has three parts: several independent unlock credentials, a user-held recovery code shown once, and an explicit statement that losing all of them loses the data. v4 adopts it.

## Decision

### 1. `users.key_state`

| State | Meaning | Data at rest |
|---|---|---|
| `plaintext` | v3 row not yet backfilled (exists only between the v4.0 expand migration and the backfill) | plaintext |
| `pending` | new user; no UMK yet; no data possible (forced rotation blocks every data route) | none |
| `escrowed` | UMK wrapped **only** under `KEK_escrow` (server secret) | ciphertext; readable by the server without the user (A3) |
| `claimed` | UMK wrapped under the user's password (+ PRF passkeys + recovery code); escrow wrap deleted | ciphertext; unreadable without the user |
| `erased` | crypto-shredded and purged (ADR-0083) | none |

Allowed transitions: `plaintext → escrowed → claimed`, `pending → claimed`, `* → erased`. Anything else is rejected in the service layer. The admin panel shows the state per user. It's metadata, not data.

### 2. Migrating existing data: escrow, then claim

1. **Backfill at deploy.** After the v4.0 expand migration (ADR-0081 §5), the entrypoint runs `python -m budget_planner.cli.encrypt_backfill`. For each `plaintext` user, in one transaction, it:
   - generates a UMK and DEK_1;
   - wraps the UMK under `KEK_escrow`;
   - encrypts every value into the `_ct` columns, `NULL`s the plaintext, and sets `escrowed`.

   It's idempotent, resumable per user, and logs counts only. A restore drill (T-D41) runs against a pre-backfill copy before prod.

   From this point all data is ciphertext at rest, which covers A2 (the backup thief doesn't hold `ESCROW_MASTER`).
2. **Claim at next login.** A user in `escrowed` state who logs in with their password goes through a one-page **"Protect your data"** step before anything else. It works like forced rotation: middleware redirect, with HTMX and JSON variants per ADR-0070 §4.
   - The server unwraps the UMK through escrow and creates the `password` wrap from the password just entered.
   - The server generates and shows the **recovery code** (§4). The user confirms it by typing its last group.
   - Optionally the user adds PRF to existing passkeys (a single `get()` per passkey).
   - The escrow wrap is **deleted** and the state becomes `claimed`. Audited as `escrow_claimed`.
   - Passkey-only users (no password, possible since T-D02) claim through PRF if their passkey supports it. Otherwise they're asked to set a password first.
3. **The escrow window** runs from the v4.0 deploy to each user's next login. Target: every active user claims within 30 days. The admin panel lists unclaimed users (state only), and the v4 runbook asks the operator to notify them. Escrowed users are never locked out, since escrow still unlocks. The contract migration (ADR-0081 §5) depends only on there being no `plaintext` users, not on claims.
4. The **"What the operator can see"** page (ADR-0079) shows each user their own state. `escrowed` reads as "Pending: finish protecting your data by signing in".

### 3. New users

- Admin creation (ADR-0073) creates the user in `pending`, with no key. The one-shot password authenticates only, and wraps nothing. The admin who saw it learns nothing that decrypts data.
- First login hits forced rotation (ADR-0074). When the user sets their own password, the server generates the UMK and DEK_1, wraps under the new password, shows the recovery code, and sets `claimed`. Rotation and claim are a single step.
- Admin bootstrap (ADR-0069) follows the same path. The legacy `user_id = 1` row with v3 history is backfilled under escrow (§2) and claimed at the admin's next login.

### 4. Credentials

- **Password login**: Argon2id derivation, then unwrap (ADR-0080 §2). Expected ~0.3–0.5 s on Stardust1-S. The login button shows a progress state.
- **Password change** (ADR-0074, still requires the current password): a new `password` wrap from the new password, and the old wrap is deleted in the same transaction. The session already holds the UMK. The existing "revoke other sessions" rule is unchanged.
- **Passkey registration** (step-up guarded, ADR-0076): the JS requests the WebAuthn **PRF** extension. Many authenticators return PRF output only on `get()`, so registration is followed by one immediate `get()` with `prf.eval.first = "bp/prf/v1"` (an app-wide salt; PRF output differs per credential anyway). If output comes back, a `passkey_prf` wrap is created and the passkey is labelled **"Signs in and unlocks data"**. If not, it's **"Sign-in only"**: logging in with it gives a locked session (ADR-0080 §4), which the password or recovery code unlocks.
- **Passkey revoke**: its wrap row is hard-deleted along with the credential.
- **Recovery code**: 128-bit random, displayed as 8 groups of 4 Crockford-base32 characters. It's shown once at claim, can be downloaded as a text file and printed, and must be confirmed by typing its last group. It can be regenerated from Settings → Security → Data protection (step-up guarded), which replaces the old wrap. Using it to unlock (`/auth/recover`) consumes it: the user must then set a new password and receives a new recovery code.

### 5. Admin password reset

What changes: **a reset restores sign-in, not data access.**

- The admin "Reset password" action (ADR-0073) and the operator CLI `set_password` (ADR-0069) still issue a one-shot password and set `must_change_password`. After signing in, the user lands in a **locked** session and is sent to `/auth/recover`, where they unlock with:
  - their **recovery code**, or
  - a **PRF passkey** (the "Unlock with passkey" button).

  After unlocking they set a new password, which creates a new `password` wrap and deletes the old one, and they receive a new recovery code.
- If the user has neither, `/auth/recover` offers **"Start fresh"**. It requires typing the account email and confirming that the data will be permanently erased. It runs ADR-0083 erasure for the data rows only: the account, email and sessions are kept. The user gets a new UMK and an empty account with the default categories seeded. There's no time-limited archive. A user who expects to find their recovery code can simply leave the session locked and come back.
- Before confirming, the admin dialog says plainly: *"This lets the user sign in again. It does not restore their data unless they have their recovery code or a passkey that unlocks data."*
- `runbooks/user-admin.md` is updated with this flow.

### 6. Reset all credentials (UMK rotation)

Settings → Security → Data protection → **"Reset encryption keys"**, step-up guarded, for when a user suspects their credentials are exposed:

- generate a new UMK and re-wrap the current DEKs under it;
- re-enter the password, which creates a new `password` wrap;
- issue a new recovery code;
- downgrade every PRF passkey to sign-in only until it is re-unlocked (one `get()` each);
- revoke all other sessions;
- optionally run DEK rotation too (ADR-0080 §7).

### 7. Security tab additions (ADR-0075)

A new **Data protection** section in `/settings/security` shows:

- key state;
- which credentials unlock data (password, each passkey's label, recovery code present yes/no);
- regenerate the recovery code;
- reset encryption keys;
- rotate the data key;
- a link to "What the operator can see";
- the export and delete-account actions (ADR-0083).

## Consequences

- From the v4.0 deploy, no user data is plaintext at rest. From each user's claim, the operator can't read that user's data without an active session (ADR-0079 A3).
- Users are told plainly at claim time: "If you lose your password, every passkey that unlocks data, and this recovery code, nobody, including the administrator, can recover your data."
- Admin reset changes meaning. This is the documented R2 workaround, and it's the industry standard.
- Passkey-only sign-in remains available. Data unlock needs PRF or a password, and the UI labels passkeys accordingly.
- The T-D43 smoke journey gains a claim step and a recovery-code step (`runbooks/deploy.md` updated).

## Alternatives considered

- **Admin-escrowed recovery** (the admin holds a recovery wrap for everyone). Rejected: it recreates A1/A3 exposure for every user.
- **Optional per-user escrow** ("let the admin recover me"). Deferred. It's honest if opt-in and labelled, but adds a second trust model. Can be added later as a `kind='admin_recovery'` wrap without schema changes.
- **Email-based recovery.** Out of scope (no email flow, ADR-0061), and an emailed secret would defeat A3.
- **Lazy backfill at each login instead of escrow.** Rejected: plaintext would remain at rest indefinitely for users who never log in, and the contract migration could never run.
