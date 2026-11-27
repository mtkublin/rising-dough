# ADR-0151: The Mobile App Is the Installable Web App (PWA); No Native or Store App for Now

- **Status**: Proposed
- **Date**: 2026-11-27
- **Number**: 0151 is also used by open PRs #60, #61, #62 (main ends at 0150 and G14 forbids gaps); renumbered at merge, whichever lands later moves up.
- **Amends**: [ADR-0134](0134-redesign-scope-decisions-from-the-designer-change-request.md) §4 (the service worker deferral is lifted for full page loads only, after the redesign release)
- **Relates to**: [ADR-0123](0123-frontend-stays-server-rendered-no-spa-framework.md) (server-rendered, no SPA; its revisit trigger "offline-first use" is not hit), [ADR-0113](0113-csp-compatible-frontend.md) and [ADR-0036](0036-v3-reverse-proxy-caddy-auto-tls.md) (strict CSP, no inline script), [ADR-0107](0107-sourdough-redesign-from-designer-handoff.md) (redesign, icons, tokens), [ADR-0099](0099-release-and-environment-policy.md) (release path), [ADR-0061](0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) (multi-user data isolation)
- **Requirements**: [`docs/requirements.md` §16](../requirements.md#16-installable-web-app-pwa-added-2026-11-27)
- **Tasks**: T-PWA01 to T-PWA05 ([`docs/plans/pwa/tasks.md`](../plans/pwa/tasks.md))

## Context

The operator asked what a mobile app for iOS and Android would cost (2026-11-27). Facts that drive the answer:

- The app is server-rendered Jinja + HTMX (ADR-0123). Every router returns HTML; there is no JSON API.
- The redesign already ships a phone layout: below 640 px a bottom tab bar with a centre **+ Add** sheet, 44 px touch targets, 16 px inputs so iOS does not zoom (§5, §10.1).
- Auth is a session cookie with CSRF and passkeys (WebAuthn, RP ID `budget.rising-dough.eu`).
- Prod is served over HTTPS on a public URL (v3), which is what installability needs.
- The CSP is strict: `default-src 'self'; script-src 'self' 'nonce-…'`, no inline script (ADR-0113).
- ADR-0134 §4 kept the offline states and deferred a service worker: a failed full page load shows the browser's own error page.

What the operator wants from "an app": an icon on the home screen, a full-screen window without browser chrome, fast start, and a branded page instead of a browser error when the phone is offline. Nothing asked for needs offline editing, background work or a store listing.

## Options considered

Effort figures are rough, solo-developer orders of magnitude from the architecture shape, not measured.

| # | Option | What it takes | Rough effort | Verdict |
|---|---|---|---|---|
| A | **PWA** (manifest + icons + a small service worker) | Head tags, a manifest route, `/sw.js` with an offline fallback, icon set, tests | days (about 2–4) | **Chosen** |
| B | **WebView shell** (Capacitor, or a Hotwire-Native-style shell) loading the hosted app, published to the App Store and Google Play | Two store projects, signing, store accounts (Apple 99 USD per year, Google 25 USD once), passkeys inside a WebView (iOS associated domains and entitlements, Android Digital Asset Links), cookie persistence, deep links, store review | weeks (about 2–4) | Rejected for now |
| C | **Store wrap of the PWA** (Android Trusted Web Activity via Bubblewrap; iOS via a WKWebView wrapper, see B) | Android: a TWA project plus `assetlinks.json`; iOS has no TWA equivalent | Android about a day after A; iOS as B | Deferred; possible follow-up on top of A |
| D | **Cross-platform native** (React Native or Flutter) | A JSON API over the services (they are reusable thanks to thin routers), token auth, every screen rebuilt (Today, Ledger, Plan, Accounts, Settings, dialogs, SVG charts), money formatting kept server-side to respect `domain/money` | months (about 3–5) | Rejected |
| E | **Two native apps** (Swift + Kotlin) | As D, twice | roughly double D | Rejected |

Why not B, C (iOS) or E now:

- **Apple guideline 4.2 (minimum functionality).** A WebView that only loads a website is regularly rejected. Passing review needs native features (push, biometric unlock, share sheet) that nobody has asked for.
- **Passkeys in a WebView** need platform entitlements and a domain association file. This is the riskiest part of B and would need a spike before any commitment.
- **Recurring cost and process.** Store accounts, signing keys, review cycles, and a second release path beside ADR-0099's GitHub-only release.

Why not D or E:

- **Two UIs.** Every screen would exist twice, and the parity and visual regression regime (ADR-0106, ADR-0147) would need a native twin.
- **New API surface.** A JSON API with token auth is a large new attack and test surface. It also breaks the "routers return a view model rendered server-side" rule the guards enforce (ADR-0130).
- **ADR-0123 holds.** It is re-opened only by offline-first use or comparable client state. Nothing in the request needs that.

C on Android stays cheap once A exists. It can be picked up later by its own ADR if a Play Store listing is wanted.

## Decision

### 1. The mobile app is the PWA

Rising Dough becomes an installable web app on iOS (Safari, Add to Home Screen) and Android (Chrome, Install app). There is no native app and no store listing. The installed app runs the same server-rendered pages, so feature parity is automatic.

### 2. Manifest

- `GET /manifest.webmanifest`, `Content-Type: application/manifest+json`, public (no session needed), linked from the base layout head.
- Fields: `name` "Rising Dough", `short_name` "Dough", `id` and `start_url` `/today`, `scope` `/`, `display` `standalone`, `background_color` and `theme_color` from the light theme tokens. The dark theme colour is set with a second `<meta name="theme-color" media="(prefers-color-scheme: dark)">`.
- Icons: 192 and 512 px PNG, a 512 px `maskable` PNG with the safe zone, and a 180 px `apple-touch-icon`. They are generated once from the redesign's mark and committed under `static/rd/icons/` (no build-time generation; Pillow is already a dev dependency on `ui/sourdough`, ADR-0153).
- iOS head tags: `apple-mobile-web-app-capable`, `apple-mobile-web-app-title`, `apple-mobile-web-app-status-bar-style`.

### 3. Service worker: network-only, offline fallback, static shell only

- Served at `GET /sw.js` (root scope, so it controls `/`) with `Cache-Control: no-cache` and a JavaScript content type, from a file under `static/rd/js/`. It is registered by an external script (`static/rd/js/sw-register.js`); no inline script.
- **Never caches authenticated or HTML responses.** Navigations go network-only. On a network failure (not on an HTTP error status) the worker answers with the cached offline page.
- **Precache**: the offline page, the CSS bundle, the fonts, vendored htmx and the icons. These are public, user-independent files. Nothing else is written to Cache Storage.
- **Non-GET requests and HTMX requests pass through untouched.** The redesign's save-failure path (ADR-0134 §4, `offline.js`) keeps handling them.
- The cache name carries the app version. `activate` deletes older caches. A new release takes over on the next navigation (`skipWaiting` + `clients.claim`).
- Not in scope: background sync, push, periodic sync, offline data or offline editing.

### 4. The offline page is static and data-free

The offline page served by the worker is a self-contained HTML response rendered from the redesign's offline state (`fragments/states/offline-page.html`) without any user data, session or nonce, and is available unauthenticated at `GET /offline`. It works in both themes via `prefers-color-scheme`, because the per-user theme setting is unknown offline.

### 5. CSP and headers stay as they are

- `default-src 'self'` already covers `worker-src` and `manifest-src`, and `script-src 'self'` covers the same-origin worker script. ADR-0113 and ADR-0036 are not relaxed.
- Caddy's HTML-only CSP layer is unaffected: `/sw.js` is JavaScript and the manifest is JSON.
- Sign-out adds `Clear-Site-Data: "cache"` so a shared device keeps nothing from the session in its caches. The precache is re-fetched on next start.

### 6. Platform limits accepted

- iOS standalone apps keep their own cookie jar, so the user signs in once more after installing. Passkeys must work in the standalone window. T-PWA04 checks this on a real device before release; if they do not, password sign-in still works and the gap is recorded.
- iOS shows no install prompt, so the Settings page gets a short "Install on your phone" hint (copy and placement through the design gate, PR #59).
- Storage can be evicted on iOS. This is harmless because only the public shell is cached.

### 7. When

- After the redesign release (`ui/sourdough`, PR #54). The base layout, the offline page and the icons come from it.
- It ships through the normal release path (ADR-0099). No migration and no infrastructure change.

## Consequences

- **Positive**: an "app on the phone" for both platforms in days, with one codebase, one release path and no store fees. Feature parity is automatic, and the branded offline page replaces the browser error page.
- **Negative**: no store presence and no push. iOS users install through the Share menu and sign in once more. Offline means "you're offline", not offline use.
- **Requirements**: new §16; the §10.1 offline line points here for full page loads.
- **Tests**: unit tests for the manifest and `/sw.js` responses; e2e (Playwright) checks registration, the offline fallback with the context offline, and that Cache Storage holds only precache URLs after signed-in browsing; a frontend visual audit for the head change, the offline page and the install hint.
- **Revisit**: a request for a store listing, push notifications or offline editing re-opens options B, C or D through a new ADR. Offline editing would also re-open ADR-0123.
