#!/usr/bin/env bash
# NOTE: rendered via cloud-init by Terraform. Edits must happen in the .tpl.
# ADR-0037 §3: deploy-user restricted command.
#
# Invoked via SSH forced-command on the `deploy` user. The remote caller sends
# a single-token image tag over the SSH ORIGINAL_COMMAND; we validate it, pull,
# recreate the app container, probe /ready, and roll back on failure.
#
# This stub implements the contract; T-D32 finalises the rollback catalog and
# the exact `docker compose` incantations after the compose template stabilises.

set -euo pipefail

OWNER="${owner}"
IMAGE="ghcr.io/$${OWNER}/budget-planner"
COMPOSE_DIR="/etc/budget-planner"
HEALTH_URL="https://localhost/ready"
HEALTH_BUDGET_SECS=60

usage() {
    cat >&2 <<'USAGE'
deploy-budget-planner — restricted SSH forced-command.
Usage: ssh deploy@<host> deploy <image-tag>
       ssh deploy@<host> rollback
Image tag must match ^[A-Za-z0-9._-]{1,128}$.
USAGE
    exit 2
}

ORIGINAL_CMD="$${SSH_ORIGINAL_COMMAND:-}"
read -r -a ARGS <<< "$${ORIGINAL_CMD}"

if [[ "$${#ARGS[@]}" -lt 1 ]]; then
    usage
fi

ACTION="$${ARGS[0]}"

case "$${ACTION}" in
    deploy)
        TAG="$${ARGS[1]:-}"
        if [[ ! "$${TAG}" =~ ^[A-Za-z0-9._-]{1,128}$ ]]; then
            usage
        fi
        PREV_TAG="$$(cat "$${COMPOSE_DIR}/.current-tag" 2>/dev/null || echo "main")"
        echo "$${TAG}" > "$${COMPOSE_DIR}/.pending-tag"

        cd "$${COMPOSE_DIR}"
        IMAGE_TAG="$${TAG}" docker compose pull app
        IMAGE_TAG="$${TAG}" docker compose up -d --no-deps app

        for i in $$(seq 1 "$${HEALTH_BUDGET_SECS}"); do
            if curl -fsS -k "$${HEALTH_URL}" >/dev/null; then
                echo "$${TAG}" > "$${COMPOSE_DIR}/.current-tag"
                echo "$${PREV_TAG}" > "$${COMPOSE_DIR}/.previous-tag"
                rm -f "$${COMPOSE_DIR}/.pending-tag"
                echo "deploy ok: $${TAG}"
                exit 0
            fi
            sleep 1
        done

        echo "deploy failed health probe; rolling back to $${PREV_TAG}" >&2
        IMAGE_TAG="$${PREV_TAG}" docker compose up -d --no-deps app
        exit 1
        ;;

    rollback)
        PREV_TAG="$$(cat "$${COMPOSE_DIR}/.previous-tag" 2>/dev/null || true)"
        if [[ -z "$${PREV_TAG}" ]]; then
            echo "no previous tag recorded" >&2
            exit 1
        fi
        cd "$${COMPOSE_DIR}"
        IMAGE_TAG="$${PREV_TAG}" docker compose up -d --no-deps app
        echo "rollback ok: $${PREV_TAG}"
        ;;

    *)
        usage
        ;;
esac
