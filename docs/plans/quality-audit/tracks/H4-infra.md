# Track H4 — Infrastructure exposure (red team on a live explore drill)

Task T-Q18 / H4. White-box, read-only. Target: explore drill `budget-planner-drill-44609305750` (tailnet 100.116.84.107), run 44609305750, ref `main`, app image `sha-9ace5bb`. Probing window 20:44Z to 20:55Z on 2026-11-19. No packet was sent to prod; no secret value is written in this file or in `repro/H4/` (redacted at source, see each script).

## Result

No Critical. No prod data on the drill. 1 Medium confirmed live (H4-01, real client IP lost, which collapses the per-IP rate limit and the audit IP), 1 Medium design-level (H4-03, prod read credential and prod age identity sit on the drill host), 4 Low/Informational.

| ID | Severity | Confidence | Title |
|---|---|---|---|
| H4-01 | Medium | Confirmed | Caddy and the app see every tailnet client as the Docker gateway 172.18.0.1: per-IP login rate limit is one shared bucket and `audit_log.ip` is useless |
| H4-02 | Low | Confirmed | Unauthenticated status endpoints disclose image refs and digests, deploy generation, restore result and replica generation |
| H4-03 | Medium | Confirmed (presence, permissions); value validity not tested | Drill host carries the prod replica read-only key and the (prod) age identity, readable by `operator` via passwordless sudo and mounted into 4 containers |
| H4-04 | Low | Confirmed | `caddy:2.8` and `litestream/litestream:0.3.14` are mutable tags in the rendered compose (D-10) |
| H4-05 | Low | Confirmed | Only the app container is hardened; caddy and 3 litestream containers run as root with rw rootfs and no cap_drop; `icc:false` does not isolate the custom `edge` network |
| H4-06 | Low | Confirmed | App container keeps the initial admin password and cookie secret in its environment; both readable via `docker inspect` by the `docker` group |

## 0 · Step 0 — prod-data check (done first)

Question: does the drill DB hold restored prod data? **No.**

| Check | Observation |
|---|---|
| `litestream-restore` container log | `level=ERROR msg="failed to run" error="no matching backups found"` then `litestream-restore: no replica generation; starting empty (allow_empty_db)` |
| Restore report (`/data/restore-report.json`, also in the public status JSON) | `{"result":"empty","generation":""}` |
| Restore config on the host | `litestream-restore.yml` points at bucket `budget-planner-drill-pl-waw` (the drill's own), key = `SCW_ACCESS_KEY` of the drill; `LITESTREAM_ALLOW_EMPTY_DB=true` |
| Replica generation now | `cd68cc75…` created 20:41Z by this host (new generation, not a prod one) |
| Row counts (read-only open of `/data/budget.db`) | `users` 1, `accounts` 0, `transactions` 0, `categories` 2, `sessions` 0, `audit_log` 1 (before my probes) |
| User email domains | `gmail.com` (single seeded admin from `BUDGET_PLANNER_ADMIN_EMAIL`; this is the seed, not a restore) |
| `restore-from-prod` | present at `/usr/local/bin/restore-from-prod` but not run on this VM (no `restore-source` activity, DB empty) |

Conclusion: clean, probing continued. Caveat recorded as H4-03: the credentials that would allow a prod restore are on the box.

## 1 · Coverage

| Goal | Status | Where |
|---|---|---|
| Reachable ports from tailnet | Done with `nc -z` (nmap not installed; 30 common ports, sequential 1 s). Open: 22, 443, 47390 (tailscaled peerapi). Closed: 80, 2019, 8000, 2375/6, 5432, etc. | `repro/H4/h4_net_probe.sh`, `out_net_probe.txt` |
| Ports from the host (`ss`, docker vs ufw, D-11) | Done. Only 22, 443 (tcp+udp) publicly bound; 8000 not published; Caddy admin API off | `out_host_probe.txt` |
| Public-IP reachability (D-11) | Laptop to `151.115.86.61`:22/80/443/2019/8000 all filtered/closed (SG or provider filter). Docker publishes `0.0.0.0:443` and ufw does not govern DNAT traffic, so the only barrier observed is upstream of the VM | `out_net_probe.txt`, H4-06 not raised, see Notes |
| Tailnet ACL gaps | Partial. ACL source file is not in the repo. Observed: from the drill, `tailscale status` lists only the laptop and the phone; **prod is not visible from tag:drill**. Not tested: tag:ci reach, because no CI node is available. I did not contact prod | `out_host_probe2.txt`, section 4 |
| Caddy headers: normal, 404, 500, error paths (D-03, D-08) | Done. See section 2 | `out_http_probe.txt`, `out_error_path.txt` |
| XFF overwrite (H3-01) | Done, answer in section 3 | `out_xff_probe.txt` |
| `/docs`, `/openapi.json`, `/redoc`, `/dev/components` (D-12) | Unauthenticated: all 302 to `/auth/login`. Authenticated exposure not tested (no login attempted with the real admin credentials) | section 4 |
| `/ready` (D-05) | `200 {"status":"ready","db":"ok"}`, unauthenticated, no detail | section 4 |
| Image tags and digests (D-10) | Done | H4-04, `out_host_probe.txt` |
| Secrets in logs, env, layers | Logs: 0 matches in all 5 containers and the journal for key patterns. Env: names listed. History: only the base-image `GPG_KEY` (public Python release key id), no app secrets in layers | `out_host_probe.txt` |
| user_data / metadata exposure | App container cannot reach 169.254.42.42 (DOCKER-USER DROP rule, timeout). `operator` reaches `/conf` without sudo (returns only `ALLOWED_ACTIONS`); `bp-config` needs sudo, and `operator` has passwordless sudo, so operator = root | `out_host_probe.txt` |
| Bucket access with drill creds | Done, LIST only, no object read. `ListBuckets` shows `budget-planner-drill-pl-waw` (list 200) and `budget-planner-tfstate-drill-pl-waw` (list 403). **No prod bucket is visible** to the drill key | `repro/H4/h4_bucket_probe.py`, `out_bucket_probe.txt` |
| Caddy 502 page when app is down | Not attempted (would require stopping the app; rules forbid host changes) | Question 1 |
| Concurrent-request / DoS | Not attempted (rules) | n/a |
| Not attempted | nmap (absent), UDP scan, tag:ci to tag:prod:22 ACL (H1-01 context), authenticated flows | |

## 2 · Header and error-path matrix (Caddy 2.8.4 in front of the app)

Site-level `header` block applies on every response: HSTS, nosniff, X-Frame-Options DENY, Referrer-Policy, Permissions-Policy, COOP, `-Server`.

| Path | Status | CSP | Other headers |
|---|---|---|---|
| `/auth/login` (HTML) | 200 | Present, nonce from Caddy's request uuid; `style-src 'unsafe-inline'` | all present |
| `/` and unauth 404 paths (`/nonexistent`, `/docs`, `/dev/components`) | 302 to login | none (no body) | all present |
| `/static/nonexistent.css` | 404 JSON `{"detail":"Not Found"}` | none (JSON) | present |
| `/auth/login` POST without CSRF | 403 JSON `invalid_csrf` | none (JSON) | present |
| `/auth/login` POST with non-ASCII CSRF token (D-02) | **500 HTML "Something went wrong"**, pre-auth, no traceback in body | **present** (`handle_response @html` fires on the 500) | all present |
| `TRACE` | 405 JSON | none | present |
| Wrong `Host:` header over valid TLS | Caddy replies `200`, empty body, `Server: Caddy` header returned, no app headers; app TrustedHost check is never reached | none | partial |
| Direct `https://100.116.84.107/` (no SNI) | TLS fails (no cert for the IP) | n/a | n/a |

So D-02 is reproduced on the live drill and D-03/D-08 hold for the HTML paths tested: the CSP gap is only on non-HTML responses, which is acceptable. The 500 HTML page is generic. The wrong-Host 200 with an empty body (note `-Server` does not apply, the `Server: Caddy` header is present) is cosmetic.

## 3 · Answers

**H3-01 / D §7 H4-1: does Caddy overwrite `X-Forwarded-For`?** Yes. Two failed logins were sent with `X-Forwarded-For: 203.0.113.7`, `X-Real-IP: 203.0.113.7`, `X-CSP-Nonce: forged-nonce`, then again with `198.51.100.9`. The stored rows contain neither forged address: `audit_log.ip = 172.18.0.1` and `auth_rate_limit.key = login_ip:3600s:ip=172.18.0.1` (count 2, one bucket for both probes). The forged `X-CSP-Nonce` was replaced: the response CSP carries a Caddy uuid nonce, not `forged-nonce`. So the rate-limit key cannot be rotated by header, and `uvicorn --forwarded-allow-ips=*` is not exploitable today through Caddy. But see H4-01: the address it receives is the wrong one.

**D §7 H4-2: is app port 8000 reachable from other containers and loopback?** From the `litestream-probe` container on the shared `edge` network: yes, `http://budget-planner-app:8000/health` returns 200 (`icc:false` in `daemon.json` only affects the default bridge). From the host loopback: no (not published). From the tailnet and the public IP: no. D-11 on the public path: the laptop could not reach 22/80/443 on `151.115.86.61`, so the bypass is not exploitable from the internet here, but I could not prove why (Scaleway security group, outside the VM).

**D §7 H4-3: secrets in the app container.** `BUDGET_COOKIE_SECRET`, `BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD` and `BUDGET_DATABASE_URL` are present in `docker inspect` env (names only recorded). The initial password stays set after first login (H4-06). `operator` is in groups `sudo` (passwordless) and `docker`, so root equals operator on the host. The initial-password variable is not unset by the platform. The app container cannot read the age key or bucket keys: its mounts are `/data` and `/replication` (ro) only.

**D §7 H4-4: what do status endpoints reveal?** See H4-02. Caddy's 502 page was not tested.

**D §7 H4-5: replica and drill-bucket access with a drill credential.** The drill key can list the drill bucket and sees the tfstate-drill bucket name (403 on list). It does not see any prod bucket. The prod read-only key and the age identity are on the host separately (H4-03), and I deliberately did not use them.

**D-05:** `/ready` is unauthenticated and reveals only `status` and `db`. **D-10:** H4-04. **D-12:** docs and dev routes are behind the login redirect for unauthenticated callers; authenticated reachability untested. **D-11:** section 1.

## 4 · Findings

### H4-01 | Medium | Confirmed | infra-exposure
- **Title:** Every tailnet client reaches Caddy and the app as `172.18.0.1`, so IP-based controls see one address.
- **Locations:** `/etc/budget-planner/Caddyfile` (`header_up X-Real-IP {remote_host}`, no `trusted_proxies`), `src/budget_planner/web/routers/auth.py:85-100` (`_client_ip`, `_ip_identity`), `src/budget_planner/web/deps.py:57`, `Dockerfile:104-108`, host nat table (`repro/H4/out_nat.txt`).
- **Description:** Caddy's own access log shows `remote_ip`/`client_ip` = `172.18.0.1` (the `budget-planner_edge` bridge gateway) for requests that came from the laptop over Tailscale. The app therefore records the gateway for every request. Likely cause: the `MASQUERADE` rules on the bridge (`-o br-… -m addrtype --src-type LOCAL`, `ts-postrouting` mark masquerade) rewrite the tailnet source before it reaches the container; I did not isolate which rule, only the observed outcome. `userland-proxy:false` is set, so docker-proxy is not the cause.
- **Evidence:** `repro/H4/h4_xff_probe.sh`, output `out_xff_probe.txt`: `auth_rate_limit` rows `login_ip:3600s:ip=172.18.0.1` and `login:3600s:ip=172.18.0.1|email=…`; `audit_log.ip=172.18.0.1`; Caddy log client_ip `172.18.0.1` (`out_host_probe2.txt`).
- **Impact:** (1) `login_ip` limit (`rate_limit_login_ip_per_hour`) is a single bucket for all clients: any tailnet peer can exhaust it and lock the owner out of password login for an hour, and the limiter gives no per-attacker separation. (2) `audit_log.ip` (ADR-0072 and the session security UI) never identifies the real device. (3) Both defeat the intent of the T-D09 rate limit.
- **Mitigation:** Make the real source address reach Caddy (host-network Caddy, or keep the packet source with `iptables`/`--ip-masq` adjustments on the bridge, or pass the tailnet identity via the tailscale socket `whois`), then in Caddy set `trusted_proxies` explicitly and have the app trust only the Caddy address (`--forwarded-allow-ips=<caddy ip>` instead of `*`). Add a drill smoke check that sends a request and asserts `audit_log.ip` is a `100.x` address.
- **Effort:** M. **Related:** H3-01, D-§7 Q2, ADR-0036, ADR-0072.

### H4-02 | Low | Confirmed | infra-exposure
- **Title:** Unauthenticated status endpoints reveal build and replica internals.
- **Locations:** Caddy `handle /.well-known/bp-deploy-status.json` (file server on `/srv/bp-status`), `/health` (version `0.1.0`), `/health/replication`.
- **Evidence:** `out_http_probe.txt`: full `desired_ref` and `running_ref` including the digest and `sha-9ace5bb`, deploy `generation` hash, `restore.result`, `updated_at`, `error`; `/health/replication` shows `generation`, `newest_object_at`, `age_seconds`.
- **Impact:** Tailnet peers learn the exact running commit and image digest (target selection), and whether a restore happened. No secrets.
- **Mitigation:** Keep the status JSON for the CI monitor but trim it to `state`, `generation`, and a short ref; or require a deploy token header at Caddy for that path. Alternatively accept (tailnet only) and record the decision in ADR-0111. Effort S.
- **Related:** D-§7 H4-4.

### H4-03 | Medium | Confirmed (presence) | security-control
- **Title:** The drill host holds prod-restore capability: prod replica read-only key and the age identity, root-only but root equals `operator`.
- **Locations:** `/etc/budget-planner/restore-source.env` (names `RESTORE_ACCESS_KEY_ID`, `RESTORE_SECRET_ACCESS_KEY`, mode 0600 root), `/etc/budget-planner/litestream-age.key` (0600 root; script header says it "must be the PROD replica's identity"), `/usr/local/bin/restore-from-prod` (installs only on drill), compose mounts of the age key into litestream, litestream-probe and litestream-restore containers.
- **Description:** In this run the box restored nothing from prod (Step 0), but anyone with `operator` SSH (passwordless sudo, docker group) can run `restore-from-prod` or read both secrets and decrypt the prod replica. Same root cause as H1-01. I read file names, permissions and the script header only; I did not read the key values nor test them against prod.
- **Impact:** SSH to an explore drill (reachable by `tag:ci`) yields the ability to restore and read prod data, on a host that is created ad hoc and whose lifetime is governed by a sweeper.
- **Mitigation:** Do not render `restore-source.env` or the prod age identity into explore drills; scope them to the `restore-drill` workflow environment and inject them for the single run, or use a separate drill-only age key plus a re-encrypted test replica. Effort M. **Related:** H1-01, H1-06, ADR-0105.

### H4-04 | Low | Confirmed | config-drift
- **Title:** Caddy and Litestream images are pinned by mutable tag in the compose file.
- **Locations:** rendered `docker-compose.yml` lines 60, 77, 102 (`litestream/litestream:0.3.14`), 122 (`caddy:2.8`); the app image is `tag@sha256`.
- **Evidence:** `out_host_probe2.txt`; running digests recorded: `caddy@sha256:226d1f05…`, `litestream@sha256:c5a1e1b0…` (`out_host_probe.txt`). D-10 confirmed.
- **Impact:** A rebuilt tag changes the proxy that terminates TLS and carries the CSP logic without a repo diff; `restore-drill` and prod could run different Caddy digests.
- **Mitigation:** Pin both by digest in `docker-compose.yml.tpl`; bump through a PR. Effort S.

### H4-05 | Low | Confirmed | security-control
- **Title:** Hardening is app-only; the other four containers are root with rw rootfs and no dropped capabilities; the edge network is flat.
- **Evidence:** `docker inspect`: app `user=10001 ro=true`; caddy, litestream, litestream-probe: `user= (root) ro=false caps_drop=[]`. From `litestream-probe`, `app:8000/health` is reachable. `no-new-privileges` is on at daemon level (`daemon.json`).
- **Impact:** A compromise of Caddy or a Litestream container (the latter hold bucket write keys and the age identity) gets root-in-container, with write access to the replica and no network segmentation to the app.
- **Mitigation:** Add `read_only`, `cap_drop: [ALL]`, `user:` where the images allow, and put the litestream services on a separate network from the app. Effort M.

### H4-06 | Low | Confirmed | infra-exposure
- **Title:** Initial admin password and cookie secret stay in the app container environment for the life of the container.
- **Evidence:** names `BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD`, `BUDGET_COOKIE_SECRET` in `docker inspect budget-planner-app` (values redacted in `out_host_probe.txt`). Audit row 1 shows `must_change_password: true` for the seeded admin.
- **Impact:** Readable by any `docker` group member; recurs in `bp-config`, Terraform state (D §7 H4-3). The password is only valid until the forced change, so the exposure is bounded, but the variable is not removed afterwards.
- **Mitigation:** Seed via a one-shot container or file that is removed, or drop the variable from the rendered compose after first login (host-agent generation bump). Effort S. **Related:** D-§7 H4-3.

## 5 · Notes (not findings)

- Public-IP exposure: published `0.0.0.0:443` bypasses ufw's `ufw allow 443 on tailscale0` because Docker writes DNAT before ufw's INPUT chain; the internet-side probe was filtered, so this is only defence in depth. If the provider security group ever opens 443, the drill (and a replaced prod host) would be public. Worth binding the published port to the tailscale IP (`100.x:443:443`) rather than relying on the SG.
- The prod-only `DOCKER-USER -d 169.254.42.42 -j DROP` rule works: the app container cannot reach metadata.
- Probes wrote three rows to the drill DB (failed-login audit and rate-limit rows, `h4probe@example.invalid`); a temporary `/tmp/h4_bucket_probe.py` on the host was removed.

## 6 · Questions

1. What does Caddy return when the app is down (502 page, headers, CSP)? Needs a controlled app stop on a throwaway drill.
2. Which MASQUERADE rule rewrites the tailnet source to the bridge gateway (`ts-postrouting` mark vs the `LOCAL` hairpin rules)? Needs `conntrack -E` or a packet capture on the drill.
3. What does tag:ci reach (ACL source is not in the repo)? The tailnet policy file should be versioned and tested for `tag:ci -> tag:prod:22` (H1-01).
4. Is the age identity on the drill really the prod identity (script header says yes)? Compare the public recipient with the prod recipient in a context that may touch prod config.
5. Are `/docs` and `/openapi.json` served to an authenticated session in production (D-12)? Needs a login on a drill.

## 7 · Repro index (`docs/plans/quality-audit/repro/H4/`)

`h4_http_probe.sh`/`out_http_probe.txt`, `h4_net_probe.sh`/`out_net_probe.txt`, `h4_host_probe.sh`/`out_host_probe.txt`, `h4_host_probe2.sh`/`out_host_probe2.txt`, `h4_xff_probe.sh` + `h4_xff_readback.py`/`out_xff_probe.txt`, `h4_error_path.sh`/`out_error_path.txt`, `h4_bucket_probe.py` + `h4_bucket_run.sh`/`out_bucket_probe.txt`, `out_nat.txt`. All target the drill only; scripts redact secret values at source.
