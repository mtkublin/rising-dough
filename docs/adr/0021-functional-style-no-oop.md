# ADR-0021: Functional Style, No Gratuitous OOP

- **Status**: Accepted
- **Date**: 2026-10-23
- **Amended by**: [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md) (2026-11-20: pure layers defined and enforced by guards)

## Decision

- Services and repositories are **modules of pure functions**, not classes.
- Data types are frozen `@dataclass(frozen=True)` or Pydantic models (as DTOs).
- Classes are allowed **only** when they serve as pure data containers (dataclasses) or Protocols for structural typing.
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
