#!/usr/bin/env bash
# shellcheck shell=bash
#
# deploy-budget-planner — ForceCommand entry point for the restricted `deploy`
# user on the Scaleway Stardust host (ADR-0037 §3). Rendered by Terraform via
# cloud-init. The deploy user has NO interactive shell: every incoming SSH
# session is routed through this script via the `command="…"` directive in
# ~deploy/.ssh/authorized_keys. Any argument the operator typed after the ssh
# target lands in $SSH_ORIGINAL_COMMAND verbatim.
#
# Expected authorized_keys line (one per deploy key):
#
#   command="/usr/local/bin/deploy-budget-planner",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty,restrict ssh-ed25519 AAAA...pubkey... github-actions@budget-planner
#
# Supported subcommands:
#
#   deploy <image-ref>   Pull + swap to <image-ref>. Image tag must match
#                        `sha-<7..40-hex>` or `vMAJOR.MINOR.PATCH`.
#                        <image-ref> may be a bare tag OR a full
#                        `ghcr.io/<owner>/budget-planner:<tag>` ref — any
#                        `/` or `:` prefix is stripped before tag validation.
#                        On `/ready` failure, auto-rollback kicks in and the
#                        command exits non-zero.
#
#   rollback             Switch back to the tag recorded in
#                        ${previous_tag_file}. Fails if the file is missing
#                        or empty.
#
#   rollback <sha-xxx>   Explicit rollback target. Same tag-shape validation
#                        as `deploy`. Does not require ${previous_tag_file}.
#
#   status               Print the current + previous recorded tags and the
#                        output of `docker compose ps` for the app service.
#
# ADR-0037 §3 audit requirement: `ssh deploy@<host> "ls /"` returns the usage
# line and exits non-zero (code 1). Verified in T-D32 acceptance; the dispatcher
# below rejects every unknown subcommand through the explicit `*)` arm.
#
# Terraform template variables (interpolated at render time by cloud-init):
#
#   ${owner}              — GitHub owner/org that owns the GHCR image repo.
#   ${app_image}          — Full image repo path, e.g.
#                           ghcr.io/<owner>/budget-planner.
#   ${compose_dir}        — Directory holding docker-compose.yml + .env (e.g.
#                           /opt/budget-planner).
#   ${previous_tag_file}  — Absolute path to the host-side previous-tag
#                           record (e.g. /opt/budget-planner/previous-tag).
#
# Shell-side variables use the `$${…}` escape so Terraform leaves them alone.

set -Eeuo pipefail
IFS=$'\n\t'

readonly OWNER='${owner}'
readonly APP_IMAGE='${app_image}'
readonly COMPOSE_DIR='${compose_dir}'
readonly PREVIOUS_TAG_FILE='${previous_tag_file}'
readonly CURRENT_TAG_FILE="$${COMPOSE_DIR}/current-tag"
readonly READY_URL='https://localhost/ready'
readonly READY_RETRIES=12
readonly READY_SLEEP_S=5
readonly TAG_REGEX='^(sha-[0-9a-f]{7,40}|v[0-9]+\.[0-9]+\.[0-9]+)$'

readonly PROGNAME='deploy-budget-planner'

usage() {
  cat <<EOF >&2
usage: $${PROGNAME} <subcommand> [args]

subcommands:
  deploy <image-ref>     Pull + swap to <image-ref> (tag must match $${TAG_REGEX}).
  rollback               Roll back to the tag recorded in $${PREVIOUS_TAG_FILE}.
  rollback <sha-xxx>     Roll back to an explicit tag.
  status                 Print recorded tags + docker compose ps.
EOF
}

audit() {
  # Best-effort syslog line per invocation; silently no-op if syslog is absent
  # (dev hosts without rsyslog, test containers).
  local subcmd="$${1:-unknown}"
  local raw="$${SSH_ORIGINAL_COMMAND:-<local>}"
  local conn="$${SSH_CONNECTION:-<local>}"
  if command -v logger >/dev/null 2>&1; then
    logger -t "$${PROGNAME}" -p auth.info -- \
      "subcmd=$${subcmd} ssh_original_command=$${raw} ssh_connection=$${conn}" \
      >/dev/null 2>&1 || true
  fi
}

die() {
  local code="$${1}"; shift
  printf '%s: %s\n' "$${PROGNAME}" "$${*}" >&2
  exit "$${code}"
}

normalize_tag() {
  # Accept `sha-abc1234`, `vX.Y.Z`, `ghcr.io/owner/repo:tag`, or `repo:tag`;
  # print the bare tag on stdout and return 0 on success. On failure, print
  # an error to stderr and return 2 — callers MUST check the return code
  # explicitly because `tag="$(normalize_tag ...)"` under `set -e` would
  # otherwise mask the subshell exit (bash does not propagate subshell
  # failure through command substitution assignments).
  local raw="$${1}"
  local tag="$${raw##*:}"
  tag="$${tag##*/}"
  if ! [[ "$${tag}" =~ $${TAG_REGEX} ]]; then
    printf '%s: invalid image tag %q (want sha-<hex> or vX.Y.Z)\n' \
      "$${PROGNAME}" "$${raw}" >&2
    return 2
  fi
  printf '%s' "$${tag}"
}

record_tags() {
  # Atomically rotate current → previous, then write the new current. Uses
  # mv to make each write atomic; a crash mid-write leaves either the old or
  # the new file intact, never a truncated one.
  local new_tag="$${1}"
  local tmp
  tmp="$(mktemp "$${COMPOSE_DIR}/.tag.XXXXXX")"
  if [[ -f "$${CURRENT_TAG_FILE}" ]]; then
    cp -- "$${CURRENT_TAG_FILE}" "$${PREVIOUS_TAG_FILE}.tmp"
    mv -- "$${PREVIOUS_TAG_FILE}.tmp" "$${PREVIOUS_TAG_FILE}"
  fi
  printf '%s\n' "$${new_tag}" > "$${tmp}"
  mv -- "$${tmp}" "$${CURRENT_TAG_FILE}"
}

probe_ready() {
  local i
  for i in $(seq 1 "$${READY_RETRIES}"); do
    if curl -fsS --max-time 5 --resolve "localhost:443:127.0.0.1" -k \
      "$${READY_URL}" >/dev/null 2>&1; then
      printf 'ready after attempt %s\n' "$${i}"
      return 0
    fi
    sleep "$${READY_SLEEP_S}"
  done
  return 1
}

compose() {
  # Thin wrapper so every compose call runs with the right project dir + env.
  TAG="$${TAG:-}" docker compose -f "$${COMPOSE_DIR}/docker-compose.yml" "$${@}"
}

switch_to_tag() {
  local tag="$${1}"
  TAG="$${tag}" compose pull app
  TAG="$${tag}" compose up -d app
}

cmd_deploy() {
  local raw="$${1:-}"
  [[ -n "$${raw}" ]] || die 1 "deploy requires an image ref"
  local tag
  if ! tag="$(normalize_tag "$${raw}")"; then
    exit 2
  fi

  local prev_tag=""
  if [[ -f "$${CURRENT_TAG_FILE}" ]]; then
    prev_tag="$(cat -- "$${CURRENT_TAG_FILE}")"
  fi

  record_tags "$${tag}"
  if ! switch_to_tag "$${tag}"; then
    die 3 "docker compose failed for tag $${tag}"
  fi

  if probe_ready; then
    printf '%s: deployed %s (previous %s)\n' \
      "$${PROGNAME}" "$${tag}" "$${prev_tag:-none}"
    return 0
  fi

  printf '%s: /ready probe failed for %s, rolling back\n' \
    "$${PROGNAME}" "$${tag}" >&2
  if [[ -n "$${prev_tag}" ]]; then
    # Best-effort rollback; keep original failure semantics regardless.
    switch_to_tag "$${prev_tag}" || true
    probe_ready || true
    # Restore previous as current so a subsequent `rollback` without args
    # does not try to re-apply the failed tag.
    record_tags "$${prev_tag}"
  fi
  exit 3
}

cmd_rollback() {
  local tag raw
  if [[ "$${#}" -eq 0 ]]; then
    [[ -s "$${PREVIOUS_TAG_FILE}" ]] \
      || die 4 "no previous tag recorded at $${PREVIOUS_TAG_FILE}"
    raw="$(cat -- "$${PREVIOUS_TAG_FILE}")"
  else
    raw="$${1}"
  fi
  if ! tag="$(normalize_tag "$${raw}")"; then
    exit 2
  fi

  record_tags "$${tag}"
  if ! switch_to_tag "$${tag}"; then
    die 3 "docker compose failed for rollback target $${tag}"
  fi
  if ! probe_ready; then
    die 3 "/ready probe failed after rollback to $${tag}"
  fi
  printf '%s: rolled back to %s\n' "$${PROGNAME}" "$${tag}"
}

cmd_status() {
  local cur="(none)"
  local prev="(none)"
  [[ -s "$${CURRENT_TAG_FILE}" ]]  && cur="$(cat -- "$${CURRENT_TAG_FILE}")"
  [[ -s "$${PREVIOUS_TAG_FILE}" ]] && prev="$(cat -- "$${PREVIOUS_TAG_FILE}")"
  printf 'owner:    %s\n' "$${OWNER}"
  printf 'image:    %s\n' "$${APP_IMAGE}"
  printf 'current:  %s\n' "$${cur}"
  printf 'previous: %s\n' "$${prev}"
  echo
  compose ps app || true
}

main() {
  # SSH ForceCommand entry: parse SSH_ORIGINAL_COMMAND when the script is
  # invoked with no positional args (the common case). When invoked locally
  # with explicit args (dev / tests), honour "$@" directly.
  local -a args=()
  if [[ "$${#}" -gt 0 ]]; then
    args=( $${1+"$${@}"} )
  elif [[ -n "$${SSH_ORIGINAL_COMMAND:-}" ]]; then
    # shellcheck disable=SC2206  # word splitting is desired here
    args=( $${SSH_ORIGINAL_COMMAND} )
  fi

  if [[ "$${#args[@]}" -eq 0 ]]; then
    audit "noop"
    usage
    exit 1
  fi

  local subcmd="$${args[0]}"
  audit "$${subcmd}"

  case "$${subcmd}" in
    deploy)
      [[ "$${#args[@]}" -eq 2 ]] || { usage; exit 2; }
      cd -- "$${COMPOSE_DIR}"
      cmd_deploy "$${args[1]}"
      ;;
    rollback)
      [[ "$${#args[@]}" -le 2 ]] || { usage; exit 2; }
      cd -- "$${COMPOSE_DIR}"
      if [[ "$${#args[@]}" -eq 2 ]]; then
        cmd_rollback "$${args[1]}"
      else
        cmd_rollback
      fi
      ;;
    status)
      [[ "$${#args[@]}" -eq 1 ]] || { usage; exit 2; }
      cd -- "$${COMPOSE_DIR}"
      cmd_status
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main $${1+"$${@}"}
