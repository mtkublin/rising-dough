# v4 — Data Protection Implementation Plan

> Requirements: [`docs/requirements.md` §7](../../requirements.md). Decisions: ADR-0079..ADR-0083. Task detail: [`tasks.md`](tasks.md).

## Guiding principles

- **Docs first** (CLAUDE.md). Any deviation from ADR-0079..0083 needs a new or amended ADR before code.
- **Never weaken v3 controls.** CSP, CSRF, step-up re-auth, hashed session ids, rate limits and the user-scoping static check all stay. v4 adds to them.
- **Expand → backfill → contract.** Every schema step stays readable by the previous image (ADR-0071) until the single, announced contract release (T-E25).
- **The existing test suite is the regression net for R2.** Behaviour tests must pass unchanged across the field-encryption phase. Fixture plumbing (a `keys` fixture) is the only allowed edit.
- **Crypto lives in one place.** `budget_planner.crypto` holds only pure functions. No other module imports `cryptography` or `argon2` (static check, T-E11).
- **Prod DB hands-off.** All development runs on scratch DBs or `data/demo.sqlite`. Prod changes only via the deploy pipeline with operator approval (T-E24, T-E25).
- **Functional-first, immutable** (ADR-0021). `UserKeys` is a frozen dataclass passed explicitly. No global key state.

## Architecture delta (v3 → v4)

```
browser ──cookie <session_id>.<SWK>──▶ Caddy ──▶ app
                                               │
             AuthRequired → session lookup (sha256(id))
             → unwrap UMK with SWK (sessions.wrapped_umk)
             → unwrap DEK_v (user_key_wraps, layer=dek)
             → request.state.keys : UserKeys   (request-scoped)
                                               │
             routers → services(keys) → repositories(keys)
                         │                       │
               Python aggregates          SQL on plaintext metadata;
               sort / search              encrypt/decrypt value columns
                                               │
                                    SQLite (/data/budget.db)
                                    + erasure_ledger.db
                                               │
                         Litestream (age-encrypted) → Object Storage (≤37 d)

server secrets: PEPPER, ESCROW_MASTER ← Scaleway Secret Manager (tmpfs at boot)
```

## Phased delivery

### Phase 0 — Preconditions (T-E00)

Entry: none. Exit: v3 Phase 5 merged; T-D53 merged; T-D50 ADR renumbered off 0076; ADR-0079..0083 Accepted.

### Phase 1 — Crypto core and secrets (T-E01..T-E04)

Goal: every building block exists and is tested; no user-visible change.
Exit:
- `crypto/` fully covered by tests.
- Prod refuses to start without secrets.
- Drill host reads secrets from Secret Manager (or the recorded fallback).
- Key-wrap schema migrated on drill.

### Phase 2 — Session binding and unlock (T-E05..T-E07)

Goal: logging in yields keys; nothing yet encrypts user data.
Exit:
- Password, PRF passkey and recovery-code unlock work.
- Locked sessions behave per ADR-0080 §4.
- Claim flow works on a scratch DB.
- frontend-visual-audit clean on `/auth/unlock`, `/auth/protect` and `/settings/security`.

### Phase 3 — Field encryption (T-E08..T-E14)

Goal: all user values encrypted at rest; every feature unchanged.
Exit:
- The full existing suite is green unchanged.
- Static check green.
- Backfill rehearsed on drill (restore drill logged).
- Performance budget met (≤ +50 ms p95).
- Byte-scan clean.

Parallelism: T-E09a..e run in parallel worktrees (orchestrator-mode). T-E10, T-E11, T-E13 and T-E14 follow.

### Phase 4 — Lifecycle and Security tab (T-E15..T-E17)

Goal: every credential operation is key-aware; admin reset semantics are live.
Exit:
- The lifecycle e2e matrix is green.
- `runbooks/user-admin.md` updated.
- Key-hygiene checks recorded.

### Phase 5 — Erasure, export, retention (T-E18..T-E22)

Goal: R4 delivered; keyless operations migrated.
Exit:
- Erasure e2e green.
- Erasure replay after restore proven on drill.
- Export bundle schema committed.
- Demo builder no longer opens prod.
- `/privacy` published on drill.

### Phase 6 — Rollout and contract (T-E23..T-E26)

Goal: prod on v4 with no plaintext at rest.
Exit:
- v4.0 deployed and backfilled.
- Users notified.
- Contract release shipped.
- Byte-scan of the restored prod copy clean.
- Security review: no HIGH or CRITICAL findings.
- Dated go-live entry in the CHANGELOG.

## Rollout order (compressed)

```
T-E00 ─▶ T-E01 ┐
        T-E02 ─▶ T-E03
        T-E04 ┘
           │
           ▼
        T-E05 ─▶ T-E06
              └▶ T-E07
           │
           ▼
        T-E08 ─▶ T-E09a..e (parallel) ─▶ T-E10 ─▶ T-E13
              └▶ T-E11                 └▶ T-E14
                                       └▶ T-E12 (needs T-E02)
           │
           ▼
        T-E15 ─▶ T-E16     T-E17 (after T-E05)
           │
           ▼
        T-E18 ─▶ T-E19 (needs T-D56)
        T-E20 ─▶ T-E21
        T-E22 (after T-E18)
           │
           ▼
        T-E23 ─▶ T-E24 [human] ─▶ T-E25 ─▶ T-E26
```

## Release mapping

| Release | Contains | N-1 safe |
|---|---|---|
| v4.0 | Phases 1–5 + backfill (escrow) | yes |
| v4.0.x | fixes during the claim window | yes |
| v4.1 | contract migration (T-E25) | **no**: rollback by restore (ADR-0071) |

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Behaviour drift when aggregates move to Python | unchanged suite as the regression net (T-E10); page HTML snapshot equality across backfill (T-E12) |
| Lost `PEPPER` or `ESCROW_MASTER` | operator password-manager copy; pepper loss is recoverable via PRF or recovery code; claim window bounds escrow dependence |
| Users lose every credential | recovery code mandatory at claim; PRF passkeys encouraged; `/privacy` states the consequence |
| Performance regression | budget test (T-E13); request-scoped memo |
| Restore resurrects erased users | erasure ledger + replay + readiness gate (T-E19) |
| Litestream or SQLite behaviour with large BLOB rewrites during backfill | rehearsal on drill; pre-backfill `VACUUM INTO` backup |
| PRF unsupported on some authenticators | "Sign-in only" label + password unlock; no lockout |

## Handoff shape (per task)

Same as v3 (`docs/plans/v3/implementation_plan.md` §Handoff shape): Context, Deliverables, Acceptance, Dependencies, Validation hook. The handoff also records:
- the ADR sections it implements;
- for frontend tasks, the frontend-visual-audit routes and findings;
- for crypto tasks, the parameters actually used (Argon2 params, library versions).

## Guardrails

- **Do not** add a cross-request plaintext cache, log decrypted values, or persist an SWK or UMK anywhere server-side.
- **Do not** add a code path that decrypts a user's data without that user's session, other than the one-time escrow backfill (T-E12) and claim (T-E07).
- **Do not** soft-delete key wraps; hard delete only (ADR-0080 §2).
- **Do not** weaken the static checks to make a feature work. Change the ADR first.
- **Do** write a dated `docs/CHANGELOG.md` line per merged task and mark it `✅` in `tasks.md`.
