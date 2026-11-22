# ADR-0133: The Rate-Limit Identity Is the Proxy-Set Client Address; Attacker Text in `audit_log` Is Bounded

- **Status**: Accepted
- **Date**: 2026-11-21
- **Amends**: [ADR-0072](0072-auth-rate-limit-sqlite-fixed-window.md) §4 (client IP and trusted proxies)
- **Related**: T-Q203, Q-027 (D-06, H3-01, H3-05, H3-07, H2-04, H4-01), [ADR-0032](0032-v3-remote-deployment-scaleway-stardust-warsaw.md), [ADR-0036](0036-v3-reverse-proxy-caddy-auto-tls.md), OQ-25 (answered), OQ-30 (open)

## Context

ADR-0072 §4 trusted `X-Forwarded-For` because `--forwarded-allow-ips=*` was safe "while the app publishes no host port". The H3 and H4 tracks found three gaps:

1. `*` trusts the header from any peer, so the safety rests on one network fact instead of on configuration (H3-01).
2. The value uvicorn writes to `request.client` is never validated; arbitrary strings reach the counter key, `audit_log.ip` and `sessions.ip` (H3 R4, R8).
3. On the live drill every tailnet client reached Caddy as the Docker gateway `172.18.0.1` (H4-01, a `MASQUERADE` on the `edge` bridge, rule not isolated: OQ-30). The per-IP bucket was one bucket for everybody and the audit IP was useless.

Separately, throttled and failed logins wrote the full submitted email (200 kB accepted) and the full user agent to `audit_log` (H3-05).

## Decision

### 1. Identity is the proxy-set client address

- Caddy overwrites `X-Forwarded-For` and `X-Real-IP` with `{remote_host}` on every request (`header_up`, both Caddyfiles). Caddy is the first hop, so it must not trust inbound forwarded headers: `trusted_proxies` stays unset on purpose (an explicit overwrite, not a trust list).
- uvicorn trusts forwarded headers from **one pinned address**: `FORWARDED_ALLOW_IPS` (read by uvicorn; the `--forwarded-allow-ips=*` flag is removed). The Dockerfile default is `127.0.0.1`; each compose file sets the address of its proxy hop.
- The app never reads the header itself. `request.client.host` is passed through `domain.client_ip.parse_client_ip`: only a valid IPv4/IPv6 literal is accepted (canonical form); anything else is `None`, stored as NULL in `audit_log.ip`/`sessions.ip` and bucketed as `ip=unknown`.

### 2. Real-IP chain on the host (OQ-30)

Chosen: **Caddy uses host networking** (`network_mode: host`) in the production compose template. Tailnet and public clients then reach Caddy with their real source address (no bridge DNAT/MASQUERADE hop in front of Caddy). The app publishes `127.0.0.1:8000:8000` only (loopback, still no public exposure) and Caddy proxies to `127.0.0.1:8000`. The `edge` network gets a fixed subnet `172.28.0.0/24` (gateway `172.28.0.1`); the app sees Caddy's connection from the bridge gateway, so `FORWARDED_ALLOW_IPS=172.28.0.1`. This works without knowing which `MASQUERADE` rule is responsible, which is why it is preferred while OQ-30 is open.

Alternative (not chosen): keep Caddy on the bridge and remove the masquerade of the tailnet source (`ts-postrouting` mark rule versus the `LOCAL` hairpin rules) through `iptables`/daemon `--ip-masq` changes. It needs the OQ-30 answer (`conntrack -E` on a throwaway drill), is host-global and fragile across Docker/tailscale upgrades.

The prod-sim compose keeps Caddy on the bridge (no NAT in front of it locally) with a fixed Caddy address (`172.29.0.2`) pinned in `FORWARDED_ALLOW_IPS`.

Release check (operator, drill first): the drill smoke asserts `audit_log.ip` of a login is the client's `100.x` address, not a gateway address.

### 3. Buckets

Unchanged shape (ADR-0072 §2): password login is keyed on (IP, normalised email) with a global per-IP ceiling. With a real, validated IP, an attacker at another address can no longer burn the owner's bucket, and the identity can no longer be injected. Normalised email is capped at 254 characters in keys. A per-email bucket across IPs is deliberately **not** added: it would let any attacker lock a known user out from anywhere, the opposite of this ADR's goal.

### 4. Bounded attacker text

Text from the request that reaches `audit_log` is truncated by `domain.client_ip.bound_text`: email 254 characters (audit payloads and counter keys), user agent 256 characters. Output escaping stays with the templates (autoescape); values are stored as data, never as HTML.

## Consequences

- A forged `X-Forwarded-For` from any peer except the pinned proxy is ignored; junk addresses collapse to `unknown`.
- Caddy host networking changes the production compose and needs a drill before release; the app port binds to host loopback.
- Per-IP limits for peers without a usable address share the `ip=unknown` bucket.

## Amendment 2026-11-22 (T-Q305): the network is migrated by renaming, not by changing it in place

Release v3.1.0 failed on the live host: the `edge` network gained `ipam` (§2) and Compose cannot change the subnet of a network that already exists and has containers attached. `compose up` failed, and the automatic rollback to v3.0.8 failed identically because a rollback swaps only the image ref and keeps the new compose template. The drill gate passed because a drill is always a fresh host (see the ADR-0099 amendment of the same date).

Decision: the network is renamed `edge` -> `edge_v2` (Compose project `budget-planner`, so `budget-planner_edge_v2`). Compose creates the new network with the fixed subnet `172.28.0.0/24` and recreates every service (their `networks:` config changed). The old `budget-planner_edge` is left unused, and the agent removes it after a successful `up`, best effort (ignores "not found" and "in use"; ADR-0111 amendment).

Why rename over `compose down` before `up` (the alternative):

- `down` stops every service, including the app and litestream, on any detected spec change: a guaranteed outage and a replication gap, on the path that is meant to be a rolling convergence. Rename needs no spec-change detection (which is itself fragile).
- Rename works for the rollback path: the template that was just applied already names `edge_v2`, so the swapped image ref converges without touching the network.
- The cost is one orphan network until cleanup, and one fresh subnet; `172.28.0.0/24` does not overlap Docker's default pools in use (the old network sits in the default pool from `172.17.0.0/16`).
- Data volumes (`/data`, `caddy-data`, `caddy-config`) are untouched; `down -v` is never used.

Other in-place changes since v3.0.8 were reviewed and need no migration: Caddy's `network_mode: host` and the app's `127.0.0.1:8000` publish are applied by Compose recreating those containers (the old bridged Caddy releases 80/443 when it is stopped for recreation); the pinned image digests only change the image.

Rule going forward: a network's name must change whenever its definition changes (`tests/unit/deploy/test_compose_upgrade_in_place.py` compares against the latest `v*` tag).

Evidence (host journal of the first apply, 2026-11-22 20:39:06): `Network budget-planner_edge  Removed` followed by `Error response from daemon: error while removing network: network budget-planner_edge has active endpoints (name:"budget-planner-caddy" id:"<id>")`. Compose replaces the network before the containers that use it, and the old bridged Caddy was still attached. Every later attempt, including the v3.0.8 image rollback on the new template, failed with `container <id> is not connected to the network budget-planner_edge` (app, litestream and probe exited; old Caddy up, publishing 80/443; `budget-planner_edge` on `172.18.0.0/16`, one endpoint).

Recovery and port handover (agent, ADR-0111 amendment): before `up` the agent removes a Caddy whose `HostConfig.NetworkMode` is not `host` (releases the docker-proxy on 80/443; certificates live in named volumes, untouched). If `up` fails it runs `compose rm --force --stop` once (containers only: never `-v`, never `down`; containers hold no state) and retries, so a host already half-migrated by the v3.1.0 attempt converges too.
