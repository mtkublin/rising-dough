#!/usr/bin/env bash
# H4 network probe from the laptop against the DRILL only (tailnet IP + its own public IP). nmap absent -> nc, polite (sequential, 1s timeout).
TIP=${DRILL_IP:-100.116.84.107}; PUB=${DRILL_PUB:-151.115.86.61}
echo "### tailnet-IP tcp ports"
for p in 21 22 23 25 53 80 110 111 135 139 443 445 993 1433 2019 2375 2376 3000 3306 5432 6379 8000 8080 8081 8443 9090 9100 9999 19999 47390; do
  nc -z -G 1 $TIP $p 2>/dev/null && echo "open $TIP:$p"
done
echo "### public IP (not via tailnet) tcp"
for p in 22 80 443 2019 8000; do nc -z -G 3 $PUB $p 2>/dev/null && echo "open $PUB:$p" || echo "closed/filtered $PUB:$p"; done
echo "### route used to public IP"; route -n get $PUB 2>&1 | grep -E 'interface|gateway'
echo "### public https handshake (SNI = drill name)"
curl -sk -m8 -o /dev/null -w "http=%{http_code}\n" --resolve budget-planner-drill-44609305750.tail7fef0f.ts.net:443:$PUB https://budget-planner-drill-44609305750.tail7fef0f.ts.net/health
echo "### forged nonce check"
H=budget-planner-drill-44609305750.tail7fef0f.ts.net
curl -sk -m8 -D - -o /dev/null -H 'X-CSP-Nonce: forged-nonce' --resolve $H:443:$TIP https://$H/auth/login | grep -io "nonce-[a-z0-9-]*"
