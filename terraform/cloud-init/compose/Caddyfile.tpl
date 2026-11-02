# NOTE: rendered via cloud-init by Terraform. Edits must happen in the .tpl.
# ADR-0036 §1: Caddyfile shape (auto-TLS, security headers, CSP nonce, rate limit, access logs).

{
    email ops@${hostname}
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

    # Per-request nonce exported to upstream for the app's CSP middleware (ADR-0036 §3).
    vars nonce {http.request.uuid}
    request_header X-CSP-Nonce {vars.nonce}

    @html {
        header Content-Type text/html*
    }
    header @html Content-Security-Policy "default-src 'self'; script-src 'self' 'nonce-{vars.nonce}'; style-src 'self' 'nonce-{vars.nonce}'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'"

    reverse_proxy app:8000 {
        header_up X-Forwarded-Proto {scheme}
        header_up X-Real-IP {remote_host}
        header_up X-CSP-Nonce {vars.nonce}
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

# Port 80 serves the ACME HTTP-01 challenge and redirects everything else to HTTPS.
:80 {
    redir https://{host}{uri} 308
}
