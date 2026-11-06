# ADR-0094: SSH Only Over Tailscale; Port 22 Closed to the Internet

- **Status**: Accepted
- **Date**: 2026-11-06
- **Amends**: [ADR-0035](0035-v3-infrastructure-as-code-terraform.md) (security group `22/80/443`, firewall step), [ADR-0032](0032-v3-remote-deployment-scaleway-stardust-warsaw.md)
- **Related**: [ADR-0037](0037-v3-github-actions-deploy-pipeline.md) (deploy SSH), [ADR-0069](0069-admin-bootstrap-env-policy-and-operator-cli.md) (secret-file pattern), [ADR-0088](0088-dns-zone-not-owned-by-env-state.md) (tailnet-global resource not owned by env state), T-D67

## Context

1. Inbound TCP 22 was open to `0.0.0.0/0` on the security group and in `ufw` (all interfaces). Even with key-only auth this exposes sshd to scanners, `fail2ban` noise and any future sshd CVE.
2. The app itself must stay public on 80/443 (TCP) and 443 (UDP, HTTP/3) through Caddy. Only admin/CI traffic (operator SSH, GitHub Actions deploy/rollback/restore-drill) needs a private path.
3. Operator decision (2026-11-06): use Tailscale (Personal plan, free) for SSH/admin only. App users never need Tailscale.
4. The tailnet ACL is tailnet-global. If both the `drill` and `prod` Terraform states managed it, they would fight over one object (the same trap as the DNS zone, ADR-0088).

## Decision

1. **Security group** (`modules/compute`): remove inbound TCP 22. Keep default-drop inbound plus 80/tcp, 443/tcp, 443/udp. Inbound UDP 41641 (Tailscale direct path) is deliberately **not** opened: Tailscale works outbound-only through NAT traversal and DERP relays (outbound policy is `accept`), and a direct path is only a latency optimisation for an admin shell. Fewer open ports wins.
2. **Host firewall** (amended by T-D71): `ufw allow in on tailscale0 to any port 22 proto tcp` replaces `ufw allow 22/tcp`, so host SSH is reachable only on the Tailscale interface (defence in depth behind the security group). Rules by interface name are valid before `tailscale0` exists; `ufw --force enable` runs after them. Break-glass (item 7) now also needs a temporary `ufw allow 22/tcp` on the host, which has no console login, so break-glass is effectively limited to hosts already reachable by other means; accepted trade-off.
3. **VM join** (Terraform + cloud-init):
   - Root module configures the `tailscale/tailscale` provider with an OAuth client (`tailscale_oauth_client_id` / `tailscale_oauth_client_secret`, sensitive, supplied via `TF_VAR_*`; `scopes = ["auth_keys"]`). `tailnet` is omitted: per provider docs it defaults to the tailnet owning the credentials.
   - `tailscale_tailnet_key.vm`: `preauthorized = true`, `reusable = false`, `tags = ["tag:<env>"]`, `ephemeral = (env == "drill")`, `expiry = 3600`. Prod stays a normal (non-ephemeral) node; drill nodes are removed from the tailnet automatically after they go offline, so the monthly destroy leaves nothing behind.
   - The key is passed to cloud-init as a sensitive input and written to `/run/tailscale-authkey` (tmpfs, `0600 root`, ADR-0069 secret-file pattern). `tailscale up --auth-key=file:/run/tailscale-authkey --hostname=budget-planner-<env> --advertise-tags=tag:<env> --accept-dns=false` reads it from the file (`file:` prefix supported by the CLI), and the same `runcmd` removes it afterwards. The key is single-use and expires in 1 h, so the copy that remains in cloud-init `user-data` (like every other secret rendered there) is inert after first boot.
   - Tailscale is installed from the official apt repo (`pkgs.tailscale.com/stable/ubuntu`, `noble`). **No Tailscale SSH**: normal sshd stays, key-only, users `operator` and the restricted `deploy` are unchanged.
   - Output `tailscale_hostname` (`budget-planner-<env>`, the MagicDNS name). No `tailscale_device` data lookup: the name is deterministic.
4. **ACL not managed in env state.** The intended policy is committed as `docs/plans/v3/runbooks/tailscale-acl.hujson` and pasted by the operator in the admin console (runbook `tailscale-ssh.md`). It defines `tagOwners` for `tag:prod`, `tag:drill`, `tag:ci` and allows only: operator's own devices to `tag:prod,tag:drill` on 22, and `tag:ci` to `tag:prod,tag:drill` on 22.
5. **CI**: `deploy.yml`, `rollback.yml`, `restore-drill.yml` add `tailscale/github-action` (pinned to a commit SHA) with `oauth-client-id`, `oauth-secret`, `tags: tag:ci` before the first SSH. `DRILL_HOST` / `PROD_HOST` secrets (deploy, rollback) now hold the tailnet names `budget-planner-drill` / `budget-planner-prod`. In `restore-drill.yml`, public `DRILL_HOST` stays for the HTTPS `/ready` probe and a new `DRILL_SSH_HOST=budget-planner-drill` is used for SSH. The drill host joins the tailnet during apply, so a bounded wait (60 x 10 s) polls `ssh-keyscan` until the name answers on 22, and records the host keys. `terraform.yml` plan jobs also receive `TF_VAR_tailscale_oauth_*` because the variables are required.
6. **Host keys over the tailnet.** `known_hosts` entries are produced with `ssh-keyscan -t ed25519,ecdsa,rsa budget-planner-<env>` from a device on the tailnet. The peer is authenticated by its WireGuard node key and ACL, so this is not an internet trust-on-first-use. Prod: run once from the operator laptop and store the output as `DEPLOY_SSH_KNOWN_HOSTS`. Drill: scanned at runtime (a new host key every run).
7. **Break-glass** (Tailscale outage, expired/lost OAuth client, broken `tailscaled`): temporarily add a port-22 inbound rule for the operator's current IP to the VM security group with `scw` (exact commands in the runbook), SSH as `operator` with the existing key, fix Tailscale, then remove the rule. The Scaleway serial console is not a login path (passwords are locked) but shows boot/cloud-init output for diagnosis. Last resort: `terraform apply -replace` the VM and restore from Litestream (disaster-recovery runbook).

## Evidence (verified 2026-11-06)

- `tailscale/terraform-provider-tailscale` v0.29.3 (`docs/index.md`): provider args `oauth_client_id`, `oauth_client_secret` (sensitive), `scopes`, `tailnet` (optional, defaults to the credentials' tailnet). `docs/resources/tailnet_key.md`: args `reusable`, `ephemeral`, `preauthorized`, `expiry` (seconds), `tags`, `description`; read-only sensitive `key`. Constraint `~> 0.29`.
- `tailscale/github-action` v4.4.0 = commit `064b10558093f38325e838ddea35486bdc6b1d5c` (`action.yml`): inputs `oauth-client-id`, `oauth-secret`, `tags` (OAuth client needs `auth_keys` scope and must own the tags), `ping`, `timeout`, `retry`; the `post:` step logs the node out. <!-- pragma: allowlist secret -->
- Tailscale CLI source (`cmd/tailscale/cli/up.go`): `--auth-key`: "if it begins with `file:`, then it's a path to a file containing the authkey".
- `pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg` and `noble.tailscale-keyring.list` exist (HTTP 200).
- `terraform validate` on Terraform 1.17.1 with the provider downloaded: valid.

## Consequences

- sshd is invisible to the internet; the only public surface is Caddy on 80/443.
- Operator and CI need Tailscale. Admin access depends on the Tailscale control plane and DERP availability (break-glass above).
- Tailscale becomes a new trust dependency: the OAuth client (scope `auth_keys`, tags only) can mint node keys but cannot read or write the ACL. Treat `TS_OAUTH_SECRET` like `DEPLOY_SSH_PRIVATE_KEY`.
- Hostname collision risk: if a destroyed ephemeral drill node has not yet been garbage-collected, a new `budget-planner-drill` registers as `budget-planner-drill-1`; the bounded wait would then time out or reach the stale entry and fail safely (destroy still runs, T-D66). Re-run later.
- Optional hardening (operator choice): Tailnet Lock.
- `DEPLOY_SSH_KNOWN_HOSTS_DRILL` is obsolete.
