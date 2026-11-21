#!/usr/bin/env bash
# Run ON the drill host: ssh operator@<drill> 'bash -s' < h4_host_probe2.sh
echo "### Caddyfile"; sudo cat /etc/budget-planner/Caddyfile
echo "### docker daemon.json (userland-proxy / iptables)"; sudo cat /etc/docker/daemon.json 2>&1
echo "### docker-proxy processes"; ps aux | grep -E 'docker-proxy' | grep -v grep | cut -c1-160
echo "### caddy access log tail (client_ip fields only)"; docker logs --tail 400 budget-planner-caddy 2>&1 | grep -oE '"(remote_ip|client_ip)":"[^"]*"' | sort | uniq -c | head
echo "### compose image refs (names)"; sudo grep -nE 'image:|network_mode|ports:|- "?[0-9]+:' /etc/budget-planner/docker-compose.yml
echo "### app user/caps"; docker inspect budget-planner-app --format 'user={{.Config.User}} ro={{.HostConfig.ReadonlyRootfs}} caps_drop={{.HostConfig.CapDrop}} priv={{.HostConfig.Privileged}} secopt={{.HostConfig.SecurityOpt}}'
for c in budget-planner-caddy budget-planner-litestream budget-planner-litestream-probe; do docker inspect $c --format "$c user={{.Config.User}} ro={{.HostConfig.ReadonlyRootfs}} caps_drop={{.HostConfig.CapDrop}} priv={{.HostConfig.Privileged}}"; done
echo "### docker.sock mounted anywhere?"; docker ps -aq | xargs docker inspect --format '{{.Name}} {{range .Mounts}}{{.Source}} {{end}}' | grep -c docker.sock
echo "### app can read litestream/age key mounts?"; docker inspect budget-planner-app --format '{{range .Mounts}}{{.Source}}{{"\n"}}{{end}}'
echo "### litestream container sees app port?"; docker exec budget-planner-litestream-probe sh -c 'wget -q -T3 -O- http://budget-planner-app:8000/health 2>&1 | head -c 100'
echo "### bucket list with drill creds (names only, no object reads) from restore config"
docker exec budget-planner-litestream-probe sh -c 'ls /etc/litestream.yml >/dev/null 2>&1; env | grep -c SCW'
echo "### local listen on loopback"; curl -s -m3 http://127.0.0.1:8000/health | head -c 80; echo "(loopback:8000 rc=$?)"
