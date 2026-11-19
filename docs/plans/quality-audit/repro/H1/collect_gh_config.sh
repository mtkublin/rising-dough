#!/usr/bin/env bash
# H1 repro: read-only GETs of the repository's own GitHub configuration.
# No writes, no secret values. Outputs are saved to gh_api/ (recorded 2026-11-19).
set -u
cd "$(dirname "$0")"
mkdir -p gh_api
R=repos/mtkublin/rising-dough
get() { # name path
  gh api "$R$2" > "gh_api/$1.json" 2> "gh_api/$1.err" || echo "  ($1: GET failed, see gh_api/$1.err)"
}
get repo ""
get actions_permissions /actions/permissions
get actions_workflow_perms /actions/permissions/workflow
get actions_fork_pr /actions/permissions/fork-pr-contributor-approval
get actions_selected /actions/permissions/selected-actions
get rulesets /rulesets
get collaborators /collaborators
get environments /environments
get prod_branch_policies /environments/prod/deployment-branch-policies
get prodtailnet_policies /environments/prod-tailnet/deployment-branch-policies
get branch_protection_main /branches/main/protection
get hooks /hooks
get deploy_keys /keys
# secret NAMES only (metadata; values are never returned by the API)
get secrets_prod_plan /environments/prod-plan/secrets
get secrets_drill_teardown /environments/drill-teardown/secrets
get secrets_drill /environments/drill/secrets
get repo_secrets /actions/secrets
ls -la gh_api
