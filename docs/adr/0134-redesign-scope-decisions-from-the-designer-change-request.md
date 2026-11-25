# ADR-0134: Redesign scope decisions from the T-UT06 designer change request

- **Status**: Accepted (amended by ADR-0148)
- **Date**: 2026-11-21
- **Relates to**: [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) (admin bootstrap, users), [ADR-0099](0099-release-and-environment-policy.md) (drills), [ADR-0107](0107-sourdough-redesign-from-designer-handoff.md) (redesign), [ADR-0113](0113-csp-compatible-frontend.md) and [ADR-0123](0123-frontend-stays-server-rendered-no-spa-framework.md) (no SPA, CSP, service worker deferral), [ADR-0106](0106-ui-behaviour-test-harness.md) (parity inventory)

## Context

- The parity inventory (T-UT05) found 16 places where the app and the handoff disagree. They were sent to the designer as [designer-change-request.md](../plans/ui-redesign/designer-change-request.md) (T-UT06). The designer answered all 16 on 2026-11-21; the operator then decided the product questions the answers raised.
- The release rule of ADR-0107 §8 holds: the redesign ships once, when the whole migration is done. "Same release" below means that release.
- Designer answers are summarised in the change request. This ADR records only decisions that change scope, requirements or architecture.

## Decisions

### 1. Invite email is real, behind a config switch, after a cost check (ST16)

- Invites are sent by email by the app. Sending sits behind a config switch (default off).
- Before the switch is enabled anywhere, the operator evaluates the added cost (mail provider, Terraform, secret). That evaluation is its own task and comes before the email task.
- If the cost is too high, the switch stays off. The code is kept, not removed, and invites use the copy-link flow only.
- Invites sit beside the direct add (admin types email, name, role; one-time credential shown once). Reset and the forced change stay for recovery, direct adds and resets (ADR-0061 §3 keeps the forced change).

### 2. Accepted as drawn, no app decision beyond building it

- TD10: the Today board already carries the net-worth card (total, assets and liabilities, "all N accounts", "forecast"); only the per-account list was dropped. Parity row corrected.
- L11: the monthly strip is dropped; the Recurring hero shows out, in and net per month.
- L18: credit-limit hint under the account in new entry, edit and the phone sheet (left of limit, left after this entry); over limit turns pink with a warning mark (`role=alert`), saving stays allowed.
- ST10, ST15, ST18, ST19: kept and drawn (see §10).

### 3. Account delete is blocked while anything points at it (AC07)

- Adopt the designer's rule: deleting an account is refused while any transaction, planned or recurring item references it. The refusal dialog links to them (view N transactions, view recurring rules); otherwise a final confirm.
- This is a requirement change: today delete is soft and unconditional. New state: blocked by recurring only.

### 4. Offline (AU14): states kept, service worker deferred

- All offline pages and states are kept in the redesign.
- No service worker in the redesign (ADR-0123, ADR-0113 stay as written): a failed full page load keeps showing the browser's own error page until a later ADR adds one.
- In the release: the save-failure path. When a page load via HTMX or a save cannot reach the server, an open dialog keeps what was typed and shows the offline state.

### 5. Inline promote is dropped (L23b)

- Promote is dialog-only. `GET /planned/{planned_id}/promote/inline` and `GET /recurring/{rule_id}/promote/inline` are removed in the redesign work, with their templates and UI-map names. The requirements line "promote-in-place" (§5.1) is amended.
- Closes open question 2 in `derived.md`.

### 6. Export stays on phone (SH13)

- An `export` menu sits beside the Ledger tabs (actual, planned): csv or parquet, current tab and filters. Recurring has none. It is kept on phone, wrapped under the tabs.

### 7. Other packages stay out of the redesign

- The Feedback handoff, Goals, Gamification with Starter and the App-Walkthrough are separate packages, implemented after the redesign migration.
- The command palette stays during the redesign.

### 8. Theme switch ships with the redesign (SH12)

- Light and dark with system, light and dark choice in Preferences; default system; the full light set is drawn. It ships in the redesign release. Server-side theme persistence stays a non-goal (per browser).

### 9. First-run setup on a new path; drills stop bootstrapping an admin (AU07)

- A first-run page at a new path (working name `/setup`; `/auth/register*` belongs to passkey registration). Reachable only on the first visit while the app has no users and no bootstrap admin is configured; the account becomes admin; once any user exists it redirects to sign in. Errors: invalid email, credential under 12 characters, mismatch.
- **One-time setup token** (operator, 2026-11-21): the setup page additionally requires a one-time token. On drill deploys the token is generated per deploy and surfaced in the drill workflow output (job summary, or the explore-drill URL as `/setup?token=...`, ADR-0099); it is single-use, invalidated once the first admin is created, never committed and never written to app logs. Without a valid token the page returns 404 (no oracle). Prod is unaffected (it has users).
- The bootstrap admin capability of ADR-0061 §3 stays (`BUDGET_PLANNER_ADMIN_EMAIL`, Terraform var `admin_email`) but is **off by default for drill deploys** (ADR-0099), so on explore drills the operator creates the admin through the setup page (no SSH for temporary credentials). Prod keeps its existing users; prod bootstrap behaviour is unchanged.

### 10. Users and invites (ST10, ST15, ST16, ST18, ST19, AU08, AU09)

- Invite page (AU08): email fixed by the invite; the person adds name and credential. Invite link states: expired (asks to get an admin to resend), already used, invalid.
- Pending invite row menu: copy link, resend (new link and expiry), revoke (confirm).
- Add user dialog: email, name, member or admin; one-time credential shown once in a dialog (not a toast); duplicate email refused.
- User row menu: reset (confirm, one-time credential dialog, forced change), delete (destructive confirm; the user's ledger entries stay).
- Forced change page (ST10): after sign-in for users added directly or reset; nothing else is reachable; sign out is the only way out.
- Edit user: see §11 (ST17). The first handoff dropped it; the designer restored it in a delta package.

### 11. Edit user is kept (ST17)

- The designer's answer (2026-11-21): keep editing, leaving it out was an oversight. `overlays/edit-user` is drawn: an Edit user dialog (460px) with name and member or admin; the **email is fixed and read-only**.
- User row menu order: edit user, reset password, delete user. An admin's own row has **no menu**, so an admin cannot demote or delete themselves and there is always at least one admin.
- The app enforces this server side, not only by hiding the menu (T-UR20): the edit route refuses an actor editing their own role to member, refuses demoting the last admin, ignores or refuses an email change; delete keeps refusing self and last admin (ADR-0073 §3, §4). Today `services/users.edit_user` allows self-demotion while a second admin exists and still edits the email; T-UR20 closes both.
- Requirement: `docs/requirements.md` §6.2 user admin. Harness: parity row ST17 resolved with `overlays/edit-user`.

## Consequences

- Requirements amended: F1.4 (export control), F2.1a (credit-limit hint), account delete rule (new F2.8), §6.2 users and bootstrap (invites, email switch, first-run page), §6.2 admin bootstrap (drill default, setup token), §5.1 promote-in-place, §10.1 (offline, theme, users).
- New redesign tasks T-UR18..T-UR28 in [tasks.md](../plans/ui-redesign/tasks.md). They land in the redesign release; none is implemented by this ADR.
- Quality-audit allowlists, canonical modules and guards are unaffected until those tasks land.

## Amendments

- 2026-11-22: [ADR-0148](0148-redesign-backend-preconditions-released-first.md): the server-side parts of §1, §3, §9, §10 and §11 (invite data layer and email port, setup-token service, account delete rule, user edit guards) and the fields the handoff needs ship in a precondition release before the migration (T-UR29..T-UR35). Pages, dialogs and the routes rendering them stay in the redesign release.
- 2026-11-23: [ADR-0151](0151-designer-follow-up-answers-2026-11-23.md): designer answers to the seven Phase P follow-up questions (afford, edit preview, category counts and picker, re-auth limit, device label, spent period, forecast start); four backend deltas land as T-UR36 on `ui/sourdough`.

- 2026-11-25 (operator QA Q9, T-UR18): invite email is NO-GO for v1 (§1, §10). `BUDGET_INVITE_EMAIL_ENABLED` stays off, no mail provider, Terraform or secret is added, and admins copy the invite link by hand from the Users page. The mail port, the no-op adapter and the switch code stay (T-UR31), so a later go needs only configuration plus an ADR. Decision source: [operator decisions](../plans/ui-redesign/operator-decisions-2026-11-25.md).
