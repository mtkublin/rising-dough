# ADR-0057 — v2: Archived categories on existing recurring rules

- **Status**: Accepted
- **Date**: 2026-10-28
- **Supersedes/Amends**: Amends ADR-0048 (category color coding), extends ADR-0038 (recurring standalone lifecycle).
- **Related**: ADR-0022 (soft-delete audit), ADR-0051 (v2 IA), handoff `docs/application_redesign_handoff/docs/07-open-items.md`.

## Context

Mockups and handoff show categories can be archived from Settings · Categories. The handoff open item asks whether an archived category can still back an existing recurring rule. Two shapes were considered:

1. Block archive while any live recurring rule references the category.
2. Allow archive — the rule keeps running; UI treats the category pill as muted on the rule row; new rules cannot pick an archived category.

## Decision

**Allow archive. Rules continue to fire.** Archived categories remain valid foreign keys for already-live rules, recurring overrides, and historical transactions. New rule creation and the add-entry form filter archived categories out of the picker.

Repository invariants:

- `categories.archived_at` nullable column (soft-delete timestamp, consistent with ADR-0019 / ADR-0022 pattern — no new schema; reuses `deleted_at`).
- `services.categories.archive(category_id)` sets `deleted_at`; no cascade.
- `services.categories.list_active(…)` filters `deleted_at IS NULL`; existing readers for rules/transactions keep joining on `category_id` without filtering.
- `services.recurring.create_rule(...)` validates the category is active (not archived); raises `CategoryArchivedError` otherwise.
- `services.transactions.create(...)` similarly rejects archived categories at creation time.

UI treatment:

- Ledger · Recurring: archived source category pill rendered with `.pill--muted` and an "archived" micro-chip; row still fires.
- Settings · Categories: archived groups collapsed under "Archived" sub-section; Restore action soft-undeletes.
- Add-entry / Create-rule pickers: archived categories hidden; "Restore to use" copy in the empty-state when every option in a direction is archived.

## Rationale

Block-on-reference forces the operator to tear down an active income stream to clean up a stale label. The muted-but-live approach preserves history, matches ADR-0022's soft-delete philosophy, and keeps the UI honest: history always visible, future creation disallowed.

## Implementation checkpoints

- `tests/services/test_categories.py::test_archive_leaves_recurring_rule_live`
- `tests/services/test_recurring.py::test_create_rule_rejects_archived_category`
- `tests/services/test_transactions.py::test_create_rejects_archived_category`
- `tests/web/test_settings_categories.py::test_archived_group_renders_restore_affordance`
- `tests/web/test_ledger_recurring.py::test_archived_category_pill_renders_muted`

## Consequences

- One new error class (`CategoryArchivedError`) in `services.categories`.
- No migration (`deleted_at` already exists on `categories` per ADR-0022).
- `requirements.md` F1.6 unchanged; archive is an existing capability, this ADR pins its interaction surface.

## Addendum 2026-11-21: validation not implemented as written

The repository invariants above name `CategoryArchivedError`, `services.recurring.create_rule` and `services.transactions.create`; none of these exists. `services.categories.archive` sets `deleted_at` (no `archived_at` column), and neither the recurring save path nor the transaction save path rejects an archived category today. The rule "new rules cannot pick an archived category" is a requirement still open; enforcement is owned by the quality-audit remediation (Q-028, T-Q202 for recurring rules). Quality-audit finding Q-052.
