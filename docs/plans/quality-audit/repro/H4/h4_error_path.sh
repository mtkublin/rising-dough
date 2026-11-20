#!/usr/bin/env bash
# H4 / D-02,D-03,D-08: headers on a 500 path (non-ASCII CSRF token, one request) and on an HTML 404/403 path.
H=${DRILL_HOST:-budget-planner-drill-44609305750.tail7fef0f.ts.net}; IP=${DRILL_IP:-100.116.84.107}
c(){ curl -sk -m10 --resolve "$H:443:$IP" "$@"; }
rm -f /tmp/h4_jar2; c -c /tmp/h4_jar2 -o /dev/null "https://$H/auth/login"
echo "### POST with non-ASCII csrf token"
c -b /tmp/h4_jar2 -D - -H "X-CSRF-Token: é" --data-urlencode "_csrf_token=é" --data-urlencode "email=a@b.invalid" --data-urlencode "password=x" "https://$H/auth/login" | head -25
echo "### POST without csrf token"
c -b /tmp/h4_jar2 -D - --data-urlencode "email=a@b.invalid" --data-urlencode "password=x" "https://$H/auth/login" | head -25
echo "### oversize header / bad method"
c -D - -X TRACE "https://$H/auth/login" | head -8
