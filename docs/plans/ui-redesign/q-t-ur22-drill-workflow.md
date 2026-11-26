# T-UR22: drill workflow patch (operator)

The agent token has no `workflow` scope, so the `.github/workflows` edits for T-UR22 are not committed. Everything else is merged (Terraform `admin_email` optional for drills, compose without the admin env when empty, `scripts/ci/tf_env.py`, ADR-0134 amendment 2026-11-26).

## What the patch does

- `drill.yml`, job `ttl`: in explore mode generates the token (`openssl rand -hex 32`), registers it with `::add-mask::`, writes `https://budget-planner-drill-<run id>.<tailnet>/setup?token=...` to `$GITHUB_STEP_SUMMARY`, and exposes only the sha256 as job output `setup-token-hash` (the token is never an output). The explore `apply` job passes it as `setup_token_hash`. Gate and upgrade drills pass nothing: setup stays closed there.
- `terraform.yml`: new input `setup_token_hash` (drill only), exported as `DRILL_SETUP_TOKEN_HASH` for the apply job; `scripts/ci/tf_env.py` (merged) turns it into `TF_VAR_setup_token_hash` for a drill and leaves `TF_VAR_admin_email` empty (admin_email is mapped for prod only), so the drill has no bootstrap admin.
- No new secret, variable or environment. The `ADMIN_EMAIL` entry in the `drill.yml` `detect` job `secrets-json` is now unused by drills and may be dropped later (harmless).
- Security: the token is visible only in the job summary of a private repository (read access to the repo), never in logs or outputs; it is single use and dies with the drill TTL. Prod is untouched.

## Apply

Save the diff below as `q-t-ur22.diff` and, from the repository root:

```sh
patch -p1 --dry-run < q-t-ur22.diff
patch -p1 < q-t-ur22.diff
```

Commit it as `ci(T-UR22): drill setup token and no bootstrap admin`. Merge this item first: `tf_env.py` must know `DRILL_SETUP_TOKEN_HASH` before the workflow sets it. The patch was checked against the workflows at base `d6d8221b` (applies cleanly, both files parse as YAML).

## Verify

1. `terraform -chdir=terraform test` passes (cases `compose_without_admin_email_has_no_bootstrap_admin`, `compose_with_admin_email_keeps_bootstrap_admin`, `empty_admin_email_rejected_on_prod`).
2. Dispatch an explore drill (`gh workflow run drill.yml --ref <branch> -f mode=explore -f ttl_minutes=60`). In the run summary find "Setup link"; the log shows `***` wherever the token would print.
3. Open the link over the tailnet: `/setup` renders (token valid), create the admin, sign in. Reload the same link: 404 (token consumed); `/setup` without a token: 404.
4. The compose file on the drill host has `BUDGET_PLANNER_SETUP_TOKEN_HASH` and no `BUDGET_PLANNER_ADMIN_EMAIL`.
5. A gate drill boots without `BUDGET_PLANNER_SETUP_TOKEN_HASH` (setup closed, no admin; smoke does not need one).
6. Prod: the next prod plan shows no change from this item (prod keeps `ADMIN_EMAIL`; its `SETUP_TOKEN_HASH` is still the operator's, [q10-operator-steps.md](q10-operator-steps.md)).

## Diff

```diff
--- a/.github/workflows/drill.yml
+++ b/.github/workflows/drill.yml
@@ -175,6 +175,8 @@
     permissions: {}
     outputs:
       expires-at: ${{ steps.ttl.outputs.expires_at }}
+      # T-UR22: sha256 of the explore drill's setup token (not secret); never the token.
+      setup-token-hash: ${{ steps.setup-token.outputs.hash }}
     steps:
       - name: Compute expires-at (RFC3339 UTC)
         id: ttl
@@ -201,6 +203,27 @@
           fi
           echo "expires_at=$(date -u -d "+${ttl} minutes" +%Y-%m-%dT%H:%M:%SZ)" >> "$GITHUB_OUTPUT"

+      # T-UR22 / ADR-0134 section 9 (amendment 2026-11-26): per-deploy one-time setup
+      # token for the explore drill. Masked, never a step or job output, shown only in
+      # this run's job summary (private repo); only its sha256 travels on.
+      - name: Generate the setup token (explore)
+        id: setup-token
+        if: ${{ inputs.mode == 'explore' }}
+        env:
+          HOST: budget-planner-drill-${{ github.run_id }}.${{ vars.TAILNET_DNS_NAME }}
+        run: |
+          set -euo pipefail
+          token="$(openssl rand -hex 32)"
+          echo "::add-mask::${token}"
+          echo "hash=$(printf '%s' "${token}" | sha256sum | cut -d' ' -f1)" >> "$GITHUB_OUTPUT"
+          {
+            echo "### Setup link (explore drill)"
+            echo
+            echo "https://${HOST}/setup?token=${token}"
+            echo
+            echo "Single use; valid until the drill expires. Creates the first admin (no bootstrap admin on drills)."
+          } >> "$GITHUB_STEP_SUMMARY"
+
   # mode=explore: a fresh boot of the dispatched ref, unchanged (ADR-0149 §1).
   apply:
     name: terraform apply (drill)
@@ -217,6 +240,7 @@
       replace: module.compute.scaleway_instance_server.app tailscale_tailnet_key.vm
       drill_expires_at: ${{ needs.ttl.outputs.expires-at }}
       boot_log_upload: ${{ inputs.boot_logs }}
+      setup_token_hash: ${{ needs.ttl.outputs.setup-token-hash }}
     secrets: inherit  # pragma: allowlist secret

   smoke:

--- a/.github/workflows/terraform.yml
+++ b/.github/workflows/terraform.yml
@@ -47,6 +47,11 @@
         type: boolean
         required: false
         default: false
+      setup_token_hash:
+        description: Drill only (T-UR22, ADR-0134 section 9) - sha256 hex of the per-deploy setup token (not secret). Ignored for prod; empty keeps /setup closed.
+        type: string
+        required: false
+        default: ""
       reuse_drill_run_id:
         description: >-
           Drill only (T-D139, ADR-0116) - this apply targets an EXISTING drill VM (rollback): keep the
@@ -375,6 +380,8 @@
       # T-D90: drill-only knobs, forced to their prod-safe values otherwise.
       TF_VAR_drill_expires_at: ${{ inputs.env == 'drill' && inputs.drill_expires_at || '' }}
       TF_VAR_boot_log_upload: ${{ inputs.env == 'drill' && inputs.boot_log_upload || false }}
+      # T-UR22: read by scripts/ci/tf_env.py (drill only), which exports TF_VAR_setup_token_hash.
+      DRILL_SETUP_TOKEN_HASH: ${{ inputs.env == 'drill' && inputs.setup_token_hash || '' }}
       # ADR-0127 §7: rehearsal knobs, forced to their defaults otherwise (prod ignores them).
       TF_VAR_drill_root_volume_type: ${{ inputs.env == 'drill' && inputs.drill_root_volume_type || 'l_ssd' }}
       TF_VAR_drill_allow_empty_db: ${{ inputs.env == 'drill' && inputs.drill_allow_empty_db || 'true' }}
```
