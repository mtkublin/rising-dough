# Runbook: SSH over Tailscale (T-D67, ADR-0094)

## Context

Port 22 is closed on the Scaleway security group of both `drill` and `prod`. Operator and CI reach sshd only through the tailnet, using MagicDNS names `budget-planner-prod` and `budget-planner-drill`. The app stays public on 80/443; app users never need Tailscale.

## Preconditions

- Tailscale account (Personal plan), Tailscale app installed and logged in on your machine.
- Operator checklist A9 done (ACL pasted, OAuth client created, GitHub secrets set).

## Procedure

### 1. Paste the ACL

1. Open the admin console, Access controls.
2. Replace the contents with `tailscale-acl.hujson` (same folder), setting `you@example.com` to your login email.
3. Save. The editor validates the policy and its tests. Only your devices and `tag:ci` may reach `tag:prod` / `tag:drill` on port 22.

The ACL is deliberately not in Terraform (tailnet-global; two env states would both own it, same trap as ADR-0088).

### 2. Day-to-day SSH

```sh
ssh operator@budget-planner-prod
ssh deploy@budget-planner-prod "rollback"   # restricted deploy user, see rollback.md
```

### 3. Host keys over the tailnet

From a device on the tailnet:

```sh
ssh-keyscan -t ed25519,ecdsa,rsa budget-planner-prod
```

Store the output as the GitHub secret `DEPLOY_SSH_KNOWN_HOSTS`. The peer is authenticated by its WireGuard node key and the ACL, so this scan is trustworthy. The drill host has fresh host keys on every run; `restore-drill.yml` scans them at runtime. `DEPLOY_SSH_KNOWN_HOSTS_DRILL` is obsolete.

### 4. Rotating the OAuth client

Create a new client (scope Auth Keys: write, tags `tag:prod`, `tag:drill`, `tag:ci`), update `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_SECRET` in GitHub and your local `TF_VAR_tailscale_oauth_*`, then delete the old client. Running nodes are unaffected; the client is only used to mint keys.

## Verification

- `tailscale status` lists `budget-planner-prod` (tag:prod).
- `ssh operator@budget-planner-prod true` succeeds; from a public network without Tailscale, `nc -zv <vm-public-ip> 22` times out.

## Troubleshooting

- **Name does not resolve**: MagicDNS off or Tailscale not running; use `tailscale ip -4 budget-planner-prod`.
- **Drill node named `budget-planner-drill-1`**: a destroyed ephemeral node was not yet garbage-collected. Delete the stale machine in the admin console (or wait) and re-run.
- **Node never joined** (first boot): the auth key lives 1 h and is single-use. Check `sudo tail /var/log/cloud-init-output.log` through break-glass below, then re-apply with `terraform apply -replace=tailscale_tailnet_key.vm -replace=module.compute.scaleway_instance_server.app` (replaces the VM; data restores from Litestream).

## Break-glass (Tailscale unreachable)

Open port 22 for your current IP only, fix, close again. Find the group and your IP:

```sh
SG_ID=$(scw instance security-group list zone=pl-waw-2 name=budget-planner-prod-sg -o json | jq -r '.[0].id')
MY_IP=$(curl -fsS https://api.ipify.org)
scw instance security-group create-rule security-group-id="$SG_ID" zone=pl-waw-2 \
  protocol=TCP direction=inbound action=accept dest-port-from=22 ip-range="${MY_IP}/32"
ssh operator@<vm-public-ip>
```

When done, remove the rule:

```sh
scw instance security-group list-rules security-group-id="$SG_ID" zone=pl-waw-2
scw instance security-group delete-rule security-group-id="$SG_ID" security-group-rule-id=<rule-id> zone=pl-waw-2
```

Use `budget-planner-drill-sg` for the drill env. The Scaleway web serial console shows boot and cloud-init output for diagnosis but is not a login path (account passwords are locked). Do not leave the rule in place; a later `terraform apply` also removes it (drift).

## Rollback

Reverting ADR-0094 means re-adding the `22/tcp` inbound rule in `modules/compute/main.tf` and applying.
