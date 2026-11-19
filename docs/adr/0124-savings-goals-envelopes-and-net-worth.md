# ADR-0124: Savings Goals — Envelope Allocations and Net-Worth Goals

- **Status**: Accepted
- **Date**: 2026-11-18
- **Relates to**: [ADR-0006](0006-multi-currency-model.md) (multi-currency), [ADR-0019](0019-soft-delete-and-audit-log.md) (soft delete + audit), [ADR-0021](0021-functional-style-no-oop.md) (functional-first), [ADR-0042](0042-forecast-budget-overlay.md) (forecast), [ADR-0043](0043-forecast-tab-monthly-horizon-and-table.md) (forecast horizon), [ADR-0048](0048-category-color-coding.md) (colour presets), [ADR-0051](0051-v2-information-architecture-rising-dough.md) (IA), [ADR-0056](0056-v2-inline-interactions-and-backend-additions.md) §3 (afford preview), [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) (per-user isolation), [ADR-0081](0081-v4-field-level-encryption-scope-and-query-model.md) (encrypted columns), [ADR-0125](0125-sourdough-starter-rules.md) (the starter built on top), [ADR-0126](0126-gamification-design-handoff.md) (UI source), requirements §12

## Context

- The app tracks accounts, transactions, budgets and a fortune forecast, but has no way to save *towards* something. §12 (2026-11-17) captured savings goals as the base for a gamification layer (ADR-0125), and as a finance feature on their own.
- Users save in different shapes. Some banks offer real sub-accounts per purpose; many users keep one savings pot for several purposes. Creating fake "sub-accounts" in the app to model one pot is a workaround abstraction we do not want: an account in the app mirrors a real account.
- Some goals are about the whole picture rather than one pot ("100 000 PLN net worth by May 2027"). `services.fortune.compute_fortune` already derives net worth (`net_base`: active accounts, liabilities subtracted, base currency).
- v4 (§7, ADR-0080/0081) encrypts amounts and names per user and runs aggregates in Python on decrypted rows during a live session. The feature lands after the redesign (§10); whether before or after v4 is not decided, so the schema must be v4-ready from day one.

## Decision

### 1. Two goal kinds

| Kind | Progress | Deadline |
|---|---|---|
| `envelope` | Σ live allocations (§2), converted to the goal currency | optional |
| `net_worth` | `compute_fortune(...).net_base`, converted to the goal currency | **required**, ≤ today + 60 months |

Goals are **strictly per user** (ADR-0061). No shared or household goals.

### 2. Envelope allocations (earmarks)

- An allocation earmarks part of a real account's balance for a goal. **Balances do not change.** No transaction is written.
- Data shape: a **dated event ledger** `goal_allocations(id, user_id, goal_id, account_id, op_date, amount, created_at, updated_at, deleted_at)`. A positive amount allocates; a negative amount releases (the one signed-amount exception besides reconciliation, ADR-0008; documented in the schema comment). Current allocation per `(goal, account)` = Σ live rows. Rows are editable and soft-deletable with audit, like ledger rows.
- One goal may draw from **several accounts** in different currencies. Only **asset** accounts host allocations; liability accounts are rejected (422).
- `free(account) = balance(account) − Σ live allocations on that account` (account currency).
- **Write-time invariant**: an allocate that would make `free < 0` is rejected (422, "Only X is free in <account>"). Releases beyond the goal's allocation on that account are rejected too.
- **Over-allocation after the fact** (spending drops the balance below the allocations): **flag, never auto-change**. Allocations stay as entered. The account shows "over-allocated by X"; affected goals show **unbacked**. The user releases manually. No proportional or priority shrink.
- No recurring or automatic allocations in this version (non-goal; revisit after use).

### 3. Currency

- A goal has its own currency (default: the user's base currency). Allocations are stored in the account's currency.
- Progress converts at the **latest cached FX rate** (today's value), the same way current aggregates do (ADR-0006, ADR-0095). Progress therefore moves with FX; this answers "do I have enough now".

### 4. Projection

- **Net worth**: read the existing fortune forecast (F5.2, ADR-0042 overlay on) at the deadline month. Show projected vs target, on track / behind, and the monthly gap. Deadline capped at 60 months (the forecast's max horizon, F5.4) so the projection always exists.
- **Envelope with deadline**: required per month = `remaining ÷ months left`. On track if the trailing 90-day net allocation pace meets it.
- **Envelope without deadline**: ETA from the trailing 90-day net allocation pace; "no recent saving" when the pace is ≤ 0.
- Pure functions in `domain`/`services`; no stored projections.

### 5. Lifecycle

- **Reached** is derived (`progress ≥ target`) and can be lost again if money is released or spent. The **first** time a goal is reached is persisted as `goals.first_reached_at` (needed for the shelf and the starter, ADR-0125).
- **Archive**: hides the goal. For an envelope with live allocations, archiving writes release events for the remainder (audited, one per account) so archived goals never earmark money; the dialog states the amount. Abandoning = archiving an unreached goal.
- Target, deadline, name, colour and note are editable (audited). Kind and currency are immutable after creation.
- No hard limit on the number of goals. Goals carry a manual `sort_order`.

### 6. Goal fields

`goals(id, user_id, kind, name, target_amount, currency, deadline NULL, color NULL, note NULL, sort_order, first_reached_at NULL, archived_at NULL, created_at, updated_at, deleted_at)`.

- `color` uses the category colour presets (ADR-0048). No icons.
- Name uniqueness among live goals per user via a blind index under v4 (`name_bidx`), mirroring accounts and categories.

### 7. Coupling with existing money math

- Balances, budget, forecast and analytics are **unchanged** by allocations.
- **Accounts** shows `allocated` and `free` per asset account once anything is allocated, plus the over-allocated flag.
- **Afford preview** (ADR-0056 §3): `services.today.afford` additionally warns when the amount exceeds the total free balance of asset accounts in base currency (today's FX). It is a warning only: left-per-day and the pace tag are computed as before.

### 8. Placement (IA)

- New **Plan → Goals** tab (`/plan?tab=goals` alongside budget, year, forecast, analytics); no new rail item (ADR-0051 unchanged).
- Compact goals card on `/today` (top 3 by `sort_order`).
- Allocated / free on `/accounts`.

### 9. Encryption (v4)

- Encrypted columns: `goals.name`, `goals.target_amount`, `goals.note`, `goal_allocations.amount`; `goals.name_bidx` blind index. Plaintext: ids, FKs, `kind`, `currency`, `color`, dates (`deadline`, `op_date`, `first_reached_at`, `archived_at`), `sort_order`, timestamps.
- If goals land **before** v4 Phase 3, these columns join the T-E08 expand migration, the T-E09 repository sweep and the T-E12 escrow backfill. If they land **after** v4, the tables are created with ciphertext columns from the start. Either way the repository API takes and returns plain domain values.

## Rationale

- Envelopes model one real pot with many purposes without inventing accounts that do not exist at the bank.
- A dated ledger (not a single editable number) gives history for the pace and ETA, clean events for the starter (ADR-0125), and the same edit/delete/audit semantics as the rest of the app.
- Rejecting impossible allocations at write time keeps "free" meaningful; flagging later shortfalls instead of auto-shrinking never changes user data silently.
- Reusing `compute_fortune` and the forecast keeps one definition of net worth and one projection engine.
- No coupling into budget or forecast keeps regression risk near zero; the afford warning is the one place where earmarked money matters for a spending decision.

## Consequences

- New tables `goals`, `goal_allocations`; new `services.goals`, repositories, a Plan tab, a Today card, Accounts additions, an afford warning branch.
- One more signed-amount column (`goal_allocations.amount`) to document beside reconciliation.
- v4 plan gains rows for the goal columns if goals ship first.
- UI is built only from the designer's handoff (ADR-0126).

## Alternatives considered

- **Linked whole accounts.** Rejected: only works when the user has a real sub-account per goal; otherwise it forces fake accounts.
- **Tagged contributions (goal_id on transactions).** Rejected: untagged moves, interest and reconciliations drift; touches the core transaction model.
- **Accounts + fixed split rules.** Rejected: envelope complexity in disguise.
- **Single current value per (goal, account).** Rejected: no history for pace, ETA or starter events.
- **Auto-shrink on over-allocation.** Rejected: silently changes user data.
- **Net worth over a user-chosen account subset.** Rejected for now: a second definition of net worth that diverges from the one on `/today`.
- **New top-level Goals rail item.** Rejected: changes ADR-0051's IA; Plan is the planning home.
