# ADR-0101: Drill Environment Is Tailnet-Only; Drill Apply Is Human-Gated

- **Status**: Accepted
- **Date**: 2026-11-07
- **Relates to**: ADR-0035, ADR-0036, ADR-0092, ADR-0094, ADR-0099, ADR-0100
- **Amends**: ADR-0092 (drill DNS), ADR-0099 (drill smoke, drill environment), ADR-0100 (ci-drill permissions). Nothing is superseded.

## Context

The drill VM is a throwaway copy of the app that runs arbitrary feature branches and restores a copy of prod data (restore drill). Until now it was public: an A/AAAA record `drill.budget.<domain>` in the prod project's DNS zone, security-group ports 80/443 open, a Let's Encrypt certificate for the public name, and a smoke test from a GitHub-hosted runner. Consequences:

- Anything on a feature branch is reachable from the internet.
- `ci-drill` needs `DomainsDNSFullAccess` on the **prod** project (Scaleway cannot scope DNS permissions to one zone), which is a prod-blast-radius permission held by an environment that any `*-deploy` branch can use.
- Any push to a `*-deploy` branch or any PR applied infrastructure without a human in the loop.

SSH is already tailnet-only (ADR-0094); the web UI should follow.

## Decision

### 1. Drill is reachable over Tailscale only

- **No public DNS.** `module.dns` is instantiated for `prod` only (`count = var.env == "prod" ? 1 : 0`, with a `moved` block so prod state is unaffected). Drill creates no records.
- **No public HTTP(S).** The compute security group opens 80/tcp, 443/tcp and 443/udp only when `public_web = true` (prod). Drill has no public inbound rule except the optional, temporary `break_glass_ssh_cidrs` (unchanged, ADR-0094). Host `ufw` for drill allows 443/tcp only on `tailscale0`.
- **Hostname = MagicDNS name.** Terraform variable `tailnet_dns_name` (e.g. `tail1234.ts.net`, not a secret, validated as `<label>.ts.net`, required when `env = drill`, rejected on prod) yields the drill FQDN `budget-planner-drill.<tailnet_dns_name>` (the VM's tailnet hostname is already `budget-planner-drill`). Prod keeps `<subdomain>.<domain>`. `BUDGET_TRUSTED_HOSTS` follows the same FQDN.
- **TLS from tailscaled.** Caddy serves the `*.ts.net` name and obtains its certificate from the local `tailscaled` through its socket (Caddy has native Tailscale certificate support for `*.ts.net` names, no ACME account or public reachability needed). On drill only, the compose file mounts `/var/run/tailscale` (the directory that holds `tailscaled.sock`, so a tailscaled restart does not leave a stale bind mount) into the Caddy container, publishes 443/tcp+udp only, and the Caddyfile drops the global ACME `email` and the port-80 redirect site. The official Caddy image runs as root, which tailscaled accepts for certificate requests; `TS_PERMIT_CERT_UID` is only needed if Caddy is ever run as a non-root user. Security headers, CSP nonce, rate limit and log filter are identical in both environments. Prod rendering is byte-identical to before.
- **ci-drill loses DNS.** `terraform/bootstrap/ci`: the `DomainsDNSFullAccess` rule on the prod project is removed from the `ci-drill` policy. `ci-prod` and `ci-plan` are untouched. `IAMManager` on `ci-drill` stays (separate pending decision, ADR-0100 alternatives).
- **Smoke from the tailnet.** The `smoke` job of `drill.yml` joins the tailnet as `tag:ci` (same `tailscale/github-action` pin and OAuth secrets as `deploy.yml`) and curls `https://budget-planner-drill.${TAILNET_DNS_NAME}/ready`. `TAILNET_DNS_NAME` is a GitHub environment variable; `vars.DRILL_URL` is no longer used by `drill.yml`. The tailnet ACL must allow `tag:ci -> tag:drill:443`.
- Operator prerequisites in the Tailscale admin console: MagicDNS enabled and HTTPS certificates enabled (otherwise `tailscale cert` and therefore Caddy fail). A stale node of the same name makes the new node register as `budget-planner-drill-1` and the certificate name would not match; drill nodes are ephemeral, so this clears itself within minutes of a destroy.

### 2. Drill apply is human-gated

- Every drill apply (push to `*-deploy`, `workflow_dispatch`, PR pre-merge) runs in GitHub environment `drill`, which has **Required reviewers**. Nothing is applied to the drill project until the owner approves.
- Everything that must never wait runs in ungated environments holding the same drill secrets and variables:
  - `drill-teardown`: every destroy path (`drill-sweeper.yml`, `drill-destroy.yml`, the `teardown` job of `drill.yml`), the sweeper's scan job and the smoke job (a second approval for the same run would be pointless).
  - `drill-plan`: the drill leg of the PR plan in `terraform.yml` (mirrors `prod-plan`, ADR-0093).
- `terraform.yml` selects the environment per job: plan -> `drill-plan`/`prod-plan`; apply with `destroy=true` -> `drill-teardown`; apply otherwise -> `<env>`. Prod destroy is not made ungated (a prod destroy through `terraform.yml` still uses environment `prod`).
- Because the gate protects only the apply, the single credential an unreviewed branch can use is the `drill-plan` one; it holds the same `ci-drill` key. This is accepted: that key is scoped to the drill project (and, after this ADR, no longer to prod DNS), and `drill-plan` and `drill-teardown` can only be reached by workflows already on the repository.
- Note: required reviewers on environments need GitHub Pro/Team for private repositories.

## Consequences

- Drill is invisible from the internet; a compromised feature branch cannot expose a public endpoint or reach prod DNS.
- Prod-project blast radius of the drill credential shrinks (no DNS write on prod).
- Drill needs a working tailnet: MagicDNS, HTTPS certificates, ACL rule `tag:ci -> tag:drill:443`, and the CI runner must join for smoke. Browsers need to be on the tailnet to use the drill UI.
- Every drill apply costs one approval click; teardown, sweeping and plan never wait.
- `restore-drill.yml`'s `/ready` probe moves to the MagicDNS name and passes `tailnet_dns_name` (minimal edit); `deploy.yml` and `rollback.yml` still read `vars.DRILL_URL`, which should now hold `https://budget-planner-drill.<tailnet>.ts.net`.
- Existing drill state has DNS records from earlier runs: the next drill destroy under the old credentials removes them; with the narrowed `ci-drill`, leftover records (if any) must be deleted by the operator (`scw dns record delete`, org admin).

## Alternatives considered

- **Keep public DNS but restrict by IP allow-list**: runner and operator IPs change; still public ACME and prod DNS permission. Rejected.
- **Tailscale Funnel / serve proxy instead of Caddy**: second TLS terminator with different headers; Caddy stays the one reverse proxy (ADR-0036). Rejected.
- **Internal CA / self-signed**: runner and browsers would need trust configuration. Rejected.
- **Gate only PR/branch pushes, not dispatch**: dispatch from a branch is exactly the path to run arbitrary code. Rejected; every trigger is gated.
