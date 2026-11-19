#!/usr/bin/env bash
# H4 on-host read-only probe. Run ON the drill host as operator:
#   ssh operator@<drill> 'bash -s' < h4_host_probe.sh
# Secret VALUES are redacted by the sed filters below.
red(){ sed -E 's/((KEY|SECRET|TOKEN|PASS|PASSWORD|IDENTITY|COOKIE_SECRET|ACCESS_KEY_ID|SECRET_ACCESS_KEY|DATABASE_URL)[A-Z_]*)=.*/\1=<REDACTED>/; s/AGE-SECRET-KEY-[A-Z0-9]+/AGE-SECRET-KEY-<REDACTED>/g; s/SCW[A-Z0-9]{17}/SCW<REDACTED>/g'; }
echo "### Caddyfile"; cat /etc/budget-planner/Caddyfile
echo "### ss -tlnp"; sudo ss -tlnpu | head -40
echo "### ufw"; sudo ufw status verbose 2>&1 | head -30
echo "### iptables DOCKER-USER / nat DOCKER"; sudo iptables -S DOCKER-USER 2>&1 | head; sudo iptables -t nat -S DOCKER 2>&1 | head
echo "### docker ps"; docker ps --no-trunc --format '{{.Names}} | {{.Image}} | {{.Ports}}'
echo "### image digests"; for i in $(docker ps --format '{{.Image}}' | sort -u); do docker image inspect "$i" --format '{{.RepoTags}} {{.RepoDigests}}' ; done
echo "### networks"; docker network ls; for n in $(docker network ls --format '{{.Name}}' | grep -v -E '^(bridge|host|none)$'); do echo "-- $n"; docker network inspect "$n" --format '{{range .Containers}}{{.Name}} {{.IPv4Address}}{{"\n"}}{{end}}'; done
echo "### env names per container (values redacted)"; for c in $(docker ps -a --format '{{.Names}}'); do echo "-- $c"; docker inspect "$c" --format '{{range .Config.Env}}{{println .}}{{end}}' | red | grep -v '^$' | sed -E 's/^(PATH|LANG|PYTHON[A-Z_]*|TZ|GPG_KEY)=.*/\1=…/'; done
echo "### docker history --no-trunc (secret-ish grep)"; docker history --no-trunc "$(docker inspect budget-planner-app --format '{{.Image}}')" | grep -iE 'secret|password|token|key=' | red | cut -c1-200
echo "### docker logs secret grep (matches count only)"; for c in $(docker ps -a --format '{{.Names}}'); do printf '%s: ' "$c"; docker logs "$c" 2>&1 | grep -ciE 'AGE-SECRET-KEY|secret_key|password=|initial_password|SCW[A-Z0-9]{17}'; done
echo "### journal secret grep (count)"; sudo journalctl --no-pager 2>/dev/null | grep -ciE 'AGE-SECRET-KEY|initial_password|SCW[A-Z0-9]{17}'
echo "### app container -> metadata 169.254.42.42"; docker exec budget-planner-app python -I -c "
import urllib.request
try:
    r=urllib.request.urlopen('http://169.254.42.42/conf',timeout=4); print('REACHABLE', r.status, r.read(120))
except Exception as e: print('unreachable', type(e).__name__, e)"
echo "### app container -> metadata via 8000/other"; docker exec budget-planner-app python -I -c "
import socket
for h,p in (('budget-planner-caddy',2019),('budget-planner-litestream',8080),('budget-planner-litestream-probe',8080)):
    s=socket.socket(); s.settimeout(3)
    try: s.connect((h,p)); print(h,p,'OPEN')
    except Exception as e: print(h,p,type(e).__name__)
    s.close()"
echo "### operator: read secrets?"; id; sudo -n true && echo "passwordless sudo: yes"
echo "### operator: metadata reachable w/o sudo?"; curl -s -m4 http://169.254.42.42/conf | head -c 80; echo "(rc=$?)"
echo "### file perms"; ls -la /etc/budget-planner /var/lib/budget-planner 2>&1 | head -30; sudo ls -la /var/lib/budget-planner /var/lib/budget-planner/status 2>&1 | head -20
echo "### status.json"; sudo cat /var/lib/budget-planner/status/status.json 2>&1 | head -30
