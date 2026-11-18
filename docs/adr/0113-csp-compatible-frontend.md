# ADR-0113: CSP-Compatible Frontend — No Inline Script, Vendored Assets

- **Status**: Accepted
- **Date**: 2026-11-18
- **Relates to**: ADR-0027 (frontend toolchain), ADR-0036 (nonce CSP, partially amended here for `style-src`), ADR-0111 (host state delivery of the Caddyfile), T-D132, T-D140
- **Amends**: ADR-0036 §CSP (`style-src` only; `script-src` is kept as decided)

## Context

Since the T-D132 fix (ADR-0036), Caddy sends the nonce CSP on HTML responses in prod. Prod v3.0.1 (2026-11-18) is the first release where the browser enforces it on the real app, and the result is that HTMX-driven controls are dead:

- Add (Today, Ledger), Promote (Today), and Override (Plan/Budget) do nothing.

Dev has no Caddy and therefore no CSP, so dev behaves normally and every test that runs without Caddy passed. Reproduced locally by injecting the same policy with Playwright. The violations were:

1. **HTMX from a CDN.** `base.html` loads `https://unpkg.com/htmx.org@2`. The host is not in `script-src`, so `window.htmx` is undefined and no `hx-*` attribute works.
2. **Inline `<script>` blocks.** `base.html` and about ten partials contain inline script. No template emits `csp_nonce`, and partials swapped in by HTMX could never match the page nonce anyway, because each response gets a fresh nonce.
3. **Inline event handlers.** About 25 `onclick=` and `hx-on::` attributes. Nonces never cover attributes, and `hx-on` evaluates code, which needs `'unsafe-eval'`.
4. **Inline styles.** 27 templates use `style="..."` attributes, and the HTMX indicator injects a `<style>` element. These are blocked under `style-src 'self' 'nonce-…'`.
5. **Google Fonts.** The stylesheet host is not allowed by `style-src` or `font-src`.

The gap that let this through: the drill smoke test has no browser under the CSP, and the e2e suite runs without Caddy, so no test ever saw the policy the browser receives.

## Decision

The frontend is made compatible with the strict policy that ADR-0036 already ships. The policy is not relaxed for scripts.

1. **Scripts stay strict.** `script-src 'self' 'nonce-{uuid}'` is unchanged. No `'unsafe-inline'`, no `'unsafe-eval'`, no CDN host in `script-src`.
2. **htmx is vendored.** A pinned 2.x release is committed under `src/budget_planner/web/static/vendor/` and served from `'self'`. No runtime CDN. Its licence and version are recorded next to the file.
3. **Fonts are self-hosted.** The woff2 files live under `src/budget_planner/web/static/`, declared in `fonts.css` with `@font-face` and `font-display: swap`. The Google Fonts links and preconnects are removed. `font-src 'self'` and `style-src` need no external host.
4. **No inline script, no inline handlers.** Templates contain no inline `<script>` element and no `on*=` or `hx-on` attribute. Behaviour lives in static JS files loaded once from `base.html` (`<script src="…" defer>`, nonce not needed). Handlers use event delegation on `data-*` attributes (for example `data-action="promote"`), so they also work for HTMX-swapped content without rebinding.
5. **htmx configuration without inline script.** Configuration is supplied through `<meta name="htmx-config" content='{"includeIndicatorStyles": false, "allowEval": false}'>`. With `includeIndicatorStyles: false` htmx does not inject its `<style>` element; the indicator styling moves to the app stylesheet. With `allowEval: false`, `hx-on` and other eval paths are disabled, which is the reason item 4 forbids `hx-on`.
6. **Stopgap for styles.** `style-src 'self' 'unsafe-inline'`. The nonce is removed from `style-src`, because when a nonce is present browsers ignore `'unsafe-inline'`, and the stopgap only works without the nonce. Rationale: inline style attributes cannot run script and carry low risk; migrating the 27 templates to classes is a follow-up (T-D140d) and is not part of this fix. `style-src` is the only directive that changes from ADR-0036.
7. **Regression guard.** The e2e fixture reads the prod CSP from `terraform/cloud-init/compose/Caddyfile.tpl` (so it cannot drift from what Caddy sends) and injects it on every response. Any CSP violation reported by the browser fails the test. Tests run against the real HTML the app produces, including partials swapped by HTMX.

Scope of this decision: the policy string in ADR-0036 is otherwise unchanged; the Caddy change is limited to `style-src`.

## Consequences

- The prod buttons work again once the fix is released. Nothing on the server changes except the Caddy `style-src` value and the static files.
- Scripts stay under a strict nonce policy; a reflected or stored HTML injection still cannot execute script, because there is no inline script to match and no `unsafe-eval`.
- Inline styles remain allowed. This is a known, bounded weakening, recorded here and tracked as T-D140d.
- Template authors must not add `<script>` or `on*=`. The e2e CSP guard enforces this at test time.
- Vendored htmx needs a deliberate bump (pinned version, file replaced, hash recorded); there is no silent upgrade.
- Adds about one static JS module set and a small font payload (woff2 subsets) to the first page load. Preload only the primary font weight, per the performance rules.

## Alternatives considered

- **A: Relax the CSP** (`'unsafe-inline'` and `'unsafe-eval'` in `script-src`, allowlist `unpkg.com`). Rejected. It makes the nonce policy from ADR-0036 meaningless for scripts, and an allowlisted CDN is a third-party trust dependency on every page. It would gut ADR-0036.
- **C: Hotfix now, proper fix later** (for example, loosen the policy for one release, then migrate). Rejected. Every release goes through the same `terraform apply` path (ADR-0111), so a hotfix is a release either way. Loosening the policy would ship a weaker site for the time it stays in place, and the migration would then be done under pressure with no guard.
- **Keep the CDN and add a nonce to htmx.** Rejected. htmx's own script tag cannot carry a nonce unless it is inlined; vendoring is simpler and removes the external dependency.
- **Use a hash for every inline script.** Rejected. Partials swapped by HTMX would each need a hash, and inline handlers cannot be hashed at all.

## Follow-ups

- T-D140d: replace `style="..."` attributes with classes, then drop `'unsafe-inline'` from `style-src` and restore a nonce or hash policy for styles.
- 2026-11-18: T-D140d (drop style-src 'unsafe-inline') deferred to the redesign migration, ADR-0107. The redesign rebuilds the templates anyway, so inline styles are removed there instead of twice. Tracked in `docs/plans/ui-redesign/tasks.md` (T-UR16 hardening item).
