# Installable Web App (PWA) — Tasks

> Plan: [README.md](README.md). Decision: [ADR-0151](../../adr/0151-installable-pwa-as-the-mobile-app.md). Requirements: [§16](../../requirements.md#16-installable-web-app-pwa-added-2026-11-27).
> Legend: `[P]` parallel-safe, `[S]` sequential, `→ T-PWAxx` depends on upstream task.

---

### T-PWA01 [P] Manifest, icons and head tags → PR #54 merged
- **Deliverables**: `GET /manifest.webmanifest` (public, `application/manifest+json`, fields per ADR-0151 §2); icon set under `static/rd/icons/` (192, 512, 512 maskable, 180 apple-touch) generated once from the redesign mark; base layout head links the manifest, icons, both `theme-color` metas and the iOS tags.
- **Acceptance**: the manifest body equals the ADR-0151 §2 fields; Chrome DevTools "Application → Manifest" shows no errors; the maskable icon passes the safe-zone check.
- **Validation**: unit test asserting the manifest JSON and content type; `frontend-visual-audit` for the head change (no console errors, no failed requests).

### T-PWA02 [S] Service worker and offline page → T-PWA01
- **Deliverables**: `GET /sw.js` (root scope, `Cache-Control: no-cache`) from `static/rd/js/sw.js`; `static/rd/js/sw-register.js` loaded from the base layout; public `GET /offline` rendered from `fragments/states/offline-page.html` with no user data; precache list and versioned cache name per ADR-0151 §3; `Clear-Site-Data: "cache"` on sign-out (§5).
- **Acceptance**: navigations are network-only; with the network down a navigation shows the offline page; HTMX and non-GET requests are not intercepted; after signed-in browsing Cache Storage holds exactly the precache URLs (no HTML other than `/offline`); a new release replaces the old cache on the next navigation.
- **Validation**: unit tests for `/sw.js` and `/offline` headers and body; e2e (Playwright `context.set_offline(True)`) for registration, the offline fallback and the Cache Storage contents; `frontend-visual-audit` of `/offline` at 375/1024/1440 in both themes.

### T-PWA03 [S] Install hint in Settings → T-PWA01, PR #59 merged
- **Deliverables**: a short "Install on your phone" hint in Settings (iOS: Share → Add to Home Screen; Android: menu → Install app), hidden when already running standalone; copy and placement through the design gate.
- **Acceptance**: hint renders on touch widths, is hidden under `display-mode: standalone`; axe 0 serious or critical.
- **Validation**: `frontend-visual-audit` of `/settings` at 375/1024/1440.

### T-PWA04 [S] Device check → T-PWA02
- **Deliverables**: a check on a real iPhone (Safari) and Android phone (Chrome) against a drill explore deploy (ADR-0099, operator go): install, standalone launch on `/today`, password and passkey sign-in in the standalone window, offline page with airplane mode, update after a redeploy. Results recorded in `docs/audits/<date>-pwa-device-check.md`.
- **Acceptance**: every step passes, or a failure is recorded with its follow-up (ADR-0151 §6: passkeys in iOS standalone).
- **Validation**: the audit record.

### T-PWA05 [S] Release → T-PWA02, T-PWA04
- **Deliverables**: release through the normal pipeline; ADR-0151 status to Accepted; CHANGELOG line.
- **Acceptance**: on prod, Chrome shows the app as installable and `/sw.js` is served with `Cache-Control: no-cache`.
- **Validation**: `curl -fsSI https://budget.rising-dough.eu/sw.js`; operator installs on their phone.
