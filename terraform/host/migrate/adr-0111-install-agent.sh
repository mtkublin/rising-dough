#!/usr/bin/env bash
# One-time prod migration to Terraform-declared host state (ADR-0111, T-D129f).
#
# Installs the fixed bootstrap that cloud-init writes on new VMs (agent loader,
# bp-converge service + timer, metadata guard) on a VM booted before ADR-0111,
# and removes the SSH deploy path (deploy user, forced-command script, tag
# files). Idempotent. Logged break-glass host change: explicit user go, entry in
# docs/CHANGELOG.md. Run from a checkout of the merged commit:
#
#   ssh operator@budget-planner-prod 'sudo bash -s' < terraform/host/migrate/adr-0111-install-agent.sh
#
# The file bodies below must equal terraform/cloud-init/bootstrap.yaml.tpl
# (tests/unit/deploy/test_host_migration.py checks this).
set -euo pipefail
umask 022

install_file() { # path mode; content on stdin
  local tmp
  tmp="$(mktemp "$1.XXXXXX")"
  cat > "$tmp"
  chmod "$2" "$tmp"
  chown root:root "$tmp"
  mv "$tmp" "$1"
}

install_file /usr/local/sbin/bp-agent-loader 0755 <<'BP_EOF'
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
BP_EOF

install_file /etc/systemd/system/bp-converge.service 0644 <<'BP_EOF'
[Unit]
Description=Converge host to the Terraform-declared state (ADR-0111)
Wants=network-online.target
After=network-online.target docker.service bp-metadata-guard.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/bp-agent-loader
TimeoutStartSec=15min
BP_EOF

install_file /etc/systemd/system/bp-converge.timer 0644 <<'BP_EOF'
[Unit]
Description=Run the host agent every 30 s (ADR-0111)

[Timer]
OnBootSec=30s
OnUnitInactiveSec=30s
AccuracySec=5s

[Install]
WantedBy=timers.target
BP_EOF

install_file /etc/systemd/system/bp-metadata-guard.service 0644 <<'BP_EOF'
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
BP_EOF

install -d -m 0755 -o root -g root /var/lib/budget-planner

systemctl daemon-reload
systemctl enable --now bp-metadata-guard.service
systemctl enable --now bp-converge.timer

# ADR-0111 §7: the SSH deploy path is gone.
if id deploy >/dev/null 2>&1; then
  userdel --remove deploy
fi
rm -f /usr/local/bin/deploy-budget-planner \
  /etc/budget-planner/.current-tag /etc/budget-planner/.previous-tag

iptables -C DOCKER-USER -d 169.254.42.42/32 -j DROP
systemctl is-active --quiet bp-converge.timer
echo "bp-agent bootstrap installed; deploy path removed"
