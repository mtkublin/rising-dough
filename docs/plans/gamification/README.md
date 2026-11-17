# Savings goals + sourdough starter (gamification)

> **Status**: idea, not scheduled. No ADR, no tasks yet. Captured 2026-11-17.
> **Requirements**: [`docs/requirements.md` §12](../../requirements.md#12-savings-goals--sourdough-starter-idea-added-2026-11-17).
> **Next step**: grill the open questions below, then write the ADRs and `tasks.md`.

## Idea

A sourdough-starter character, Tamagotchi-style, that the user "feeds" by:

- completing one-time setup milestones (first account, first recurring payment, …);
- keeping good habits (logging regularly, reconciling);
- saving towards goals. The app has no goal-setting mechanism yet.

It fits the product: the app is called *Rising Dough* and the redesign is sourdough-themed (§10). A starter has to be fed regularly or it goes flat, which is the habit we want users to build.

## When

After the sourdough redesign (§10) ships. §10.4 rules out new features during the migration. The character's art comes from the redesign's design system.

```
redesign ─ (v4 Phase 2) ─ savings goals ─ starter
```

The timing against v4 Phase 2 is open (see the constraints below).

## Shape: two features, goals first

1. **Savings goals.** This is useful as a finance feature on its own: target amount, deadline, linked account(s), progress, and a projection to the deadline.
2. **Starter.** A layer on top that reacts to goal progress and a few habit signals.

Without goals, the starter can only react to setup milestones and logins, so the novelty wears off quickly. Ship goals first.

## Design principles

- **Reward the right behaviour.** "Log payments often" invites fake or split entries. Reward consistency (activity on N distinct days a week), reconciliations that match the real balance, and goal progress. Never reward more spending or more transactions.
- **No death, no guilt.** Punishment backfires with money: people who feel bad about their finances stop opening the app. A neglected starter goes *dormant* (flat, sleepy jar) and revives after one feed.
- **One-time milestones vs ongoing health.** Setup milestones fire once. The ongoing loop is saving and logging regularly, so the starter is never "complete" after the first week.
- **Opt-out.** A preference to hide the starter. Goals stay.

## Architecture notes

- **Derived, not stored.** The starter's state is computed by a pure function, e.g. `starter_state(goals, activity, milestones, today) -> StarterState`, in line with ADR-0021 (functional-first). This means no backfill for existing users, no drift, and soft-deletes and corrections show up automatically.
- **Only unlocked milestones are persisted** (enum + timestamp, plaintext), so deleting the first account does not revoke the milestone. Soft delete + audit log per ADR-0019.
- **v4 encryption constrains the design (ADR-0080, ADR-0081).** Amounts are encrypted, and aggregates run in Python on decrypted rows while a session is live. So there is no background job computing hunger or goal progress while the user is offline: everything is computed at render time from plaintext dates and timestamps, plus amounts decrypted in-session. Goal target amounts and names join the encrypted-column list in §7.2. Design the goals schema for this from day one, whether it lands before or after v4 Phase 2.
- **Multi-user (ADR-0061):** goals, milestones and the starter preference are per user.
- **Multi-currency (ADR-0006):** a goal has its own currency. Progress across accounts in other currencies converts at historical FX rates, the same way the existing aggregates do.
- **Art and motion.** Starter states (dormant, bubbly, rising, overflowing) are drawn by the designer within the sourdough design system. Animate only transform and opacity, and respect `prefers-reduced-motion`. Stay inside the §10.2 JS/CSS budgets.

## Open questions

1. What exactly counts as a "feed"? List the milestones and habit signals, with their weights.
2. How fast does the starter decay, and what thresholds trigger dormancy?
3. Goals: one account per goal, several accounts, or a virtual envelope within an account?
4. Goal progress: account-balance delta since the goal was created, or explicit contributions (transfers tagged to the goal)?
5. Multi-currency goals: does the goal currency have to match the linked accounts?
6. Is there a level or progression system (bread types, jar sizes), or just a health state?
7. Where does the starter appear: `/today` only, or in the global chrome?
8. Timing against v4 Phase 2: build goals before it (and encrypt them at Phase 2) or after it?

## Docs to write when scheduled

- ADR: savings goals data model (schema, progress semantics, encryption columns, FX).
- ADR: starter rules (feed signals, decay, milestones, derived-state function, opt-out).
- `docs/requirements.md` §12 promoted from idea to scope; `tasks.md` in this folder.
