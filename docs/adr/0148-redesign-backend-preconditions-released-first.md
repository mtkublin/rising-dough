# ADR-0148: Redesign Backend Preconditions Ship in Their Own Release, Before the Migration

- **Status**: Accepted (implementation pending, T-UR29..T-UR35)
- **Date**: 2026-11-22
- **Amends**: [ADR-0134](0134-redesign-scope-decisions-from-the-designer-change-request.md) (Context and Consequences: "land in the redesign release"); [ADR-0107](0107-sourdough-redesign-from-designer-handoff.md) §8 (rollout) and §9 (sequencing)
- **Relates to**: [ADR-0099](0099-release-and-environment-policy.md) (release pipeline), [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md), [ADR-0073](0073-user-admin-panel-guard-and-one-shot-password.md) (admin guards), [ADR-0021](0021-functional-style-no-oop.md) (injected ports), [ADR-0106](0106-ui-behaviour-test-harness.md) (contract tests), [ADR-0147](0147-handoff-parity-ci-rendered-references-and-data-overlay.md) (value inventory)

## Context

ADR-0134 put the app changes from the designer answers (invites, invite email, first-run setup, account delete rule, user edit guards) into the single redesign release. That release already carries the whole new frontend. Bundling schema migrations (which apply automatically on prod start) and behaviour changes into it makes it larger and harder to roll back, and mixes backend review with template work. The operator decided (2026-11-22) that everything backend that can ship before the migration ships first, in a dedicated PR and release; the migration itself is frontend work only.

## Decision

### 1. A precondition release before T-UR00

- One PR to `main` with the backend items below, released to prod through the ADR-0099 pipeline (`drill-gate`, approved apply). The redesign migration (T-UR00 onward) starts only after that release is live and its smoke passed.
- **In scope**: schema migrations, repositories, services, injected ports, config switches, service-level guards, and view-model or service fields the handoff needs. Existing routes may change only the service call and the error they show through the existing flash ([ADR-0143](0143-htmx-event-and-error-flash-contract.md)).
- **Out of scope**: templates, CSS, JS, and new routes that render pages. Those stay with their page in the migration. Dormant services (invites, setup token) ship tested but unreachable from the UI until their pages land.

### 2. Items

| Task | What ships | Was |
|---|---|---|
| T-UR29 | User edit guards: refuse self-demotion and demoting the last admin; email is read-only on edit; delete keeps refusing self and last admin | T-UR20 server side |
| T-UR30 | Invite data layer: migration, repository, service (create, resend, revoke, accept, link states pending / expired / used / invalid); token stored hashed, never logged | T-UR20 data part |
| T-UR31 | Invite email through an injected mail port behind a config switch, default off; no secret committed; Terraform and secret only after the T-UR18 cost check says go | T-UR19, moved whole |
| T-UR32 | Setup-token service: single-use, invalidated when the first admin is created, never committed or logged; predicate "no users and no bootstrap admin configured" | T-UR21 service part |
| T-UR33 | Account delete rule: service refuses delete while any transaction, planned item or recurring rule references the account, and returns the reference counts; the current UI shows the refusal | T-UR23 service part |
| T-UR34 | Value inventory and gaps: every value the handoff displays mapped to the service or view-model field that produces it; missing fields added; export honours the current tab and filters | new (ADR-0147 §3) |
| T-UR35 | Release | new |

### 3. What stays in the migration

- Pages and routers: invite pages and actions, add user and one-time credential dialogs, user row menu (T-UR20); `/setup` page and route (T-UR21); drill default for the bootstrap admin and the setup token in workflow output (T-UR22, needs the `/setup` page); account delete dialogs (T-UR23).
- Removal of the inline promote routes (T-UR24), presentational value helpers (T-UR03) and chart geometry (T-UR12), by operator choice.
- Offline save handling, theme switch, export menu and credit-limit line (T-UR25, T-UR27, T-UR28): frontend.

### 4. Contract tests

Behaviour that changes in the precondition release (user edit guards, account delete rule) changes its contract tests there, with the requirement text already in `docs/requirements.md`. The migration then starts from that baseline, and the redesign rule "contract tests do not change" (requirements §10.3) holds unchanged for the migration.

## Consequences

- The redesign release carries no schema migration and no service behaviour change beyond page wiring; a rollback of it is a frontend rollback.
- The user edit guard bug (self-demotion with a second admin, email edit) is closed weeks earlier.
- Dormant invite and setup-token code sits in prod for the migration's duration. It is covered by tests and has no route; the invite table is empty.
- The migration waits for one more release cycle.
- Requirements F2.8 and §6.2 now name the precondition release for the server side and the redesign release for the dialogs and pages.

## Alternatives considered

- **Everything in the redesign release** (ADR-0134 as written). Rejected by the operator: one large release mixing schema, behaviour and the whole frontend.
- **Backend items on `ui/sourdough`, released with the frontend.** Same release risk; only separates review.
- **Also build old-chrome pages for invites and setup now.** Rejected: throwaway templates in a frontend that is about to be deleted, and new files under old-frontend paths (T-UR00 ledger).

## Amendments

- 2026-11-23: [ADR-0151](0151-designer-follow-up-answers-2026-11-23.md) §3: the designer follow-up answers arrived after v3.2.0; their four backend deltas land as T-UR36, the first code item on `ui/sourdough`, and ship with the redesign release. The only backend exception to "the migration is frontend work only".
