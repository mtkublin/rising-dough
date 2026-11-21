# Change request for the designer: 16 places where the app and the "rising dough" handoff disagree

> Task T-UT06. Status: **answered 2026-11-21**; operator decisions recorded below and in [ADR-0134](../../adr/0134-redesign-scope-decisions-from-the-designer-change-request.md). The Edit user follow-up was answered the same day (see the end of this file). The sections below are the original questions, unchanged.

## Why you are getting this

We are rebuilding the app's screens to match your "rising dough" handoff. Before starting, we ran a parity check: we went through the running app page by page and feature by feature, and compared it against every board in the handoff. The full comparison is in [parity.md](../ui-test-harness/parity.md). For most features the two sides line up. For 16 of them they do not:

- **Part A (9 items):** the app has a screen or feature, but the handoff has no board for it.
- **Part B (7 items):** the handoff has a board, but the app has no such feature today.

For every item we would like one answer from you. The IDs (SH13, ST10 and so on) are the row IDs from parity.md, so we can trace each answer back. Route paths are kept out of the text on purpose; they are in the appendix.

Screenshots: the app screenshots we already have live in `tests/visual/baselines/` (desktop, tablet and mobile for Today, Ledger, Plan, Accounts, Budget). Where a screen is not in there we say "screenshot on request" and will capture it for you.

---

## Part A: screens the app has, that the handoff has no board for (9)

For each one, the ask is the same: **draw a board, or confirm we drop it.**

### SH13. Export the Ledger as CSV or Parquet
- **Today:** the app can export transactions and planned items as a CSV or Parquet file. The export itself works, but the current Ledger screen has no visible button for it, so it is reachable only by typing the address.
- **Why it matters:** this is how the owner gets data out for a spreadsheet or backup. Without a button it is effectively hidden.
- **Screenshot:** on request (there is no UI to photograph).
- **Ask:** draw an export control in the Ledger (where, and what format choice looks like), or confirm we drop it from the product.

### TD10. Net-worth card on Today
- **Today:** Today shows a card with total net worth, the top account balances, an "All N accounts" link and a "Forecast" link.
- **Why it matters:** it is the first number the owner looks at and the quickest way into Accounts and the forecast.
- **Screenshot:** `tests/visual/baselines/desktop___today.png` (also tablet and mobile versions).
- **Ask:** draw it into the Today board, or confirm Today should not carry it.

### L11. Monthly cash-flow strip above Recurring
- **Today:** when you look at the Recurring view of the Ledger, a thin strip above the list summarises the month's money in, money out and the net.
- **Why it matters:** it gives the monthly picture without leaving the recurring list.
- **Screenshot:** the Ledger baselines are in `tests/visual/baselines/` (`desktop___ledger.png`, tablet, mobile); the strip is only visible in the Recurring view, so a dedicated screenshot is on request.
- **Ask:** draw the strip on the Recurring board, or confirm we drop it.

### L18. Credit-limit hint while entering a transaction
- **Today:** when you add a transaction on a credit-card or other liability account, a small hint appears in the form showing how much of the credit limit is left, before you save.
- **Why it matters:** it stops the owner from overspending a card without noticing. Your handoff shows the credit line only on the account row in Accounts, not in the entry form.
- **Screenshot:** on request.
- **Ask:** draw the hint into the transaction form (and its warning state when the limit is exceeded), or confirm we drop it.

### L23b. Inline "promote" row
- **Today:** to turn a planned or recurring item into a real transaction, the app can open a compact inline row in the list, where you confirm date and amount in place. There is also the dialog version, which your handoff does draw.
- **Why it matters:** the inline version is faster for a quick confirm. The handoff seems to have dropped it on purpose (its README, section 6, lists it as "no board").
- **Screenshot:** on request.
- **Ask:** please **confirm whether dropping it was intentional**. If yes, we use the dialog only. If no, draw the inline row. This is also open question 2 in [derived.md](derived.md).

### ST10. Forced password change after an admin reset
- **Today:** when an admin resets someone's password, that person is sent to a "Set a new password" page on their next sign-in and cannot reach anything else until they choose one.
- **Why it matters:** it is the only way a temporary password gets replaced; without it the temporary password would stay valid.
- **Screenshot:** on request.
- **Ask:** draw this screen (including its error states), or confirm we drop the forced change. Note this depends on your answer to ST15 and ST18.

### ST15. Add a user directly, with a one-time password
- **Today:** an admin adds a person by typing email, name and whether they are an admin. The app creates the account and shows a generated password once, in a toast, to hand to the person.
- **Why it matters:** this is the only way new users get in today. Your handoff draws an invitation by link instead (see ST16 in Part B).
- **Screenshot:** on request.
- **Ask:** draw it (the add form and the "shown once" password message), or confirm we drop it in favour of invites. See the questions under ST16.

### ST18. Reset a user's password
- **Today:** in the users list, an admin can reset someone's password; the app shows a new one-time password once.
- **Why it matters:** it is the recovery path for someone locked out.
- **Screenshot:** on request.
- **Ask:** draw it on the user row or in the edit-user overlay, or confirm we drop it (for example if recovery will be by a fresh invite instead).

### ST19. Delete a user
- **Today:** in the users list, an admin can delete a user.
- **Why it matters:** it is how access is removed when someone leaves.
- **Screenshot:** on request.
- **Ask:** draw it, including the confirmation step, or confirm we drop it.

---

## Part B: boards in the handoff that the app has no feature for (7)

Here the app has nothing to match your board, so building it is new product work. For each item, please tell us three things: is it meant for **the first release of the redesign or later**; are there **missing states** (errors, empty, mobile); and the specific questions listed.

### SH12. Theme switch (system, light, dark)
- **The board shows:** an Appearance control in Preferences with system, light and dark, remembered per browser.
- **The app does today:** it ships a single light theme and has no switch.
- **Questions:** First release or later? Does the dark theme need mobile and chart variants beyond what is drawn? Is "system" the default?

### AU07. First-run registration
- **The board shows:** a screen to create the very first account.
- **The app does today:** there is no self-registration. The first user is created during setup, before anyone sees a screen.
- **Questions:** First release or later? Is this meant for anyone who finds the address, or only the first visit on an empty app (and what happens on every later visit)? Which error states exist (email taken, weak password)?

### AU08 and AU09. Accept an invitation, and invitation expired
- **The boards show:** a page where an invited person sets their password from a link (AU08), and the page they see if the link has expired (AU09).
- **The app does today:** there are no invitations at all. Admins create users directly (ST15).
- **Questions:** First release or later? What should the expired page offer (ask for a new link, contact the admin)? Are there states for an already-used link or a wrong link? Is mobile drawn?

### ST16. Invite by email and role
- **The board shows:** in the users list, "create invite link" with an email and a role, and the list showing an "invited, expires" status.
- **The app does today:** no invite concept. Admins add users directly with a one-time password (ST15).
- **Questions:** First release or later? **Do invites replace the direct add (ST15) or sit beside it?** If they replace it, what is the recovery path when someone is locked out (ST18), and does the forced password change (ST10) go away? Can an admin revoke or resend an invite? Does the app send email, or does the admin copy the link by hand?

### AU14. Offline page
- **The board shows:** a page for when the app cannot be reached.
- **The app does today:** nothing. It is a local-first web app with no offline support, so the browser's own error page appears.
- **Questions:** First release or later? When exactly should it appear, and should it say anything about unsaved work?

### AC07. Delete account blocked while it has transactions
- **The board shows:** a dialog that refuses to delete an account that still has transactions.
- **The app does today:** delete is soft and unconditional. It asks nothing and removes the account (the data is kept internally and can be recovered).
- **Questions:** First release or later? Should the dialog offer a way forward (archive the account, move the transactions, view them)? Is the refusal also needed for accounts that only have planned items?

---

## Summary

| ID | Title | Part | The ask | Designer answer |
|---|---|---|---|---|
| SH13 | Export CSV / Parquet from the Ledger | A | Draw a board, or confirm drop | Draw. `export` menu beside the Ledger tabs (actual, planned): csv or parquet, current tab and filters; none on Recurring; kept on phone, wrapped under the tabs. |
| TD10 | Net-worth card on Today | A | Draw a board, or confirm drop | Already drawn on the Today board (total, assets and liabilities, all N accounts, forecast); per-account list dropped on purpose. Our parity row was wrong. |
| L11 | Monthly cash-flow strip above Recurring | A | Draw a board, or confirm drop | Covered by the Recurring hero (out, in, net per month); no separate strip. |
| L18 | Credit-limit hint while entering a transaction | A | Draw a board, or confirm drop | Draw. One line under the account in new entry / edit / phone sheet: left of limit, left after this entry; over limit turns pink with a warning mark (`role=alert`), saving allowed. |
| L23b | Inline promote row | A | Confirm the drop was intentional, or draw it | Intentional drop; promote is dialog-only. |
| ST10 | Forced password change after admin reset | A | Draw a board, or confirm drop | Keep. "Set a new password" (desktop, error, phone) after sign-in for users added directly or reset; nothing else reachable; sign out is the only way out. |
| ST15 | Add a user directly, one-time password shown once | A | Draw a board, or confirm drop | Keep beside invites. Add user dialog (email, name, member/admin); one-time credential shown once in a dialog, not a toast; duplicate email refused. |
| ST18 | Reset a user's password | A | Draw a board, or confirm drop | Keep. Row menu, reset, confirm, one-time credential dialog, forced change. |
| ST19 | Delete a user | A | Draw a board, or confirm drop | Keep. Row menu, delete user, destructive confirm; their ledger entries stay. |
| SH12 | Theme switch (system, light, dark) | B | First release or later; missing states | Part of the redesign release (ships only when the whole migration is done); default system; full light set drawn. |
| AU07 | First-run registration | B | First release or later; missing states | First visit only, while the app has no users; the account becomes admin; once any user exists it redirects to sign in. Errors: invalid email, under 12 characters, mismatch. |
| AU08 | Accept an invitation | B | First release or later; missing states; invite vs direct add | Same release; email fixed by the invite; the person adds name and credential. |
| AU09 | Invitation expired | B | First release or later; missing states | Expired page asks to get an admin to resend; also already-used and invalid-link states. |
| ST16 | Invite by email and role | B | First release or later; replace or sit beside direct add (ST15) | Keep beside direct add; the app sends the email; pending row menu: copy link, resend (new link and expiry), revoke (confirm). Reset stays for recovery; forced change stays for direct adds and resets. |
| AU14 | Offline page | B | First release or later; missing states | Same release; shown when a page load or save cannot reach the server; an open dialog keeps what was typed. |
| AC07 | Delete account blocked while it has transactions | B | First release or later; missing states | Same release; refuse delete while any transaction, planned or recurring item points at the account; dialog links to them (view N transactions / view recurring rules); otherwise final confirm. New state: blocked by recurring only. |

---

## Appendix: where each item lives (from parity.md)

| ID | App route(s) | Handoff page |
|---|---|---|
| SH12 | none | `settings/preferences` |
| SH13 | `GET /transactions/export`, `GET /planned/export` | none |
| AU07 | none (`GET /auth/register` is an unrelated legacy redirect, row AU15) | `auth/register` |
| AU08 | none | `auth/invite` |
| AU09 | none | `auth/invite--expired` |
| AU14 | none | `errors/offline` |
| TD10 | `GET /today` | none |
| L11 | `GET /ledger` (Recurring view) | none |
| L18 | `GET /transactions/_limit_preview` | none |
| L23b | `GET /planned/{planned_id}/promote/inline`, `GET /recurring/{rule_id}/promote/inline` | none (dialog variants: `overlays/promote--planned`, row L23) |
| AC07 | `POST /accounts/{account_id}/delete` | `overlays/delete-account--blocked` |
| ST10 | `GET /settings/password`, `POST /settings/password` | none |
| ST15 | `POST /settings/users` | none |
| ST16 | none | `settings/users` ("create invite link") |
| ST18 | `POST /settings/users/{user_id}/reset-password` | none |
| ST19 | `POST /settings/users/{user_id}/delete` | none |

Handoff reference screenshots for the Part B boards (frozen handoff, 1440 wide, light) are in `tests/visual/reference/`: `auth/register`, `auth/invite`, `auth/invite--expired`, `errors/offline`, `settings/preferences`, `settings/users`. Overlay boards (such as `overlays/delete-account--blocked`) are rendered locally with `just visual-reference` but not committed.

---

## Operator decisions (2026-11-21)

Recorded in [ADR-0134](../../adr/0134-redesign-scope-decisions-from-the-designer-change-request.md).

1. **ST16 invite email**: real email sending behind a config switch (default off). Before enabling, the operator evaluates the added cost (mail provider, Terraform, secret) as its own task. If too high, the switch stays off, the code is kept, and invites use copy-link only.
2. **AU14**: keep all offline pages and states; the service worker is deferred (failed full page loads keep the browser error until then). The save-failure path (dialog keeps typed input, shows the offline state) is in the redesign release.
3. **AC07**: adopt the designer's rule (requirements change; today delete is soft and unconditional).
4. **L23b**: drop the inline promote row; remove `GET /planned/{planned_id}/promote/inline` and `GET /recurring/{rule_id}/promote/inline`; amend the promote-in-place requirement.
5. **AU07**: first-run page on a new path (`/setup`), only while there are no users and no bootstrap admin is configured, and only with a single-use setup token (404 otherwise). Drills stop bootstrapping an admin by default (capability kept, off by default for drills); on explore drills the operator creates the admin through `/setup` using the token surfaced in the drill workflow output. Prod keeps its users.
6. **SH13**: export stays on phone.
7. The Feedback handoff, Goals, Gamification with Starter and App-Walkthrough are separate packages, implemented after the redesign migration. The command palette stays during the redesign.
8. **Edit user**: asked the designer; kept, see ADR-0134 §11 (below).

## Follow-up for the designer (2026-11-21)

**Edit user dialog.** The Edit user dialog is gone from Settings, Users (the handoff page `overlays/edit-user` was removed). Should the user row menu get an "edit name / role" entry, or is editing intentionally dropped (changing a role would then mean delete and re-add)? Until you answer, the app has no way to edit an existing user's name or role.

**Answered 2026-11-21 (ST17).** "Keep editing; leaving it out was an oversight. Drawn: edit user is now the first item in the member row menu and opens an Edit user dialog with name and member/admin; the email stays fixed. An admin's own row has no menu, so they can't demote or delete themselves and there is always at least one admin." Delivered as a delta package (`pages/overlays/edit-user.html`, Users page and overlays, CSS move), vendored in T-UT06-EDITUSER (ADR-0107). Decision: ADR-0134 §11.
