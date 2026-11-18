# Security audit log (T-D42)

Append-only log of external security scans of the live prod site `https://budget.rising-dough.eu`. All scans are read-only (GET/HEAD only, no login, no form fuzzing, no load). Raw output is kept outside the repo (scratch); only summaries are recorded here. Cookie values are never recorded.

## 2026-11-16

Target: `budget.rising-dough.eu` (151.115.78.144 / 2001:bc8:1d90:3010::). Deployed image: `ghcr.io/mtkublin/budget-planner:sha-89ac3c2` (Debian 13.7 base, ADR-0102). Policy references: ADR-0036 (Caddy headers/CSP), ADR-0103 (image scan ignores unfixed OS CVEs).

### Results vs targets

| Tool | Target | Result | Status |
|------|--------|--------|--------|
| Mozilla HTTP Observatory (API v2, algorithm v6) | >= A+ | **B, score 75**, 11/12 tests passed, 1 failed (CSP) | FAIL |
| testssl.sh 3.2 | grade A | **A+** (score 96; protocol 100, key exchange 100, cipher 90); no vulnerabilities | PASS |
| trivy image, CI policy (`HIGH,CRITICAL --ignore-unfixed`) | no HIGH/CRITICAL | **0 findings** (OS and Python) | PASS |
| trivy image, full (no `--ignore-unfixed`) | record only | 107 HIGH, 0 CRITICAL; 27 distinct CVEs in 24 Debian packages; none has a fixed version | Recorded |
| nikto 2.5.0 | no significant findings | **Incomplete**: aborted after ~300 requests (error limit 20 reached); nothing reported before abort | Partial |

### 1. Mozilla HTTP Observatory

Command: `curl -X POST "https://observatory-api.mdn.mozilla.net/api/v2/scan?host=budget.rising-dough.eu"`, details from `GET /api/v2/analyze?host=budget.rising-dough.eu`.

- Grade B, score 75, tests passed 11/12.
- Only failed test: `content-security-policy` (`csp-not-implemented`, -25). Passing: cookies (+5, `__Host-csrf` Secure + SameSite=Lax), COOP (+10, `same-origin`), HSTS, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, redirection to HTTPS, CORS not implemented, COEP not implemented (no penalty).
- The score is 75 solely because the CSP is missing (finding F1). With a valid no-unsafe CSP the grade is expected to reach A+ or better.

### 2. testssl.sh

Image: `drwetter/testssl.sh:3.2` (digest `sha256:64bab3c1fd8eee440f68d5e020dd633c1f2d375fe0ae593bdfec2725110a7e29`, run under amd64 emulation on arm64; took 1573 s).
Command: `docker run --rm -v <scratch>:/out drwetter/testssl.sh:3.2 --quiet --color 0 --severity LOW --jsonfile /out/testssl.json budget.rising-dough.eu`

- Overall grade **A+** (experimental SSL Labs 2009r rating, final score 96).
- Protocols: TLS 1.2 and TLS 1.3 only; SSLv2/3, TLS 1.0/1.1 not offered. ALPN h2 + http/1.1. HTTP/3 advertised via Alt-Svc.
- Ciphers: AEAD with forward secrecy only (ECDHE-ECDSA AES-GCM, ChaCha20); server cipher order set; curves prime256v1, X25519.
- Certificate: ECDSA P-256, Let's Encrypt (YE2), valid 2026-11-07 to 2027-02-05 (80 days left at scan time), SAN matches, chain OK, CT present.
- Vulnerabilities: Heartbleed, CCS, ROBOT, CRIME, BREACH, POODLE, SWEET32, FREAK, DROWN, LOGJAM, BEAST, LUCKY13, RC4: all not vulnerable.
- Informational (no grade impact): OCSP stapling not offered (Let's Encrypt has ended OCSP; CRL only); no DNS CAA record (F4).
- HSTS: 365 days, includeSubDomains, preload.

### 3. nikto

Image: `ghcr.io/sullo/nikto@sha256:0bb37022ebfadc38d6a9a2755c03bfd1f9e079e01e8946fe548153d9ba0c2012` (Nikto 2.5.0; upstream image, pinned by digest because only `latest` is published).
Command: `docker run --rm <image> -h budget.rising-dough.eu -p 443 -ssl -Pause 1 -ask no -nointeractive -maxtime 20m` (single run).

- Findings reported: informational only (`x-request-id` uncommon header; Alt-Svc advertises HTTP/3; root redirects to `/auth/login?next=%2Ftoday`; no server banner, so the Caddy `Server` header is stripped as intended).
- The scan terminated early: "Error limit (20) reached for host" after 300 of about 7000 requests (plugin "Site Files"), 533 s. Likely cause: Caddy rate limiting or error responses to probe paths. Not retried (policy: max one run). Coverage is partial; the result means "nothing found in the first ~4%", not a clean bill of health.

### 4. trivy image

Tool: trivy 0.69.3. Image scanned: `ghcr.io/mtkublin/budget-planner:sha-89ac3c2`, pulled directly from GHCR (pullable, so no local rebuild; amd64 only, so `--platform linux/amd64`).

- `trivy image --platform linux/amd64 --severity HIGH,CRITICAL --ignore-unfixed <image>`: **0 vulnerabilities** in `debian 13.7` and in `Python` (CI policy, ADR-0103, passes).
- Same without `--ignore-unfixed`: 107 HIGH, 0 CRITICAL; 27 distinct CVEs across 24 OS packages (util-linux family: bsdutils, mount, login, libblkid1, libmount1, libsmartcols1, libuuid1, liblastlog2-2; krb5 libs; curl/libcurl4t64; ncurses; libsqlite3-0; libsystemd0/libudev1; libacl1; perl-base). **None has a fixed version** in Debian, so nothing is actionable by rebuild. No Python dependency findings.
- `.security-allowlist.yml` `trivy_image` list is empty (consistent with ADR-0103); no allowlist entries were needed.

### 5. Manual header checks (against ADR-0036)

`curl -sI /` returns 302 to `/auth/login?next=%2Ftoday`; `GET /auth/login` returns 200 HTML. (`HEAD /auth/login` returns 405 with `Allow: GET`; harmless.)

| Header | ADR-0036 expectation | Observed |
|--------|----------------------|----------|
| Strict-Transport-Security | max-age=31536000; includeSubDomains; preload | Present, as specified (also on the 302) |
| X-Content-Type-Options | nosniff | Present |
| X-Frame-Options | DENY | Present |
| Referrer-Policy | strict-origin-when-cross-origin | Present |
| Permissions-Policy | camera/microphone/geolocation off, interest-cohort off | Present, as specified |
| Cross-Origin-Opener-Policy | same-origin | Present |
| Content-Security-Policy (nonce, `frame-ancestors 'none'`) | On every HTML response | **Missing** on `GET /auth/login` (200 text/html) |
| Server banner | removed | Absent (OK) |
| HTTP to HTTPS | redirect | 308 to `https://budget.rising-dough.eu/` (OK) |
| Cookies | Secure, SameSite | `__Host-csrf`: Path=/, Secure, SameSite=Lax, no Domain (OK; not HttpOnly, as is normal for a double-submit CSRF cookie) |

### Findings needing action

| # | Severity | Finding | Suggested fix |
|---|----------|---------|---------------|
| F1 | HIGH (an ADR-0036 control is not active). **Fixed in code by T-D132 (2026-11-16); prod gets it with the next release, then re-run Observatory.** | No `Content-Security-Policy` header is served on HTML responses, so there is no nonce-based script restriction, `frame-ancestors`, `form-action` or `object-src` protection. This is the only reason Observatory shows B/75 instead of A+. In `terraform/cloud-init/compose/Caddyfile.tpl` the CSP is attached with `header @html ...` where `@html { header Content-Type text/html* }`; that `header` matcher inspects the **request** headers, so it most likely never matches (the response `Content-Type` is unknown at match time). The app middleware (`web/middleware/security_headers.py`) only consumes the nonce and does not emit the CSP itself. | Either (a) emit the CSP from `SecurityHeadersMiddleware` for HTML responses using the `X-CSP-Nonce` request header (one place for nonce and header, unit-testable), or (b) use a response-phase matcher in Caddy and cover it with a render test. Add an integration assertion that `GET /auth/login` carries the CSP, then re-run Observatory (expect >= A+). Docs first per CLAUDE.md (ADR-0036 follow-up task). |
| F2 | LOW | nikto aborted at about 4% (error limit), so web-layer coverage is incomplete. | Optionally rerun against a drill environment with the rate limit relaxed, or accept given Observatory + testssl + trivy coverage. |
| F3 | LOW / informational | 107 HIGH unfixed Debian 13.7 findings (27 distinct CVEs) in the image; no upstream fix. | No action now (ADR-0103). Re-run the full scan periodically and after each base-image bump; act once a `FixedVersion` appears. |
| F4 | LOW / informational | No DNS CAA record for `rising-dough.eu`; certificate is 90-day Let's Encrypt (80 days left, auto-renewed by Caddy). | Optionally add `CAA 0 issue "letsencrypt.org"` at the DNS provider; watch cert expiry via the uptime check (T-D44). |

### Not run / caveats

- Every requested tool ran; nikto ended early (F2). The Docker daemon had to be started locally first. An earlier testssl start while Docker was down failed immediately; the recorded run is the complete one.
- Observatory results reflect the site at 2026-11-16 20:30 UTC.

## 2026-11-18

Target: `budget.rising-dough.eu` (151.115.78.144). Deployed image: `ghcr.io/mtkublin/budget-planner:v3.0.1` (Debian 13.7 base), live since the 2026-11-18 release (run 44294472551; CSP from T-D132 is now sent). All scans read-only, one normal pass each, from the operator laptop. Raw output kept in scratch only.

### Results vs targets

| Tool | Target | Result | Status |
|------|--------|--------|--------|
| Mozilla HTTP Observatory (API v2, algorithm v6) | >= A+ | **A+, score 130**, 12/12 tests passed (was B/75) | PASS |
| testssl.sh 3.2 | grade A | **A+** (score 96; protocol 100, key exchange 100, cipher 90); no vulnerabilities | PASS |
| trivy image, CI policy (`HIGH,CRITICAL --ignore-unfixed`) | no HIGH/CRITICAL | **0 findings** (OS and Python) | PASS |
| trivy image, full (no `--ignore-unfixed`) | record only | 107 HIGH, 0 CRITICAL; 27 distinct CVEs in 24 Debian packages; none has a fixed version (same as 2026-11-16) | Recorded |
| nikto 2.5.0 | no significant findings | **Ran to its 45 min time limit, not to the end of the checks**; 4 informational items, no vulnerability; 216 connection errors (see F2) | Partial |

### 1. Mozilla HTTP Observatory

Command: `curl -X POST "https://observatory-api.mdn.mozilla.net/api/v2/scan?host=budget.rising-dough.eu"` (scan at 2026-11-18 11:42 UTC).

- Grade **A+**, score 130, 12 of 12 tests passed, 0 failed.
- The only failure on 2026-11-16 (`content-security-policy`) is gone. `GET /auth/login` now returns `Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-...'; style-src 'self' 'nonce-...'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'` (per-request nonce, no `unsafe-inline`).

### 2. testssl.sh

Image: `drwetter/testssl.sh:3.2` (amd64 emulation on arm64).
Command: `docker run --rm -e MAX_SOCKET_FAIL=200 -e MAX_OSSL_FAIL=200 -e MAX_HEADER_FAIL=200 -v <scratch>:/out drwetter/testssl.sh:3.2 --quiet --color 0 --severity LOW --jsonfile-pretty /out/testssl3.json budget.rising-dough.eu`

- Overall grade **A+** (final score 96), same as 2026-11-16.
- TLS 1.2 and 1.3 only, AEAD + forward secrecy ciphers, curves prime256v1 and X25519; ECDSA P-256 certificate from Let's Encrypt (YE2), valid 2026-11-07 to 2027-02-05 (79 days left); HSTS 365 days, includeSubDomains, preload.
- Heartbleed, CCS, Ticketbleed, ROBOT, CRIME, POODLE, SWEET32, FREAK, DROWN, LOGJAM, BEAST, LUCKY13, Winshock: all not vulnerable.
- Informational, no grade impact: OCSP stapling not offered (Let's Encrypt ended OCSP); **DNS CAA RR not offered** (F4, fix pending release).
- Operational note: the first two attempts aborted with "Connection refused / repeated TCP connect problems" (MAX_SOCKET_FAIL 2). Attempt 1 ran concurrently with nikto; attempt 2 ran right after nikto finished. The host (or Caddy) drops connections from the scanning IP after heavy probing. The third run (above, nothing else running, raised failure limits) completed.

### 3. nikto

Image: `ghcr.io/sullo/nikto@sha256:0bb37022ebfadc38d6a9a2755c03bfd1f9e079e01e8946fe548153d9ba0c2012` (Nikto 2.5.0). The error limit lives in `nikto.conf` (`FAILURES=20`); a copy with `FAILURES=500` was mounted read-only.
Command: `docker run --rm -v <scratch>/nikto.conf:/etc/nikto.conf:ro <image> -config /etc/nikto.conf -h budget.rising-dough.eu -p 443 -ssl -Pause 1 -ask no -nointeractive -maxtime 45m -Display E` (single run, 11:45 to 12:30 UTC; no brute force, no DoS tuning).

- Findings: informational only. `x-request-id` uncommon header; Alt-Svc advertises HTTP/3 (nikto cannot test QUIC); root redirects to `/auth/login?next=%2Ftoday`; no server banner; no CGI directories found.
- Two "suggested header missing" lines were checked by hand and are not findings: nikto flagged no CSP and no `X-Content-Type-Options` on `/`, but `/` is a bodiless 302 and `curl -D -` shows `X-Content-Type-Options: nosniff` (plus HSTS, XFO, Referrer-Policy, Permissions-Policy, COOP) on it. CSP is only meant for HTML responses (ADR-0036) and is present on `/auth/login`.
- Not complete: the run hit the 45 min limit with 216 request errors (201 "ssl connect failed", 15 connect timeouts), so only part of the check list ran. With the error limit raised, the scan no longer stops early, but the server keeps refusing TLS handshakes once nikto is active (the same behaviour that broke testssl). Consistent with a connection rate limit (host firewall or Caddy), not with an app fault; `/health` stayed 200 throughout. Coverage is "no findings in what was reachable", not a clean bill of health.

### 4. trivy image

Tool: trivy 0.69.3. Image: `ghcr.io/mtkublin/budget-planner:v3.0.1`, pulled directly from GHCR (no `security.yml` fallback needed; amd64 only, so `--platform linux/amd64`).

- `trivy image --platform linux/amd64 --severity HIGH,CRITICAL --ignore-unfixed ghcr.io/mtkublin/budget-planner:v3.0.1`: **0 vulnerabilities** in `debian 13.7` and in the Python packages (CI policy, ADR-0103).
- Same with `-f json` and no `--ignore-unfixed`: 107 HIGH, 0 CRITICAL; 27 distinct CVEs across 24 OS packages; **no finding has a `FixedVersion`**. Identical counts to the sha-89ac3c2 scan, so the v3.0.1 image adds nothing new.

### Previous findings

| # | Status | Note |
|---|--------|------|
| F1 CSP missing | **Closed** | CSP served (T-D132, v3.0.1); Observatory B/75 to A+/130. |
| F2 nikto incomplete | **Open (LOW)** | Error limit no longer the blocker; the host refuses TLS handshakes during nikto, so the run is cut by the 45 min limit. Follow-up below. |
| F3 unfixed Debian CVEs | Open, accepted (LOW) | ADR-0103; no fix available. Re-scan after each base-image bump. |
| F4 no CAA record | **Fix in repo, pending release** | `terraform/modules/dns` now manages CAA for the app hostname (prod only, ADR-0101): `0 issue "letsencrypt.org"`, `0 issue "sectigo.com"`, `0 issuewild ";"`. Caddy has no `acme_ca`/`issuer` override, so its defaults apply: Let's Encrypt, then ZeroSSL as fallback; ZeroSSL issues through Sectigo (CAA identifier `sectigo.com`), so it must be listed or a fallback issuance would be refused. Reaches prod with the next approved `terraform apply`. Re-run testssl (`DNS CAA RR`) after that. |

### New findings

None at MEDIUM or above. No HIGH/CRITICAL needs a code fix.

### Follow-ups

- After the next release: check `dig CAA budget.rising-dough.eu` and that the next Caddy renewal still succeeds (renewals start about 30 days before 2027-02-05).
- Optional (F2): re-run nikto against a drill with the connection limit relaxed, or find out which layer drops handshakes (UFW `limit`, Caddy rate limit, Scaleway security group). Not blocking.
