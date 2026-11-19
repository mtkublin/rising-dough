#!/usr/bin/env bash
# Runs ON the drill host: ssh operator@<drill> 'bash -s' < h4_bucket_run.sh  (probe py passed via stdin file path below)
e(){ docker inspect budget-planner-litestream --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n "s/^$1=//p"; }
export AK="$(e SCW_ACCESS_KEY)" SK="$(e SCW_SECRET_KEY)"
docker exec -i -e AK -e SK budget-planner-app python -I -c "$(cat /tmp/h4_bucket_probe.py)"
