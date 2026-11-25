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
