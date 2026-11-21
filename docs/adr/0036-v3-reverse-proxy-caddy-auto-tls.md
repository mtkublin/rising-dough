# ADR-0036: v3 Reverse Proxy & TLS — Caddy with Automatic HTTPS

- **Status**: Accepted (2026-11-21; amended by addendum below: stock caddy image, rate limiting moved to the app per ADR-0072)
- **Date**: 2026-10-27 (renumbered v2 → v3 on 2026-10-28)
- **Related**: ADR-0032 (v3 remote deployment), ADR-0033 (auth), ADR-0035 (Terraform IaC)

## Context

The v3 topology (ADR-0032) terminates TLS on the host, not at the application. The reverse proxy must:

- Issue and renew certificates automatically (zero manual steps for cert management).
- Terminate HTTP/HTTPS and forward to the app container on a Unix socket or loopback TCP.
- Inject strict security headers (HSTS, X-Frame-Options, CSP with per-request nonce, Referrer-Policy, Permissions-Policy).
- Serve `/.well-known/acme-challenge/*` on port 80 for ACME HTTP-01 while redirecting everything else to HTTPS.
- Expose structured access logs so `fail2ban` can jail abusive IPs on `/auth/*`.
- Be configurable from a single file rendered by Terraform cloud-init.

Candidates evaluated:

1. **Caddy** — auto-TLS built in, Caddyfile is small and readable, native structured logs, maintained.
2. **Nginx + certbot** — mature but splits concerns across three config surfaces (nginx, certbot cron, systemd), more moving parts to template.
3. **Traefik** — great for dynamic container discovery; overkill for one app + one host.
4. **HAProxy** — needs an external ACME helper.

## Decision

Use **Caddy v2.8+** as the reverse proxy and TLS terminator. Run it in a dedicated container inside the same `docker compose` stack as the app and the Litestream sidecar.

### 1. Caddyfile (final shape)

Rendered by Terraform from `terraform/cloud-init/compose/Caddyfile.tpl` with the single input `hostname`:

```caddy
{
    email ops@${hostname}
    admin off
    servers {
        protocols h1 h2 h3
    }
}

${hostname} {
    encode zstd gzip

    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=(), interest-cohort=()"
        Cross-Origin-Opener-Policy "same-origin"
        -Server
    }

    # CSP with per-request nonce; app injects {{ csp_nonce }} into every <script>/<style> tag.
    @html {
        header Content-Type text/html*
    }
    header @html Content-Security-Policy "default-src 'self'; script-src 'self' 'nonce-{http.vars.nonce}'; style-src 'self' 'nonce-{http.vars.nonce}'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'"

    # Per-request nonce (random hex) exported to downstream.
    vars {
        nonce {http.request.uuid}
    }
    request_header X-CSP-Nonce {http.vars.nonce}

    # Rate limit auth endpoints (requires the `caddy-ratelimit` plugin, pinned in the custom Caddy image).
    @auth path /auth/* /auth
    rate_limit @auth {
        zone auth {
            key    {remote_host}
            events 10
            window 60s
        }
    }

    reverse_proxy app:8000 {
        header_up X-Forwarded-Proto {scheme}
        header_up X-Real-IP {remote_host}
        header_up X-CSP-Nonce {http.vars.nonce}
    }

    log {
        output file /var/log/caddy/access.log {
            roll_size 20MiB
            roll_keep 7
            roll_keep_for 168h
        }
        format json
    }
}

# Serve ACME HTTP-01 challenge, 308 everything else to HTTPS. Caddy does this by default; made explicit.
:80 {
    @acme path /.well-known/acme-challenge/*
    handle @acme {
        file_server {
            root /data/caddy
        }
    }
    redir https://{host}{uri} 308
}
```

### 2. Container image

- Base image **does not include** the rate-limit plugin by default. The deployment uses a tiny custom image built via the `xcaddy` builder and pushed to GHCR as `ghcr.io/<owner>/caddy-ratelimit:<caddy-version>`. Dockerfile stub lives in `terraform/cloud-init/compose/caddy/Dockerfile` and is built by a GitHub Actions workflow on changes to that directory.
- Image is pinned by digest in `docker-compose.yml.tpl`.

### 3. Nonce propagation

- Caddy sets `{http.vars.nonce}` per request and injects it as `X-CSP-Nonce` upstream header.
- The app's `SecurityHeadersMiddleware` (ADR-0033 §5) reads the header and puts it in Jinja context as `csp_nonce`. Every inline `<script>` / `<style>` in templates uses `{{ csp_nonce }}`.
- A Phase 1 unit test asserts that the rendered HTML contains the exact nonce from the request header; a Phase 4 integration test asserts the CSP header rejects an inline script without the nonce.

### 4. Logs

- JSON access logs in `/var/log/caddy/access.log`, rotated by Caddy itself.
- The host mounts `/var/log/caddy` into `fail2ban` so the `caddy-auth` jail can read 401s on `/auth/*`.
- `journalctl -u docker` captures stderr for operational tailing; no centralised log store in v3.

### 5. Certificate storage

- Caddy stores ACME account + certs under `/data/caddy` (mounted as a named volume `caddy-data`).
- The volume is **not** replicated to object storage. If destroyed, Caddy re-issues from Let's Encrypt (within rate limits).
- To avoid rate-limit scares during disaster recovery, the Phase 4 runbook snapshots the volume to object storage once per week via `rclone sync caddy-data: s3:budget-planner-prod-pl-waw/caddy-data`. Non-critical; LE rate limits allow 50 certs/week per account.

### 6. HTTP → HTTPS

- Only HTTPS is served for app traffic. Port 80 exclusively serves the ACME challenge and redirects.
- HTTP/3 enabled (QUIC on UDP 443). Not critical for a single-user app but costs nothing on Caddy.

### 7. Health endpoints

- Caddy forwards `/health` and `/ready` without rate limiting and without auth (ADR-0033 marks them public).
- `/health` returns 200 iff Caddy itself is up (handled by the forward). `/ready` reaches the app and the app checks the DB connection.

## Consequences

### Positive

- One config file (Caddyfile) covers TLS, headers, CSP nonce, rate limiting, and logging.
- Zero manual cert management; Caddy renews ~30 days before expiry.
- CSP with per-request nonce is the strongest practical browser-side defence against XSS at this stack.
- Fail2ban jail is wired to real signals from Caddy's structured log.

### Negative

- Custom Caddy image means an extra artifact in the registry. Mitigated by a small Dockerfile and a cheap GHA job.
- Caddy's rate-limit plugin is community-maintained; version drift risk. Pinned by digest.
- Let's Encrypt rate limits apply during cert replays after full tear-downs. The weekly cert snapshot and the production/drill environment split mitigates this.

### Follow-ups

- A later ADR may replace the HTTP-01 challenge with DNS-01 (`caddy-dns/scaleway`) once the Scaleway DNS plugin is proven stable, to avoid port 80 exposure entirely.
- A later ADR may evaluate Caddy's native WebAuthn plugin as a replacement for app-layer auth once that plugin reaches stable status (currently in flux; app-layer auth is more flexible for the single-user model).

## Alternatives Considered

- **Nginx + certbot** — rejected (three config surfaces, no built-in rate-limit for `/auth/*`, more templates to render).
- **Traefik** — rejected (overkill for one host, dynamic routing not needed).
- **HAProxy + Lego** — rejected (two moving parts for TLS; Caddy covers both).
- **Cloudflare in front of the host** — rejected (adds a third-party dependency and introduces a surface for request forwarding issues; the app is small enough that direct termination is simpler and keeps data in-region).

## Addendum 2026-11-16 (T-D132): the CSP must be set with a response matcher

The CSP was never sent in prod: `header @html ...` with `@html { header Content-Type text/html* }` is a request matcher, so it never matched a browser GET. A `match { ... }` block inside `header` is not supported by Caddy 2.8 (it is parsed as a header named `Match`). The CSP therefore stays at Caddy (§3 is unchanged) but is set inside `reverse_proxy` with `@html header Content-Type text/html*` and `handle_response @html { header Content-Security-Policy "..."; copy_response }`, where the named matcher is evaluated against the upstream response. Policy string and nonce are unchanged. Guarded by `tests/unit/deploy/test_caddy_csp.py`.

## Addendum 2026-11-18 (T-D140): `style-src` amended by ADR-0113

The `style-src` directive in §1 is replaced by `style-src 'self' 'unsafe-inline'` (stopgap, no nonce). Inline style attributes are allowed until the templates move to classes (T-D140d). `script-src` is unchanged and stays strict. See [ADR-0113](0113-csp-compatible-frontend.md). The prod policy broke HTMX-driven buttons because the frontend used inline scripts, a CDN and Google Fonts; ADR-0113 fixes the frontend side.

## Addendum 2026-11-21: stock Caddy image, app-side rate limiting

Two statements above no longer hold. (1) Section 2 describes a custom `xcaddy` image with the `caddy-ratelimit` plugin; the deployment runs the stock `caddy:2.8` image (`terraform/cloud-init/compose/docker-compose.yml.tpl`) and no custom Caddy Dockerfile exists. (2) Auth rate limiting is not done by Caddy: it is in-house fixed-window counters in the app ([ADR-0072](0072-auth-rate-limit-sqlite-fixed-window.md)), and the client IP chain is amended by ADR-0133. The `rate_limit @auth` block and the fail2ban jails are not implemented. Quality-audit findings Q-052, Q-053 (D-13).
