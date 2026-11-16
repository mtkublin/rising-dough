# T-D23 — Cloud-init templates

- **Phase**: 2 — Infrastructure
- **Sequential**: must land after T-D21 (IAM + storage, provides credentials for template inputs); blocks T-D24
- **Depends on**: T-D05 (SQLite PRAGMAs), T-D10 (Dockerfile), T-D11 (docker-compose), T-D21 (bucket + IAM)
- **References**: ADR-0035 §5, ADR-0034, ADR-0036

## Context

The Scaleway instance is provisioned with Ubuntu 24.04 minimal. All in-VM configuration happens via cloud-init user-data rendered by Terraform. The template is responsible for creating users, installing packages, writing the docker-compose + Caddyfile + litestream config, mounting `/data`, wiring firewalls, enabling automatic security updates, and bringing the stack up on first boot.

## Deliverables

### `terraform/cloud-init/bootstrap.yaml.tpl`

Templated inputs (Terraform `templatefile(...)`):
- `hostname` — public DNS name.
- `app_image_tag` — e.g. `sha-abc1234`; the first-boot image to pull.
- `bucket_name`, `bucket_endpoint`, `bucket_region`.
- `scw_access_key`, `scw_secret_key` — IAM credential scoped to the bucket (sensitive).
- `github_deploy_pubkey` — ed25519 public key for the `deploy` user.
- `operator_ssh_pubkey` — operator's personal key for the `app` user.
- `ghcr_pull_pat` — read-only GHCR PAT for pulling the private image.
- `admin_fallback_bcrypt_hash` — pre-hashed fallback password (ADR-0033 §2) injected into the DB on first boot via a migration seed.

Shape (abbreviated; final version is the authoritative one in the repo):

```yaml
#cloud-config
hostname: ${hostname}
preserve_hostname: false

package_update: true
package_upgrade: true
packages:
  - docker.io
  - docker-compose-plugin
  - ufw
  - fail2ban
  - unattended-upgrades
  - needrestart

users:
  - name: app
    uid: 10001
    shell: /usr/sbin/nologin
    lock_passwd: true
  - name: deploy
    uid: 10002
    shell: /usr/sbin/nologin
    lock_passwd: true
    ssh_authorized_keys:
      - 'command="/usr/local/bin/deploy-budget-planner",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ${github_deploy_pubkey}'
  - name: operator
    sudo: ['ALL=(ALL) NOPASSWD:ALL']
    groups: [sudo, docker]
    shell: /bin/bash
    ssh_authorized_keys:
      - '${operator_ssh_pubkey}'

write_files:
  - path: /etc/budget-planner/docker-compose.yml
    permissions: '0600'
    owner: root:root
    content: |
      ${indent(6, docker_compose_rendered)}
  - path: /etc/budget-planner/Caddyfile
    permissions: '0600'
    owner: root:root
    content: |
      ${indent(6, caddyfile_rendered)}
  - path: /etc/budget-planner/litestream.yml
    permissions: '0600'
    owner: root:root
    content: |
      ${indent(6, litestream_rendered)}
  - path: /etc/budget-planner/litestream.env
    permissions: '0600'
    owner: root:root
    content: |
      SCW_ACCESS_KEY=${scw_access_key}
      SCW_SECRET_KEY=${scw_secret_key}
  - path: /etc/docker/config.json
    permissions: '0600'
    owner: root:root
    content: |
      ${jsonencode({ auths = { "ghcr.io" = { auth = base64encode("deploy:${ghcr_pull_pat}") } } })}
  - path: /usr/local/bin/deploy-budget-planner
    permissions: '0755'
    owner: root:root
    content: |
      ${indent(6, deploy_script_rendered)}
  - path: /etc/apt/apt.conf.d/50unattended-upgrades
    content: |
      Unattended-Upgrade::Allowed-Origins { "Ubuntu:${distro}-security"; };
      Unattended-Upgrade::Automatic-Reboot "true";
      Unattended-Upgrade::Automatic-Reboot-Time "04:00";

runcmd:
  - mkdir -p /data && chown 10001:10001 /data && chmod 700 /data
  - mkdir -p /var/log/caddy && chown root:root /var/log/caddy && chmod 755 /var/log/caddy
  - ufw default deny incoming
  - ufw default allow outgoing
  - ufw allow in on tailscale0 to any port 22 proto tcp   # T-D71 (was 22/tcp)
  - ufw allow 80/tcp
  - ufw allow 443/tcp
  - ufw --force enable
  - systemctl enable --now unattended-upgrades
  - systemctl enable --now docker
  - docker --config /etc/docker login ghcr.io -u deploy -p ${ghcr_pull_pat}
  - (cd /etc/budget-planner && IMAGE_TAG=${app_image_tag} docker compose pull && IMAGE_TAG=${app_image_tag} docker compose up -d)
  - # Wait for app /ready, 60s budget
  - for i in $(seq 1 60); do curl -fsS https://localhost/ready -k && break; sleep 1; done
```

### `terraform/cloud-init/compose/docker-compose.yml.tpl`
See ADR-0032 §2 for the three-service shape; template inputs: `IMAGE_TAG`, `hostname`.

### `terraform/cloud-init/compose/Caddyfile.tpl`
Exact shape from ADR-0036 §1; template input: `hostname`.

### `terraform/cloud-init/compose/litestream.yml.tpl`
Exact shape from ADR-0034 §3; template inputs: `bucket_name`, `bucket_endpoint`, `bucket_region`.

### `terraform/cloud-init/scripts/deploy-budget-planner.sh.tpl`
Exact shape from ADR-0037 §3; template input: `owner` (GitHub owner).

### Linting / validation step

In CI (T-D28), after `terraform plan` writes the rendered templates to a scratch dir:
- `yq -e . docker-compose.yml` — valid YAML.
- `caddy validate --config Caddyfile` (via a one-shot container).
- `litestream version` + `litestream replicate -dry-run -config litestream.yml` (via a one-shot container).

## Acceptance criteria

- `terraform plan` on the `drill` env produces a plan containing `scaleway_instance_server` with the expected `user_data` payload (verified by `terraform show -json | jq`).
- Rendered templates pass the three linters above.
- Running cloud-init on the `drill` instance ends with `/var/log/cloud-init-output.log` containing a `/ready` 200 line and no `ERROR` entries.

## Validation hook

```sh
cd terraform
terraform plan -var-file=envs/drill/terraform.tfvars -out=/tmp/drill.plan
terraform show -json /tmp/drill.plan | jq -r '.planned_values.root_module.resources[] | select(.type=="scaleway_instance_server") | .values.user_data' > /tmp/userdata.yaml
yq -e . /tmp/userdata.yaml
```
