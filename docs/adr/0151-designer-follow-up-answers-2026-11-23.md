# ADR-0151: Designer Follow-up Answers (2026-11-23) and Where Their Backend Deltas Land

- **Status**: Accepted (implementation pending, T-UR36)
- **Date**: 2026-11-23
- **Amends**: [ADR-0148](0148-redesign-backend-preconditions-released-first.md) ("the migration is frontend work only"); [ADR-0134](0134-redesign-scope-decisions-from-the-designer-change-request.md) (adds the follow-up answers)
- **Relates to**: [ADR-0147](0147-handoff-parity-ci-rendered-references-and-data-overlay.md) (value inventory, data overlay), [ADR-0008](0008-transaction-amount-sign-and-direction.md) and [ADR-0048](0048-category-color-coding.md) (category direction immutable), [ADR-0025](0025-user-preferences-and-income-anchor.md) (pay-period window), [ADR-0139](0139-canonical-fx-converter-cache-only-one-missing-rate-policy.md) (fortune converter), [ADR-0106](0106-ui-behaviour-test-harness.md) (contract tests)

## Context

While building the Phase P data (T-UR34), seven board values could not be reproduced from the boards' own data or had two readings. The orchestrator picked an option for each and asked the designer (T-UR34n, `docs/plans/ui-redesign/designer-change-request.md`, follow-up 2026-11-23). The designer answered on 2026-11-23: three agreed, four changed. v3.2.0 (Phase P) is already live, so the four changes cannot ride the precondition release.

The designer also wrote "board updated" for items 1, 3 and 7. The operator decided (2026-11-23) not to vendor updated boards: the vendored handoff stays as is, and the data overlay (ADR-0147 §4) corrects those values.

## Decision

### 1. Confirmed as built (no code change)

- **Today afford "over"** = entry minus what is left (left floored at 0), never below 0; the board's "−14.20 per day · 114.20 over" becomes "−57.15 per day · 400.07 over" through the overlay (T-UR34e).
- **Credit-limit preview on edit**: the entry being edited is left out of "left of limit before this entry"; "after" = "before" minus the new amount (T-UR34d).
- **Re-auth attempts left**: limit 5 per minute, counted down including the failed attempt just made; shown only on the password re-check screen, not for passkeys, not on sign-in (T-UR34i).

### 2. Changed by the designer (T-UR36)

- **Category usage counts** (T-UR34g): the edit dialog line counts live transactions, live planned items and live recurring rules that reference the category, e.g. "↓ expense · locked by 41 entries · 2 planned · 1 rule"; the archive dialog text uses the same counts. Parts at zero are omitted; with no references at all the line is just the direction ("↓ expense"). Soft-deleted rows do not count (same rule as F2.8, T-UR33).
- **Direction stays immutable** after create regardless of references (operator 2026-11-23; ADR-0008, ADR-0048 unchanged). "Locked by" is a reason shown to the user, not a rule that unlocks at zero.
- **Reconciliation is system-only in the category picker**: not in "recent", not in search results, not counted in "search all N categories". Transit is unaffected (the designer named Reconciliation only). The reconcile flow (F2.5) keeps choosing its category as today.
- **Session device label** (T-UR34h): show the part that is known: "Firefox · macOS", "Unknown browser · macOS", "Firefox · unknown system"; "Unknown device" only when neither is known.
- **Ledger "spent this period"** (T-UR34c): the pay-period window used by Budget and Today (e.g. 7 Oct → 7 Nov), resolved exactly as Budget and Today resolve it (`services/budget.resolve_period_start`, `domain/periods.fiscal_window`), not `month_bounds` of the calendar month. The label stays "spent this period".
- **Forecast "+X over N months"** (T-UR34j): X starts from today's net worth as on Accounts (`services/fortune.compute_fortune` `net_base`, same converter) and ends at the projected end balance of the last month shown; N = months shown. The NOW figure of the summary strip is the same today's net worth.

### 3. Where the deltas land

The four changes are one backend task, **T-UR36**, the first code item on `ui/sourdough`, before T-UR00b builds the seed and overlay. It changes the services and view models above and their contract tests (requirements amended first), so every surface task starts from the final values. It ships with the redesign release; no separate precondition release. This is the only backend exception to ADR-0148's "migration is frontend work only"; T-UR34c2 (already moved to the frontend phase) is unchanged.

## Consequences

- Requirements amended: F1.6 (category usage counts, picker), §10.1 (follow-up values), §10.3 (T-UR36 exception).
- Overlay candidates (value-inventory §5) gain the afford figures (row 9), the category count (row 12, Reconciliation out of N) and the edit preview (row 19, confirmed); T-UR00b adds rows for the forecast delta and the category count text.
- Contract tests for spent, forecast summary, device label and category usage change in T-UR36, not in surface tasks.

## Amendments

- None yet.
