#!/usr/bin/env bash
# H4 / H3-01: does Caddy overwrite a client-supplied X-Forwarded-For?
# Sends 2 failed logins (nonexistent user) to the DRILL with forged XFF/X-Real-IP/X-CSP-Nonce,
# then reads back what the app stored via h4_xff_readback.py on the host.
H=${DRILL_HOST:-budget-planner-drill-44609305750.tail7fef0f.ts.net}
IP=${DRILL_IP:-100.116.84.107}
HERE=$(cd "$(dirname "$0")" && pwd)
c(){ curl -sk -m10 --resolve "$H:443:$IP" "$@"; }
for xff in 203.0.113.7 198.51.100.9; do
  rm -f /tmp/h4_jar
  tok=$(c -c /tmp/h4_jar "https://$H/auth/login" | tr '\n' ' ' | sed -E 's/.*name="csrf-token" *content="([^"]+)".*/\1/')
  echo "xff=$xff csrf_len=${#tok}"
  c -b /tmp/h4_jar -o /dev/null -w "login status=%{http_code}\n" \
    -H "X-Forwarded-For: $xff" -H "X-Real-IP: $xff" -H "X-CSP-Nonce: forged-nonce" \
    --data-urlencode "_csrf_token=$tok" --data-urlencode "email=h4probe@example.invalid" \
    --data-urlencode "password=wrong" --data-urlencode "next=/today" "https://$H/auth/login"
done
echo "--- readback from the app DB"
ssh -o UserKnownHostsFile=/tmp/h4_known_hosts operator@budget-planner-drill-44609305750 \
  'docker exec -i budget-planner-app python -I -' < "$HERE/h4_xff_readback.py"
