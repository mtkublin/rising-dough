# ADR-0152: Contract Tests Pin Behaviour, Not Dialog Transport

- **Status**: Accepted (orchestrator, 2026-11-25; operator to confirm at PR review)
- **Date**: 2026-11-25
- **Amends**: [ADR-0107](0107-sourdough-redesign-from-designer-handoff.md) (the "behaviour is pinned by the harness" guardrail in `docs/plans/ui-redesign/README.md`)
- **Related**: [ADR-0143](0143-htmx-event-and-error-flash-contract.md), [ADR-0120](0120-pre-commit-is-the-local-gate.md)
- **Tasks**: T-UR00 family, T-UR04e (dialog shell), T-UR13 (finding source)

## Context

The redesign plan says: "Behaviour is pinned by the harness. If a contract test needs to change, stop: that is a behaviour change and needs a requirement or ADR first." The dialog shell (`fragments/dialogs/dialog.html`, `web/dialogs.py`, UR04e) moves flows into one modal. Several contract assertions then fail although no user-visible behaviour changed. They pin transport markup. Examples found by UR13:

- `tests/contract/test_categories.py::test_new_form_targets_itself_and_resets` asserts `hx-target="#category-form"` and `data-reset-on-submit`. The shell targets `#modal-root` through `HX-Retarget` in `dialog_response`, and the macro emits no free form attributes.
- `tests/contract/test_settings.py::test_htmx_request_gets_drawer_fragment` asserts that an HX GET `/settings` returns the old slide-over drawer (`role=dialog` "Settings", `aria-modal`). The shell has no drawer, and `removal.md` deletes `settings/_drawer.html`.

Other contract tests pin real behaviour and must not move, for example `test_archive_204_with_undo_toast_and_audit` (status 204, undo toast in `HX-Trigger`, audit row) and `test_delete_unknown_or_foreign_is_a_noop` in `tests/contract/test_accounts.py` (200 no-op for an unknown or foreign id). Without a rule, each surface item stops and asks, or edits tests ad hoc.

## Decision

1. **Behaviour stays pinned and unchanged**: route, method, status code, response headers that carry behaviour (`HX-Trigger` events, toast payloads including undo, `HX-Refresh`, `HX-Redirect`, `Location`, `Retry-After`), persisted rows, audit rows, user scoping, validation outcomes and their messages, and the content a user reads.
2. **Transport markup may change** when a surface item moves that flow onto the dialog shell:
   - which element an HTMX request targets or swaps (`hx-target`, `hx-swap`, `HX-Retarget` / `HX-Reswap` to `#modal-root`);
   - self-targeting forms and reset-on-submit data attributes;
   - container element ids and roles that exist only for the old slide-over or drawer;
   - the shape of an HX fragment for a page GET (drawer vs new-shell fragment).
3. **Rules for such a change**:
   - It lands in the same item as the surface port.
   - The changed test keeps asserting the new transport exactly (for example `HX-Retarget` `#modal-root`, the dialog role and `aria-labelledby`). Deleting the assertion is not allowed.
   - The commit body lists each old -> new assertion.
   - The reviewer checks that no item from rule 1 changed.
4. **A behaviour pin that conflicts with the new UI** (for example a 204 that cannot close a dialog) keeps the behaviour. The dialog closes client-side through an `HX-Trigger` event handled by the shell's non-vendored script (`static/rd/js/app-toast.js`, ADR-0143). Changing the status is not the fix.
5. **Out of scope**: anything in rule 1. Example: the unknown or foreign account delete no-op (audit finding F5) stays as it is until the operator decides.

## Consequences

- Surface items no longer stop on transport assertions; the old -> new list in the commit body keeps the change reviewable.
- Behaviour changes still need a requirement or ADR first.
- The ADR-0120 gates are unchanged: no test is skipped or loosened, only re-pointed at the new transport.
