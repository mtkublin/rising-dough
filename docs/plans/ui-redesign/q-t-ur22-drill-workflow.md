# T-UR22: drill workflow patch (operator)

The agent token has no `workflow` scope, so the `.github/workflows` edits for T-UR22 are not committed. Everything else is merged (Terraform `admin_email` optional for drills, compose without the admin env when empty, `scripts/ci/tf_env.py`, ADR-0134 amendment 2026-11-26).

## Operator how-to (3 lines)

1. `TOKEN=$(openssl rand -hex 32)`; keep it (password manager), never paste it into GitHub.
2. `printf '%s' "$TOKEN" | shasum -a 256 | cut -d' ' -f1` gives the hash.
3. `gh workflow run drill.yml --ref <branch> -f mode=explore -f setup_token_hash=<hash>`; when the drill is up open `https://budget-planner-drill-<run id>.<tailnet>/setup?token=$TOKEN` and create the admin (single use).

## What the patch does

- Ordering: the merged `tf_env.py` is backward compatible. A drill with no `DRILL_SETUP_TOKEN_HASH` keeps the bootstrap admin (`ADMIN_EMAIL`) and setup stays closed, so an explore dispatched before this patch is applied, and every gate or upgrade drill (smoke keeps working), behave as today. Only with a hash is the bootstrap admin dropped. After this patch explore requires the hash, so the fallback is never used for explore.
- The repository is PUBLIC, so job summaries and logs are world-readable: the token never enters GitHub. Only its sha256 (safe to publish for a 256-bit random token) is a dispatch input.
- `drill.yml`: new input `setup_token_hash`; job `ttl` validates it (64 lowercase hex chars, REQUIRED for `mode=explore`, rejected for gate), exposes it as output `setup-token-hash`, and writes only "Setup open: use /setup?token=<your token>" to the summary. The explore `apply` job passes it as `setup_token_hash`. Gate and upgrade drills pass nothing: setup stays closed.
- Why required for explore (not "keep the bootstrap admin when empty"): a drill has no bootstrap admin, so without a hash nobody could sign in; keeping the bootstrap admin on an empty input would reintroduce the generated admin password in Terraform output and the very default T-UR22 removes. Failing fast is the safer option and still lets the operator log in.
- `terraform.yml`: new input `setup_token_hash` (drill only), exported as `DRILL_SETUP_TOKEN_HASH` for the apply job; `scripts/ci/tf_env.py` (merged, validates sha256 hex) turns it into `TF_VAR_setup_token_hash` for a drill and empties `TF_VAR_admin_email` then.
- No new secret, variable or environment. The `ADMIN_EMAIL` entry in the `drill.yml` `detect` job `secrets-json` is now unused by drills (harmless).

## Apply

Save the diff below as `q-t-ur22.diff` and, from the repository root:

```sh
patch -p1 --dry-run < q-t-ur22.diff
patch -p1 < q-t-ur22.diff
```

Commit it as `ci(T-UR22): drill setup token and no bootstrap admin`. Merge this item first: `tf_env.py` must know `DRILL_SETUP_TOKEN_HASH` before the workflow sets it. The patch was checked against the workflows at base `d6d8221b` (applies cleanly, both files parse as YAML).

## Verify

1. `terraform -chdir=terraform test` passes (cases `compose_without_admin_email_has_no_bootstrap_admin`, `compose_with_admin_email_keeps_bootstrap_admin`, `empty_admin_email_rejected_on_prod`).
2. Dispatch an explore drill as in the how-to. Dispatch without `setup_token_hash` (or with a malformed one): the `ttl` job fails with the error. A gate dispatch with the input fails too.
3. Open the link over the tailnet: `/setup` renders (token valid; the hash of your token is what the app holds), create the admin, sign in. Reload the same link: 404 (token consumed); `/setup` without a token: 404.
4. The compose file on the drill host has `BUDGET_PLANNER_SETUP_TOKEN_HASH` and no `BUDGET_PLANNER_ADMIN_EMAIL`.
5. A gate drill boots without `BUDGET_PLANNER_SETUP_TOKEN_HASH` (setup closed, no admin; smoke does not need one).
6. Prod: the next prod plan shows no change from this item (prod keeps `ADMIN_EMAIL`; its `SETUP_TOKEN_HASH` is still the operator's, [q10-operator-steps.md](q10-operator-steps.md)).

## Diff

```diff
--- a/.github/workflows/drill.yml
+++ b/.github/workflows/drill.yml
@@ -67,6 +67,11 @@
         type: boolean
         required: false
         default: true
+      setup_token_hash:
+        description: "Explore only, REQUIRED there (T-UR22). sha256 hex of a setup token you generated locally (openssl rand -hex 32); open /setup?token=<token> to create the first admin. Never paste the token itself."
+        type: string
+        required: false
+        default: ""
       boot_logs:
         description: Upload boot diagnostics to the drill bucket (boot_log_upload, ADR-0094)
         type: boolean
@@ -175,6 +180,8 @@
     permissions: {}
     outputs:
       expires-at: ${{ steps.ttl.outputs.expires_at }}
+      # T-UR22: the operator's sha256 (public-safe); explore only, empty otherwise.
+      setup-token-hash: ${{ steps.setup-token.outputs.hash }}
     steps:
       - name: Compute expires-at (RFC3339 UTC)
         id: ttl
@@ -201,6 +208,31 @@
           fi
           echo "expires_at=$(date -u -d "+${ttl} minutes" +%Y-%m-%dT%H:%M:%SZ)" >> "$GITHUB_OUTPUT"

+      # T-UR22 / ADR-0134 section 9 (amendment 2026-11-26): the repository is PUBLIC, so
+      # the token never enters GitHub. The operator generates it locally and passes only
+      # its sha256. Explore requires it (a drill has no bootstrap admin, so without it
+      # nobody could sign in); gate and upgrade drills accept none.
+      - name: Validate the setup token hash
+        id: setup-token
+        env:
+          MODE: ${{ inputs.mode }}
+          INPUT_HASH: ${{ inputs.setup_token_hash }}
+        run: |
+          set -euo pipefail
+          if [ "${MODE}" != "explore" ]; then
+            if [ -n "${INPUT_HASH}" ]; then
+              echo "::error::setup_token_hash is explore only" >&2
+              exit 1
+            fi
+            exit 0
+          fi
+          if ! [[ "${INPUT_HASH}" =~ ^[0-9a-f]{64}$ ]]; then
+            echo "::error::explore needs setup_token_hash = sha256 hex (64 lowercase hex chars) of a token you generated locally" >&2
+            exit 1
+          fi
+          echo "hash=${INPUT_HASH}" >> "$GITHUB_OUTPUT"
+          echo "Setup open: use /setup?token=<your token> on the drill URL (token not stored in GitHub)." >> "$GITHUB_STEP_SUMMARY"
+
   # mode=explore: a fresh boot of the dispatched ref, unchanged (ADR-0149 §1).
   apply:
     name: terraform apply (drill)
@@ -217,6 +249,7 @@
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
