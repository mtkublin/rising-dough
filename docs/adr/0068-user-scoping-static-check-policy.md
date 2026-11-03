# ADR-0068: User-Scoping Static Check — Scope, Rules, and Allowlist Policy

- **Status**: Accepted
- **Date**: 2026-11-03
- **Related**: ADR-0022 (repository discipline, amended), ADR-0061 §2/§5 (multi-user data isolation), T-D16

## Context

T-D16 makes every repository function take `user_id` and filter on it, and asks for a `sqlglot`-backed architecture test that fails CI when a query on a user-owned table lacks the predicate. Implementing it forced several choices the task spec leaves open: which layers to scan, how to treat joined tables, how the credential tables arriving with T-D02 (`sessions`, `webauthn_credentials`) are scoped, and how exceptions are recorded.

## Decision

1. **Checker** lives in `tests/architecture/_user_scoping.py` (stdlib `ast` + `sqlglot`; no `libcst` dependency). It reconstructs SQL passed to `.execute()` / `.executemany()` from literals, f-strings (module-level string constants are inlined; other holes become a placeholder), `+`/`+=` concatenation, and `" AND ".join(<locally built clause list>)`. Branches are unioned — it is a backstop, not a proof.
2. **Scan scope**: `repositories/`, `services/`, and `web/routers/`. Repositories own SQL, but stray raw SQL in upper layers is held to the same bar.
3. **Rules**:
   - SELECT/UPDATE/DELETE on a directly user-owned table needs `<alias>.user_id = …` in that query's own WHERE or JOIN ON (unqualified `user_id` is accepted for the primary table). This applies to **every** user-owned table in the query, including joined ones — e.g. `JOIN categories c ON c.id = t.category_id AND c.user_id = t.user_id`.
   - FK-scoped tables (`account_snapshots` → `accounts`, `recurring_rule_overrides` → `recurring_rules`) need a user-scoped reference to the parent in the same statement (JOIN or EXISTS). INSERTs into them need a user-scoped parent ownership check in the same top-level function; a failed check raises `LookupError`.
   - INSERT into a directly user-owned table must list `user_id`.
   - Credential tables (`sessions`, `webauthn_credentials`) may alternatively be keyed by their opaque identifier (`id`/`session_id`/`token_hash`, `credential_id`): possessing the token is the authentication step that *yields* the user id.
4. **Signature rule**: public functions in user-scoped repository modules are `(conn, user_id, …)`. Exempt modules (`_shared`, `audit`, `fx`, and T-D02a's `sessions` / `webauthn` / `auth_users`, plus T-D19's write-side `users` repository — `users` is the identity table, ADR-0069) are listed with reasons in the test. Row-id lookups on `webauthn_credentials` (`_get_by_id`, `update_sign_count`, `revoke_credential`) still take and filter on `user_id`; only the opaque `credential_id` lookup is exempt.
5. **Allowlists** are explicit and reasoned:
   - SQL: `SQL_ALLOWLIST[(path, function)] = "reason"` in `tests/architecture/test_user_id_filter.py`, reserved for deliberately cross-user queries (admin panel, system sweepers). A test fails on stale entries. Empty at introduction.
   - Hard-coded `user_id = 1`: `.user-id-filter-allowlist` (one path per line). At introduction it holds only `db/seed.py` (demo seed runs as the bootstrap admin). The pre-T-D02 `web.deps.current_user_id` fallback (`return 1`) is tracked by its `TODO(T-D02)` and removed by T-D02b.
6. A regression test (`test_user_id_filter_regression.py`) writes leaky temp modules and asserts the checker reports them, so a silently broken checker cannot pass.

## Consequences

- New SQL on user-owned tables fails CI unless scoped or allowlisted with a reason; T-D17 (admin panel) will add the first SQL allowlist entries.
- Joined user-owned tables carry a redundant `user_id` equality — cheap defence in depth against FK rows pointing across users.
- The checker is heuristic; dynamic SQL it cannot resolve becomes a placeholder and is still checked for the table/predicate structure that remains.
