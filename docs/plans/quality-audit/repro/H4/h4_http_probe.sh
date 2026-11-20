#!/usr/bin/env bash
# H4 HTTP probe against the DRILL host only (never prod).
# Usage: DRILL_HOST=... DRILL_IP=... ./h4_http_probe.sh
H=${DRILL_HOST:-budget-planner-drill-44609305750.tail7fef0f.ts.net}
IP=${DRILL_IP:-100.116.84.107}
c(){ curl -sk -m10 --resolve "$H:443:$IP" "$@"; }
echo "== deploy status (unauthenticated)"; c "https://$H/.well-known/bp-deploy-status.json"; echo
for p in /static/nonexistent.css /static/ /auth/nonexistent; do
  echo "=== $p"; c -D - -o /tmp/h4_b "https://$H$p" | grep -iE "^(HTTP|content-sec|server|via|x-|content-type)"; head -c 200 /tmp/h4_b; echo
done
echo "== direct IP, no SNI"; curl -sk -m10 -D - "https://$IP/health" | head -12
echo "== wrong Host header"; c -D - -H "Host: evil.example" "https://$H/health" | head -12
echo "== plain http :80"; curl -s -m5 -D - "http://$IP/" | head -5
echo "== caddy admin :2019"; curl -s -m5 "http://$IP:2019/config/" | head -c 200; echo
echo "== app :8000"; curl -s -m5 "http://$IP:8000/health" | head -c 200; echo
