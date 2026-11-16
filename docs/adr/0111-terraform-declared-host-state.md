# ADR-0111: Terraform-Declared Host State, Pulled by a Host Agent

- **Status**: Accepted
- **Date**: 2026-11-16
- **Relates to**: ADR-0032 (compute), ADR-0094 (Tailscale-only SSH), ADR-0098 (cloud-init runs once), ADR-0099 (release policy), ADR-0100 (credential split), ADR-0109 (release trigger), T-D127, T-D129
- **Supersedes**: ADR-0037 §deploy step (SSH forced-command deploy); ADR-0110 (the `prod-deploy` environment is no longer needed: there is no deploy job)
- **Amends**: ADR-0099 (a release is one approved `terraform apply`)

## Context

The first pipeline release (run 43913941966, 2026-11-16) applied Terraform cleanly, then `deploy-prod` failed. The SSH deploy path had never run for real (drills boot a fresh VM through cloud-init and skip it), and it had four defects, each hidden by the one before:

1. The forced command did not split `SSH_ORIGINAL_COMMAND` (strict-mode IFS). Fixed by T-D127.
2. The `deploy` user could not write its tag files into root-owned `/etc/budget-planner`.
3. The compose file pins the image tag at render time, so `TAG=… docker compose up` re-ran the old image and would have reported success.
4. No cosign verification on the host, although ADR-0037 and `deploy.yml` say there is.

The release image went to prod by a logged break-glass (operator, digest-pinned, signature verified on the laptop).

More generally, everything cloud-init writes (compose file, Caddyfile, Litestream config, scripts) is frozen at first boot. Any later change needs a VM replace (downtime: STARDUST1-S quota is 1, so no create-before-destroy) or a hand edit on the host.

## Decision

Terraform declares the complete host state; a small agent on the host converges to it. Nothing pushes into the host.

1. **Desired state in instance metadata.** `scaleway_instance_server.user_data` (a map, updated in place, no reboot) carries, besides the minimal `cloud-init` key:
   - `bp-agent`: the agent program (Python 3 stdlib, versioned in `terraform/host/agent/`).
   - `bp-config`: one JSON document: every managed file (path, mode, owner, content, services that must restart when it changes), the app image ref (`tag@sha256:digest`), the previous ref, the cosign verification policy (pinned cosign version and checksum, certificate identity regexp, OIDC issuer) and a `generation` hash of all of it.
   Both are wrapped in `sensitive()`; secrets in files already lived in cloud-init user data, so exposure on the host is unchanged.
2. **Fixed bootstrap only in cloud-init.** cloud-init keeps what must exist before the agent can run (users, SSH, Tailscale join, Docker, swap, ufw) plus a loader, a systemd service and a timer (every 30 s). The loader fetches `bp-agent` from the metadata API (privileged source port, root only) and runs it. The loader is the only host code that needs a VM replace or a logged host edit to change.
3. **Agent behaviour.** Fetch `bp-config`. If `generation` equals the last applied one, and the app container runs the desired digest, exit. Otherwise:
   - install the pinned cosign if missing (checksum verified);
   - `cosign verify` the image ref against the policy; on failure change nothing, report `failed`;
   - write changed files atomically; `docker compose pull` + `up -d`; restart services whose mounted files changed;
   - probe `/ready` locally; report `ok` or `failed`;
   - a failed generation is retried with back-off, not in a tight loop.
   The agent never edits `bp-config`; on failure Terraform (CI) decides.
4. **Status.** The agent writes `status.json` (generation, desired ref, running digest from `docker inspect`, state, terse error code, time), which Caddy serves at `/.well-known/bp-deploy-status.json`. No secrets, no paths; the repo and image tags are public.
5. **Release = one apply.** CI reads the current ref from state (`terraform output -raw app_image_ref`) and passes it as `app_image_previous_ref`, and passes the new ref (`tag@digest` from `build.yml`). The approved apply job then monitors: it polls the status until `generation` and running digest match (timeout), and on failure re-applies with the refs swapped in the same, already approved job. Rollback (`rollback.yml`) is an apply with explicit refs.
6. **Container isolation from metadata.** A `DOCKER-USER` iptables rule (in the fixed bootstrap) drops container traffic to `169.254.42.42`. Docker grants `NET_BIND_SERVICE` by default, so a root container (Caddy) could otherwise read every secret in user data. This closes an exposure that already exists today.
7. **Removed.** `deploy.yml`, the `deploy` user, its key and forced command, `deploy-budget-planner`, the `prod-deploy` environment and its secrets (`DEPLOY_SSH_*`, `PROD_HOST` where only deploy used it).

## Consequences

- Every host change (image, compose, Caddy, Litestream, agent) is a reviewed plan and one approval. The plan shows the image digest change.
- Drill gates exercise the same agent path that prod releases use (drills previously skipped the deploy path entirely).
- No inbound deploy credential exists: the Terraform identity never touches the host, and CI holds no SSH key for prod.
- Convergence is asynchronous (seconds to a minute); the monitor makes the release wait for it.
- Prod needs one last logged host change to install the loader, timer and firewall rule and remove the `deploy` user (runbook in T-D129). After that, no hand edits.
- Open checks for the first drill: an updated metadata key is served live without a reboot; the size limit per key holds the config bundle.

## Alternatives considered

- **Fix the SSH deploy (T-D127 + state dir + compose `${APP_TAG}` + cosign on host).** Works, but keeps a second, push-based path next to Terraform, and every non-image change still needs a VM replace or hand edit.
- **Replace the VM on every release.** Quota 1 means downtime and no fallback VM; Let's Encrypt duplicate-certificate limit (5/week).
- **Terraform `remote-exec` provisioner.** Provisioners are a last resort (tainted resources on failure), and the prod Terraform identity would also need root SSH on the host, breaking the ADR-0100 split.
