#cloud-config
## NOTE: rendered via cloud-init by Terraform. Edits must happen in the .tpl.
## ADR-0035 §5: first-boot sequence (packages, users, firewall, Tailscale, Docker).
## ADR-0111: fixed bootstrap only. App files, image and config come from the
## `bp-config` metadata key via the host agent (`bp-agent`), not from here.
hostname: ${hostname}
preserve_hostname: false
fqdn: ${hostname}
manage_etc_hosts: true

# T-D82 / ADR-0032 sizing note: 1 GiB swapfile as a peak safety net on the 1 GB STARDUST1-S.
# cc_mounts runs in the init stage, before package_update_upgrade_install and runcmd.
swap:
  filename: /swapfile
  size: 1073741824
  maxsize: 1073741824

# Early and idempotent: applies swappiness now (write_files has not run yet in this stage);
# the sysctl.d file below persists it across reboots.
bootcmd:
  - [sysctl, -w, vm.swappiness=10]
%{ if boot_log_upload }
  # T-D86 (drill only, ADR-0094): write_files has not run yet, so this bootcmd writes the uploader
  # and its 0600 credentials under /run (tmpfs) itself, then starts it detached. Never fails boot.
  - |
    (
      umask 077
      printf 'AK=%s\nSK=%s\nBUCKET=%s\nREGION=%s\n' '${scw_access_key}' '${scw_secret_key}' '${bucket_name}' '${bucket_region}' > /run/boot-log-upload.env
      cat > /run/boot-log-upload.sh <<'BOOT_LOG_UPLOAD_EOF'
    #!/bin/sh
    # T-D86: push boot diagnostics to the drill bucket. Best effort; errors are ignored.
    . /run/boot-log-upload.env
    BID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo unknown-boot)
    IID=$(curl -s -m 5 'http://169.254.42.42/conf?format=json' 2>/dev/null | grep -o '"id": *"[^"]*"' | head -n 1 | sed 's/.*"\([^"]*\)"$/\1/')
    [ -n "$IID" ] || IID=$(hostname 2>/dev/null || echo unknown-host)
    D=/run/boot-log-upload.d
    mkdir -p "$D"
    redact() {
      sed -E \
        -e 's/tskey-[A-Za-z0-9-]+/tskey-REDACTED/g' \
        -e 's/AGE-SECRET-KEY-1[A-Z0-9]+/AGE-SECRET-KEY-REDACTED/g' \
        -e 's/([A-Za-z0-9_]*(PASSWORD|SECRET|TOKEN|_KEY)[A-Za-z0-9_]*"?[=:] *"?)[^ ,"]+/\1REDACTED/gI'
    }
    push() {
      curl -s -m 60 -o /dev/null --aws-sigv4 "aws:amz:$REGION:s3" --user "$AK:$SK" \
        -T "$D/$1" "https://$BUCKET.s3.$REGION.scw.cloud/boot-logs/$IID/$BID/$1" || true
    }
    snap() {
      for f in cloud-init.log cloud-init-output.log; do
        [ -r "/var/log/$f" ] && redact < "/var/log/$f" > "$D/$f" 2>/dev/null && push "$f"
      done
      timeout 30 journalctl -b --no-pager 2>&1 | redact > "$D/journal.txt"; push journal.txt
      timeout 30 dmesg 2>&1 | redact > "$D/dmesg.txt"; push dmesg.txt
      timeout 30 cloud-init status --long 2>&1 | redact > "$D/cloud-init-status.txt"; push cloud-init-status.txt
      ps auxf 2>&1 | redact > "$D/ps.txt"; push ps.txt
      free -m > "$D/free.txt" 2>&1; push free.txt
    }
    i=0
    while [ "$i" -lt 120 ]; do snap; sleep 30; i=$((i + 1)); done
    i=0
    while [ "$i" -lt 24 ]; do snap; sleep 300; i=$((i + 1)); done
    BOOT_LOG_UPLOAD_EOF
      nohup setsid sh /run/boot-log-upload.sh > /dev/null 2>&1 &
    ) || true
%{ endif }

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

# T-D84: create `docker` before `users` (cc_users_groups creates groups first); the later
# docker.io install reuses it. Otherwise `useradd -G sudo,docker` can fail and drop `operator`.
groups:
  - docker

# T-D84: SSH password login stays off; the drill-only console password (below) is console-only.
ssh_pwauth: false

users:
  - name: app
    uid: 10001
    shell: /usr/sbin/nologin
    lock_passwd: true
  - name: operator
    # T-D87: Ubuntu ships a system group `operator` (gid 37); the default per-user group collides.
    no_user_group: true
    sudo: ["ALL=(ALL) NOPASSWD:ALL"]
    groups: [sudo, docker]
    shell: /bin/bash
    lock_passwd: ${console_password_hash != "" ? "false" : "true"}
%{~ if console_password_hash != "" }
    hashed_passwd: '${console_password_hash}'
%{~ endif }
    ssh_authorized_keys:
      - '${operator_ssh_pubkey}'
%{~ if ci_ssh_pubkey != "" }
      - '${ci_ssh_pubkey}'
%{~ endif }

write_files:
  - path: /etc/sysctl.d/99-swappiness.conf
    permissions: '0644'
    owner: root:root
    content: |
      vm.swappiness = 10

  # T-D67 / ADR-0094: single-use Tailscale auth key on tmpfs (/run), 0600 root.
  # Consumed and deleted by the `tailscale up` runcmd below (ADR-0069 secret-file pattern).
  - path: /run/tailscale-authkey
    permissions: '0600'
    owner: root:root
    content: |
      ${tailscale_authkey}

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

  # ADR-0111: the fixed part of the host agent. The loader fetches the agent
  # from instance metadata (privileged source port: root only) and runs it.
  - path: /usr/local/sbin/bp-agent-loader
    permissions: '0755'
    owner: root:root
    content: |
      #!/bin/sh
      # ADR-0111: fixed bootstrap. Changing this file needs a VM replace or a
      # logged host edit; everything else comes from bp-agent / bp-config.
      set -eu
      umask 077
      dir=/run/bp-agent
      mkdir -p "$dir"
      curl -fsS --max-time 20 --local-port 1-1023 -o "$dir/bp_agent.py.new" http://169.254.42.42/user_data/bp-agent
      mv "$dir/bp_agent.py.new" "$dir/bp_agent.py"
      exec /usr/bin/python3 -I "$dir/bp_agent.py"

  - path: /etc/systemd/system/bp-converge.service
    permissions: '0644'
    owner: root:root
    content: |
      [Unit]
      Description=Converge host to the Terraform-declared state (ADR-0111)
      Wants=network-online.target
      After=network-online.target docker.service bp-metadata-guard.service
      Requires=docker.service

      [Service]
      Type=oneshot
      ExecStart=/usr/local/sbin/bp-agent-loader
      TimeoutStartSec=15min

  - path: /etc/systemd/system/bp-converge.timer
    permissions: '0644'
    owner: root:root
    content: |
      [Unit]
      Description=Run the host agent every 30 s (ADR-0111)

      [Timer]
      OnBootSec=30s
      OnUnitInactiveSec=30s
      AccuracySec=5s

      [Install]
      WantedBy=timers.target

  # ADR-0111 §6: containers must not reach the metadata API (it serves every
  # secret in user data; Docker grants NET_BIND_SERVICE, so a root container
  # could use a privileged source port). DOCKER-USER filters container egress.
  - path: /etc/systemd/system/bp-metadata-guard.service
    permissions: '0644'
    owner: root:root
    content: |
      [Unit]
      Description=Block container access to the instance metadata API (ADR-0111)
      After=docker.service
      Requires=docker.service
      PartOf=docker.service

      [Service]
      Type=oneshot
      RemainAfterExit=yes
      ExecStart=/bin/sh -c 'iptables -C DOCKER-USER -d 169.254.42.42/32 -j DROP 2>/dev/null || iptables -I DOCKER-USER -d 169.254.42.42/32 -j DROP'

      [Install]
      WantedBy=docker.service

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
  # T-D81 / ADR-0094: firewall FIRST, before any network-dependent step, so the
  # drill-only break-glass SSH rules below are in place even if the Tailscale
  # install or join fails or hangs. `tailscale0` rules are valid before the
  # interface exists.
  - ufw default deny incoming
  - ufw default allow outgoing
  - ufw allow in on tailscale0 to any port 22 proto tcp
%{ for cidr in break_glass_ssh_cidrs ~}
  - ufw allow from ${cidr} to any port 22 proto tcp
%{ endfor ~}
%{~ if tailnet_only }
  # ADR-0101: tailnet-only drill; the web port is reachable on tailscale0 only.
  - ufw allow in on tailscale0 to any port 443
%{~ else }
  - ufw allow 80/tcp
  - ufw allow 443/tcp
%{~ endif }
  - ufw --force enable
  # T-D67 / ADR-0094: join the tailnet (official apt repo, Ubuntu noble). The
  # Scaleway security group has no port 22 and ufw allows 22/tcp only on tailscale0
  # (defence in depth). Break-glass (T-D81, drill only) adds an SG rule and a ufw rule per `break_glass_ssh_cidrs` entry.
  - install -m 0755 -d /usr/share/keyrings
  - curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg -o /usr/share/keyrings/tailscale-archive-keyring.gpg
  - curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list -o /etc/apt/sources.list.d/tailscale.list
  - apt-get update
  - DEBIAN_FRONTEND=noninteractive apt-get install -y tailscale
  - systemctl enable --now tailscaled
  - sh -c 'timeout 120 tailscale up --auth-key=file:/run/tailscale-authkey --hostname=${tailscale_hostname} --advertise-tags=${tailscale_tag} --accept-dns=false; rc=$?; rm -f /run/tailscale-authkey; exit $rc'
  - systemctl enable --now unattended-upgrades
  - systemctl enable --now docker
  # ADR-0111: first convergence (writes app files, verifies + pulls the image,
  # compose up), then every 30 s via the timer.
  - systemctl daemon-reload
  - systemctl enable --now bp-metadata-guard.service
  - systemctl start bp-converge.service
  - systemctl enable --now bp-converge.timer
%{~ if tailnet_only }
  - sh -c 'for i in $(seq 1 60); do curl -fsS --resolve ${hostname}:443:127.0.0.1 https://${hostname}/ready && break; sleep 1; done'
%{~ else }
  - sh -c 'for i in $(seq 1 60); do curl -fsS -k https://localhost/ready && break; sleep 1; done'
%{~ endif }

final_message: "budget-planner bootstrap complete at $UPTIME seconds; app reachable on ${hostname}."
