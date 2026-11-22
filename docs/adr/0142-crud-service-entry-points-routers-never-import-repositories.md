# ADR-0142: CRUD Service Entry Points; Routers Never Import Repositories

- Status: Accepted (2026-11-21)
- Amends: ADR-0021
- Relates to: ADR-0019, ADR-0022, ADR-0130, ADR-0107
- Task: T-Q241 (finding Q-045)

## Context

ADR-0021 says routers call services and services call repositories, and the import-linter contract
"routers do not import repositories" encoded it, but 13 routers (36 imports) were waived in
`allowlists/layering.toml` and `ignore_imports`. Six of them wrote through repositories directly.
OQ-12 asked whether to land this before or after the Sourdough redesign (ADR-0107).

## Decision

1. **One service module per entity owns the router-facing CRUD surface:** `services/transactions`,
   `services/planned`, `services/accounts` (also account snapshots), `services/recurring` (rules and
   overrides), `services/categories`, `services/budget_overrides` (budget defaults, recurring and
   one-off overrides), `services/fx` (cached rate listing), `services/auth` (session and passkey
   listing; `IssuedSession`, `session_handle`), `services/users` (`AuthUser`).
2. **Routers import no `budget_planner.repositories` module at all.** The contract has an empty
   `ignore_imports`; `tests/architecture/test_routers_no_repositories.py` asserts it by AST scan with no
   allowlist. A new waiver needs an ADR-0130 amendment.
3. **Plain functions, no classes.** Where a router operation is a single repository call the service
   exposes it under the repository's name (`find_by_id`, `list_all`, `create`, `update`, ...) as a
   binding, so audit, soft-delete and user scoping stay in the repository helpers (ADR-0019, ADR-0022)
   and cannot be bypassed. Logic that grows around a call (validation, two mutators) moves into a named
   service function in the same module, with keyword arguments after `conn, user_id` (ADR-0021, T-Q243)
   and one `db_transaction` when it calls two or more mutators (G8).
4. Router thinning that follows (arithmetic, multi-step flows in routers) stays with T-Q265 to T-Q267.

## Consequences

- OQ-12: done before the redesign; the redesign's routers inherit the rule.
- The bindings are deliberately thin; they exist to fix the dependency direction first. Replacing a
  binding with a function does not change any router call.
- Removed: 13 `layering` allowlist entries (`contract:routers-not-repositories`, 36 imports) and the
  matching `ignore_imports` lines.

## Amendment 2026-11-22 (operator decision; T-Q285)

The pass-through bindings of the T-Q241 amendment are replaced by real service functions that own input validation and the single `db_transaction` of a mutation (a service calling two or more mutators uses one transaction, ADR-0137). Routers still make one service call. Whether the one-transaction rule (G8) becomes a guard is decided in T-Q285. Runs after T-Q267 and T-Q262.
