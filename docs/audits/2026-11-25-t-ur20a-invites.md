# Frontend visual audit: T-UR20a invites UI

- Item: UR20a (T-UR20 slice a), branch `wi/ui/sourdough/UR20a`, audited at head `f74ed650`.
- Tool: `frontend-visual-audit` skill (Playwright chromium, `/opt/pw-browsers/chromium`), own server on 127.0.0.1:8765, scratch copy of `data/demo.sqlite` migrated to head (never `data/budget.sqlite`). Admin `admin@local.test` set via `set-password --db=<scratch>`. Invites aged/used via SQL on the scratch copy only.
- Screenshots (viewed): `/tmp/fe-audit-ur20a/<viewport>__<state>.png`, plus handoff references `/tmp/fe-audit-ur20a/<viewport>__handoff_*.png` (`auth/invite`, `auth/invite--expired`, `overlays/invite-user`, `--error`, `revoke-invite`). Scripted checks: `/tmp/fe-audit-ur20a/result-{1440,1024,375}.json` (55 behaviour checks per viewport, all passing).

## Routes x viewports and diagnostics

Counts are summed over the captured states of the route at that viewport (horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures).

| Route (states captured) | Viewport | hScroll | overflowing | dupIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| `/settings/users` (19 states: list, create dialog, 422 empty/invalid/existing/pending-dup, link dialog, row menu, resend dialog, revoke dialog, 409/404 flashes, forced 500s) | 1440 | 0 | 0 | 0 | 0 (+10 browser "Failed to load resource" lines for the deliberate 422/409/404/500) | 0 |
| same | 1024 | 0 | 0 | 0 | 0 (+10 expected) | 0 |
| same | 375 | 0 | 57 (all `a.rd-tabs__tab`, the settings tab strip, contained scroller, see F2) | 0 | 0 (+10 expected) | 0 |
| `/invite/{token}` (10 states: AU08 pending, 422 short password, 422 mismatch, 429, AU09 expired / used / revoked / unknown) | 1440 | 0 | 0 | 0 | 0 (+100 expected 422/429 from the rate-limit loop) | 0 |
| same | 1024 | 0 | 0 | 0 | 0 (+100 expected) | 0 |
| same | 375 | 0 | 0 | 0 | 0 (+100 expected) | 0 |
| `/today` (post-accept 303 landing, not in scope, smoke only) | 1440 / 1024 / 375 | 0 | 0 / 0 / 1 (`pre.rd-hero__loaf`, hero art, not touched by this item) | 0 | 0 | 0 |

"Expected" console lines are Chromium's automatic `Failed to load resource ... 4xx/500` for requests the audit made fail on purpose; no JS error or `pageerror` occurred.

## Compared with the handoff

- AU08 (`auth/invite`): matches at 1440 (caption "invited by", read-only email, name, password with "12+ characters", confirm, `[ create account ]`). Name field is autofocused.
- AU09 states (expired, used, revoked, unknown): alert plus "back to sign in", no form, same page for all invalid kinds.
- Create dialog differs from handoff `overlays/invite-user` by design (Q9, no email): title "create invite", button `[ create invite ]` instead of "invite by email" / `[ send invite ]`; header button is "+ create invite" (no "+ add user", that is T-UR20b). Link dialog shows a read-only link, no copy control.
- Users table invite rows: `✉ invited · expires 02 DEC`, `✉ invite expired · 22 NOV`, row menu = resend invite / revoke invite / cancel (no copy link). 02 DEC = created + 7 days.

## Step 3b (behaviour contract)

1. Swap targets: every `hx-target` on the audited pages matched exactly one element (`#modal-root`) in all 29 captured states.
2. Failing saves visible: create invite empty / invalid / existing user / pending duplicate -> 422 dialog re-rendered with summary and `▲` message under email (exact texts as in the brief); resend/revoke on used invite -> 409 flash "This invite was already used or revoked. Create a new one."; unknown id -> 404 flash "Invite not found"; accept short password -> 422 under password; mismatch -> "▲ The two passwords do not match." under confirm, name kept, both passwords empty; 429 alert at the 101st attempt (login-IP hourly rule). Forced 500 on create and on resend (route fulfilled with 500) -> visible "Something went wrong on our side. Try again." banner. Success: revoke removes the row with flash "Revoked the invite for <email>."; accept 303 -> `/today`.
3. Templates: `rg` over the touched templates found no `float`, `/ 100`, `* 100`, `set` blocks, or arithmetic.
4. Money formatting: no money rendered by these templates (n/a).
5. Rendered numbers: the only derived values are dates; "expires 02 DEC" equals created + 7 days (`INVITE_LIFETIME`), "expired 22 NOV" equals the aged `expires_at`.
6. IDs and listeners: no duplicate ids after any swap (diagnostic re-run after each HTMX response). The one emitted event used here, `dialog-close` (409/404 flashes), has a listener (the dialog closed, flash visible).
7. Scratch data only.

Result: ok.

## Findings

- F1 (A11y/visual, low): the 409/404 error flash (`partials/_flash.html`, `.flash.flash-error`) renders as plain unstyled text at the top-left of the page in the rd shell at all widths (no border, tone or `▲`), unlike the rd toast used for the success flash and the rd banner of the 500 case. The message is visible and in an `role=alert` region, so the contract holds; the styling is the shared legacy flash, also used by the existing user routes (`users_admin.conflict_message`). Screenshot: `/tmp/fe-audit-ur20a/1440__flash-409-resend.png`. Triage: shared component, restyle outside this item (suggest rd toast/alert for `flash-error`).
- F2 (pre-existing, informational): at 375 the settings tab strip `a.rd-tabs__tab` overflows its container (contained horizontal scroll; the document does not scroll, `horizontalScroll` false). Not touched by this change (no CSS in the diff, `users-table.html` is the only shared template edited); same on `<MAIN>` settings pages by construction.
- F3 (note): the invite link base is the configured public base URL (`http://localhost:8000/...` on the scratch run); it is not derived from the request host.

No blocking findings.

## Re-audit after F1 (head 5bcbb492)

F1 fix verified: the 404/409 flashes on `/settings/users` (invite routes and the existing users routes) now render through `fragments/flash/error.html` into `#flash-region-assertive`. Own server on port 8791, scratch copy of `data/demo.sqlite` (migrated; admin set with `set-password`); never `data/budget.sqlite`. Forced via real `htmx.ajax` calls from the loaded page (stale revoked invite revoked from a second page; unknown ids; self-delete; self-demote). Screenshots: `/tmp/fe-audit-ur20a/re/<width>__<state>.png`; viewed `1440__409-resend.png`, `375__users-409-demote-self.png`, `375__create-dialog.png`, `1024__invite-unknown.png`.

| State (route `/settings/users`) | Result at 1440 / 1024 / 375 |
|---|---|
| resend revoked invite -> 409 | `rd-flash rd-flash--error`, "▲ This invite was already used or revoked. Create a new one.", Dismiss (x) button; below the header, inside the page container (x 80/24/16, widths 1280/976/343) |
| revoke revoked invite -> 409 | same text and styling |
| resend / revoke unknown id -> 404 | `rd-flash rd-flash--error`, "▲ Invite not found" |
| delete self -> 409 | styled, "▲ You can't remove your own account. Ask another admin." |
| demote last admin (self) -> 409 | styled, "▲ Can't remove admin rights from the last admin. Promote another user first." |
| delete unknown user -> 404 | styled, "▲ User not found" |
| Dismiss click | flash removed (0 left) |

Diagnostics for the audited states (users page before, create dialog, link dialog, six error flashes, after, invite landing AU08 with a real link, AU09 invalid link): horizontalScroll=0, overflowingElements=0 (at 375 only the pre-existing contained `a.rd-tabs__tab` strip, F2, same as before, document does not scroll), duplicateIds=0, consoleErrors=0 apart from Chromium's automatic `Failed to load resource 404/409` lines for the deliberately failing requests (no JS error, no pageerror), requestFailures=0. `#flash-region-assertive` exists exactly once in every state; legacy `.flash.flash-error` count 0.

Step 3b: failing saves visible (409/404 above, styled, dismissible); no template changes since the first audit; swap targets unchanged. Regression glance: create-invite dialog and the link dialog render as before; AU08 (invite landing, caption "invited by admin@local.test", form) and AU09 (invalid link alert) unchanged at 1440/1024/375.

F1: resolved. No new findings.
