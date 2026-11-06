## NOTE: rendered via cloud-init by Terraform. Edits must happen in the .tpl.
## ADR-0035 §5: first-boot sequence (packages, users, templates, firewall, compose up).

#cloud-config
hostname: ${hostname}
preserve_hostname: false
fqdn: ${hostname}
manage_etc_hosts: true

package_update: true
package_upgrade: true
packages:
  - ca-certificates
  - curl
  - jq
  - sqlite3
  - docker.io
  - docker-compose-v2
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
    shell: /bin/bash
    lock_passwd: true
    ssh_authorized_keys:
      - 'command="/usr/local/bin/deploy-budget-planner",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ${github_deploy_pubkey}'
  - name: operator
    sudo: ["ALL=(ALL) NOPASSWD:ALL"]
    groups: [sudo, docker]
    shell: /bin/bash
    lock_passwd: true
    ssh_authorized_keys:
      - '${operator_ssh_pubkey}'

write_files:
  - path: /etc/budget-planner/docker-compose.yml
    permissions: '0640'
    owner: root:docker
    content: |
      ${indent(6, docker_compose_rendered)}

  - path: /etc/budget-planner/Caddyfile
    permissions: '0644'
    owner: root:root
    content: |
      ${indent(6, caddyfile_rendered)}

  - path: /etc/budget-planner/litestream.yml
    permissions: '0644'
    owner: root:root
    content: |
      ${indent(6, litestream_rendered)}

  # T-D56 / ADR-0078 §3: restore-only config + age identity (ADR-0069 secret-file pattern).
  # Lost identity = unrecoverable replica; the operator keeps the master copy in the password manager.
  - path: /etc/budget-planner/litestream-restore.yml
    permissions: '0644'
    owner: root:root
    content: |
      ${indent(6, litestream_restore_rendered)}

  - path: /etc/budget-planner/litestream-age.key
    permissions: '0600'
    owner: root:root
    content: |
      ${indent(6, age_identity)}

  # T-D67 / ADR-0094: single-use Tailscale auth key on tmpfs (/run), 0600 root.
  # Consumed and deleted by the `tailscale up` runcmd below (ADR-0069 secret-file pattern).
  - path: /run/tailscale-authkey
    permissions: '0600'
    owner: root:root
    content: |
      ${tailscale_authkey}

  - path: /etc/budget-planner/litestream.env
    permissions: '0600'
    owner: root:root
    content: |
      SCW_ACCESS_KEY=${scw_access_key}
      SCW_SECRET_KEY=${scw_secret_key}

  - path: /etc/logrotate.d/caddy-access
    permissions: '0644'
    owner: root:root
    content: |
      # T-D59 / ADR-0078 §5: 14 daily generations of the Caddy access log.
      /var/log/caddy/access.log {
          daily
          rotate 14
          compress
          delaycompress
          missingok
          notifempty
          copytruncate
      }

  - path: /etc/docker/daemon.json
    permissions: '0644'
    owner: root:root
    content: |
      {
        "log-driver": "journald",
        "live-restore": true,
        "icc": false,
        "no-new-privileges": true,
        "userland-proxy": false
      }

  - path: /root/.docker/config.json
    permissions: '0600'
    owner: root:root
    content: |
      {
        "auths": {
          "ghcr.io": {
            "auth": "${ghcr_auth_b64}"
          }
        }
      }

  - path: /usr/local/bin/deploy-budget-planner
    permissions: '0755'
    owner: root:root
    content: |
      ${indent(6, deploy_script_rendered)}

%{ if enable_restore_helper ~}
  # T-D41a: drill-only. Read-only credential for the PROD replica + the helper
  # the monthly restore-drill workflow runs over SSH.
  - path: /etc/budget-planner/restore-source.env
    permissions: '0600'
    owner: root:root
    content: |
      RESTORE_ACCESS_KEY_ID=${restore_access_key}
      RESTORE_SECRET_ACCESS_KEY=${restore_secret_key}

  - path: /usr/local/bin/restore-from-prod
    permissions: '0755'
    owner: root:root
    content: |
      ${indent(6, restore_script_rendered)}

%{ endif ~}
  - path: /etc/apt/apt.conf.d/50unattended-upgrades
    permissions: '0644'
    owner: root:root
    content: |
      Unattended-Upgrade::Allowed-Origins {
        "$${distro_id}:$${distro_codename}";
        "$${distro_id}:$${distro_codename}-security";
      };
      Unattended-Upgrade::Automatic-Reboot "true";
      Unattended-Upgrade::Automatic-Reboot-Time "04:00";

  - path: /etc/apt/apt.conf.d/20auto-upgrades
    permissions: '0644'
    owner: root:root
    content: |
      APT::Periodic::Update-Package-Lists "1";
      APT::Periodic::Unattended-Upgrade "1";

runcmd:
  - mkdir -p /data && chown 10001:10001 /data && chmod 0700 /data
  - mkdir -p /var/log/caddy && chown root:root /var/log/caddy && chmod 0755 /var/log/caddy
  # T-D67 / ADR-0094: join the tailnet (official apt repo, Ubuntu noble). The
  # Scaleway security group has no port 22 (the SG is the gate; ufw stays open on 22 so
  # the documented break-glass SG rule works).
  - install -m 0755 -d /usr/share/keyrings
  - curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg -o /usr/share/keyrings/tailscale-archive-keyring.gpg
  - curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list -o /etc/apt/sources.list.d/tailscale.list
  - apt-get update
  - DEBIAN_FRONTEND=noninteractive apt-get install -y tailscale
  - systemctl enable --now tailscaled
  - sh -c 'tailscale up --auth-key=file:/run/tailscale-authkey --hostname=${tailscale_hostname} --advertise-tags=${tailscale_tag} --accept-dns=false; rc=$?; rm -f /run/tailscale-authkey; exit $rc'
  - ufw default deny incoming
  - ufw default allow outgoing
  - ufw allow 22/tcp
  - ufw allow 80/tcp
  - ufw allow 443/tcp
  - ufw --force enable
  - systemctl enable --now unattended-upgrades
  - systemctl enable --now docker
  - sh -c 'cd /etc/budget-planner && docker compose pull && docker compose up -d'
  - sh -c 'for i in $(seq 1 60); do curl -fsS -k https://localhost/ready && break; sleep 1; done'

final_message: "budget-planner bootstrap complete at $UPTIME seconds; app reachable on ${hostname}."
