# ADR-0021: Functional Style, No Gratuitous OOP

- **Status**: Accepted
- **Date**: 2026-10-23
- **Amended by**: [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md) (2026-11-20: pure layers defined and enforced by guards)

## Decision

- Services and repositories are **modules of pure functions**, not classes.
- Data types are frozen `@dataclass(frozen=True)` or Pydantic models (as DTOs).
- Classes are allowed **only** when they serve as pure data containers (dataclasses) or Protocols for structural typing.
- Framework-required classes (Pydantic models, Starlette middleware, `Protocol`s) and the `request`/memo parameters of framework callbacks are exempt; module-level constants are immutable (`MappingProxyType`, tuples, frozensets) and per-call state lives in `ContextVar`s or on the connection, never in module-level mutables (T-Q258, T-Q263).
- No service-locator / dependency-injection framework. Dependencies (DB connection, HTTP client) are passed as function arguments.
- Build new values; do not mutate inputs. Where SQLite requires imperative statements, those are isolated inside the repository function.

## Consequences

- Trivial unit testing — pass fixtures, assert returned value.
- No hidden state outside the DB connection and FastAPI request.
- Code review complexity bounded to the function in front of you.
- Easy mental model for new contributors.

## Alternatives Considered

- **Repository + Service classes**: ceremony; little benefit when functions suffice.
- **Framework-driven DI (`dependency-injector`, `kink`)**: adds a stage to every test; argument passing is simpler.

## Amendment 2026-11-22 (T-Q264, Q-074; ADR-0130 section 5)

Pure services and `domain/` take every effect and every setting as an argument:

- **Entropy port.** `domain/ports.TokenSource` (`new_token(nbytes)`) is the only way a service gets random tokens. The CSPRNG adapter is `adapters/entropy.SecretsTokenSource`, injected from the web edge (`web/deps.get_token_source`); tests inject `tests/auth_support.FakeTokenSource`. `users.create_user`, `users.reset_password`, `users.generate_password` and `_passwords.dummy_hash` (off-table cost only) require it. The method is not named `token_urlsafe` so the guard cannot confuse the port with the stdlib call.
- **Hashing.** bcrypt stays in `services/_passwords` (deterministic CPU work behind module functions; only its entropy use was an effect). Rounds, token length and constant-time comparison are unchanged.
- **Settings slices.** Services never import `budget_planner.config` and never call `get_settings()`. Each takes the slice it reads as a read-only `Protocol` (`RateLimitSettings`, `RetentionSettings`, `BootstrapSettings`, `WebAuthnSettings`, `fx.HasBaseCurrency`) or a plain value (`budget.*` take `base_currency: str`, required; `fx.BaseCurrency` wraps a bare code). `users.bootstrap_admin_at_startup` takes the `connect` factory explicitly.
- **`ResolvedSettings`.** Values derived from `Settings` (production DB path default, dev cookie-secret fallback) live in the frozen `config.ResolvedSettings`, returned by `Settings.resolve()`; `Settings._finalise` only validates (no `object.__setattr__`). Edge readers (`db.connection`, `db.startup_migrate`, `web.auth_cookies`) use `settings.resolve()`.
- Logging inside services stays permitted through `budget_planner.logging.get_logger` (operator ruling, ADR-0130). The `get_settings` `lru_cache` (functional_first `hidden-cache`) is unchanged here; `get_settings()` is read only at edges.

## Amendment 2026-11-22 (operator decision; T-Q291)

Reverses the "Hashing" note of the T-Q264 amendment (bcrypt stays in `services/_passwords`): password hashing becomes a port. `domain/ports.PasswordHasher` is a `Protocol` (`hash`, `verify`); the bcrypt adapter lives in `adapters/` and is injected from the web edge like `TokenSource`; tests inject a fake. Rounds and constant-time comparison are unchanged. Implementation (T-Q291): the port also carries `verify_dummy` (burns one verify at the same cost for unknown users, the timing-oracle guard that `dummy_hash` used to provide); `domain/ports.MAX_PASSWORD_BYTES` holds the 72-byte limit; the cost comes from `Settings.bcrypt_rounds` (`BUDGET_BCRYPT_ROUNDS`, default 12) so the web provider, lifespan bootstrap and `set_password` CLI build `BcryptHasher(rounds=...)` at the edge; service tests inject `tests.auth_support.FakePasswordHasher`; G22 purity now lists `bcrypt` among forbidden imports for `services/` and `domain/`.
