# NOTE: rendered by Terraform into bp-config; the host agent writes it (ADR-0111). Edit the .tpl.
# ADR-0036 §1: Caddyfile shape (auto-TLS, security headers, CSP nonce, rate limit, access logs).

# ADR-0101: on the tailnet-only drill (`tailnet_only`) the hostname is a *.ts.net
# MagicDNS name; Caddy obtains its certificate from the local tailscaled (socket
# mounted in docker-compose), so there is no ACME email and no port-80 site.
{
%{~ if !tailnet_only }
    email ops@${hostname}
%{~ endif }
    admin off
    servers {
        protocols h1 h2 h3
    }
}

${hostname} {
    encode zstd gzip

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=(), interest-cohort=()"
        Cross-Origin-Opener-Policy "same-origin"
        -Server
    }

    # ADR-0111: host agent convergence status for the CI release monitor
    # (generation, image refs, state; no secrets).
    handle /.well-known/bp-deploy-status.json {
        header Cache-Control "no-store"
        root * /srv/bp-status
        rewrite * /status.json
        file_server
    }

    handle {
        # ADR-0133: Caddy shares the host network, the app listens on host loopback.
        # Caddy is the first hop: it overwrites (never trusts) the client's forwarded headers.
        reverse_proxy 127.0.0.1:8000 {
            header_up X-Forwarded-Proto {scheme}
            header_up X-Forwarded-For {remote_host}
            header_up X-Real-IP {remote_host}
            # T-Q254: the app mints its own nonce and CSP; never forward a client value.
            header_up -X-CSP-Nonce

            # T-D132 / ADR-0036: inside reverse_proxy a named matcher is a RESPONSE
            # matcher. A site-level `@html` + `header @html` tests the request and never
            # matches; `match {}` inside `header` is unsupported in Caddy 2.8.
            @html header Content-Type text/html*
            handle_response @html {
                # T-Q254 / ADR-0036 addendum: second layer, non-fetch directives only. The app
                # sends the full nonce CSP; two CSP headers intersect, so no default-src /
                # script-src here (a different nonce would block the app's inline scripts).
                header Content-Security-Policy "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'"
                copy_response
            }
        }
    }

    log {
        output file /var/log/caddy/access.log {
            roll_size 20MiB
            roll_keep 7
            roll_keep_for 168h
        }
        # T-D59 / ADR-0078 §5: no query strings (ledger search `q`, filters) and no
        # credentials in the access log. Verified against Caddy 2.8 `filter` encoder.
        format filter {
            wrap json
            request>uri regexp "\?.*$" ""
            request>headers>Cookie delete
            request>headers>Authorization delete
            resp_headers>Set-Cookie delete
        }
    }
}

%{~ if !tailnet_only }

# Port 80 serves the ACME HTTP-01 challenge and redirects everything else to HTTPS.
:80 {
    redir https://{host}{uri} 308
}
%{~ endif }
