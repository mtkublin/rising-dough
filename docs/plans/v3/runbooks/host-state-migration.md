# Runbook — Migrate prod to Terraform-declared host state (one-time, ADR-0111, T-D129f)

> **SSH access (ADR-0094):** join the tailnet and use the MagicDNS name `budget-planner-prod`. Every command below is a single line (multi-line input after `ssh` is lost).

## Context

ADR-0111 moves every release into one approved `terraform apply`: the instance metadata (`user_data` keys `cloud-init`, `bp-agent`, `bp-config`) declares the host state and a host agent (`bp-converge.timer`, every 30 s) converges to it. New VMs get the agent bootstrap from cloud-init. The current prod VM booted before ADR-0111, and cloud-init never runs again on it, so the bootstrap (agent loader, `bp-converge.service` + `.timer`, `bp-metadata-guard.service`) is installed once by hand. Without it, the first release would apply the metadata and then wait for a status that never comes.

This is a logged break-glass host change (ADR-0099 exception list): explicit user go, and a `docs/CHANGELOG.md` entry. It does not touch the database or the running containers.

## Preconditions

- The T-D129 change is on `main`, and its PR had a green `drill-gate`. The drill boots a fresh VM through the new path: agent converges, cosign verifies, `/ready` and the status file report the generation.
- The PR's `plan (prod)` shows `scaleway_instance_server.app` **updated in-place** (`user_data`), with no replacement. Before the first new-style apply the plan uses a placeholder image ref (`sha-0000000@sha256:000…`); that is expected for a plan that is never applied.
- Optional, recommended: an explore drill (`gh workflow run drill.yml -f mode=explore -f keep=true`) followed by `gh workflow run rollback.yml --ref main -f env=drill -f target=<older sha-tag>`. This checks the two things a fresh boot cannot: a metadata update is served to the running VM without a reboot, and the agent converges to it.
- Prod is healthy: `curl -fsS https://budget.rising-dough.eu/ready | jq .`.

## Procedure

1. Install the bootstrap and remove the SSH deploy path (from a checkout of the merged `main`):
   ```sh
   ssh operator@budget-planner-prod 'sudo bash -s' < terraform/host/migrate/adr-0111-install-agent.sh
   ```
   Expect `bp-agent bootstrap installed; deploy path removed`. The script is idempotent; its unit and loader bodies are byte-identical to `terraform/cloud-init/bootstrap.yaml.tpl` (tested). Until step 2 the agent reports `config_fetch` failures every 30 s (`bp-config` does not exist in the metadata yet). It changes nothing on the host while it does.
2. Check the agent and the guard:
   ```sh
   ssh operator@budget-planner-prod 'systemctl is-active bp-converge.timer bp-metadata-guard.service; sudo iptables -C DOCKER-USER -d 169.254.42.42/32 -j DROP && echo guard-ok; sudo journalctl -u bp-converge.service -n 5 --no-pager'
   ```
3. Cut the next release ([`deploy.md`](deploy.md) step 0) and approve `prod` once. The apply writes `bp-config`. Within ~30 s the agent cosign-verifies the image, rewrites the compose file, Caddyfile, Litestream config and registry auth, recreates the containers and probes `/ready`. The job waits for `/.well-known/bp-deploy-status.json` to report the generation.
   - State holds no previous ref yet, so this first release has **no automatic rollback**. If it fails, roll back explicitly to the image prod ran before: `gh workflow run rollback.yml --ref main -f env=prod -f target=<previous release or sha-tag>` (the break-glass release on 2026-11-16 was `sha-89ac3c2`).
4. Verify:
   ```sh
   curl -fsS https://budget.rising-dough.eu/.well-known/bp-deploy-status.json | jq .
   ssh operator@budget-planner-prod 'id deploy 2>&1; ls -l /usr/local/bin/deploy-budget-planner 2>&1; sudo ls -l /etc/budget-planner/'
   ```
   Expect state `ok` with the release ref, `no such user`, no deploy script, and the compose file at `root:root 0600`.
5. GitHub cleanup ([`github-settings.md`](github-settings.md)): delete the `prod-deploy` environment; delete `DEPLOY_SSH_PUBKEY` (all envs), `DEPLOY_SSH_KNOWN_HOSTS` and `PROD_HOST`, plus the variables `PROD_URL` and `DRILL_URL`. Remove the deploy public key from the password manager entry (its private half is useless now).
6. Log it: a dated `docs/CHANGELOG.md` line (`ops(T-D129f): prod migrated to ADR-0111 host agent; deploy user removed`), and tick T-D129f in `docs/plans/v3/tasks.md`.

## Rollback of the migration

There is no way back to the SSH deploy path; `deploy.yml` and the deploy user are gone. If the agent misbehaves, stop it (`ssh operator@budget-planner-prod 'sudo systemctl disable --now bp-converge.timer'`). The containers keep running as they are; fix forward with a new release.
