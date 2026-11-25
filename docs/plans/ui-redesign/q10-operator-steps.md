# Q10 operator steps: setup-token hash for prod (T-UR21a)

Decision: [operator decisions](operator-decisions-2026-11-25.md) Q10; ADR-0134 §9, ADR-0099, ADR-0100, ADR-0111.
Agent prep is merged (docs, `ci_environments.toml`, Terraform variable `setup_token_hash`, compose env). The agent token cannot push `.github/workflows/*`, so the steps below are yours.

## 1. Compute the hash

```sh
TOKEN="$(openssl rand -base64 24)"      # keep it, you type it into /setup?token=...
printf %s "$TOKEN" | sha256sum | cut -d' ' -f1
```

Only the 64-char lowercase hex digest is stored. Never store or commit the token.

## 2. Add the secret

GitHub repo, Settings, Environments, `prod`, add environment secret `SETUP_TOKEN_HASH` = the hex digest.
(It is already declared in `tests/architecture/ci_environments.toml` under `[environment.prod]`.)

## 3. Wire the workflow

The prod apply runs through `scripts/ci/tf_env.py` (inputs become `TF_VAR_*`). Add one entry there (this is a normal file, not a workflow) and expose the secret in the prod terraform apply job:

`scripts/ci/tf_env.py`, in `ENTRIES` (optional input, empty when unset):

```python
    # T-UR21a / ADR-0134 section 9: prod environment secret; empty leaves /setup closed.
    Entry("setup_token_hash", "secret", "SETUP_TOKEN_HASH", default="", only_env="prod"),
```

Workflow: in the prod apply job of `.github/workflows/terraform.yml` (the job with `environment: prod`), add `SETUP_TOKEN_HASH` to the `secrets-json` passed to the env builder, next to the other `toJSON(secrets.X)` entries:

```yaml
          secrets-json: ${{ format('{{...,"SETUP_TOKEN_HASH":{N}}}', ..., toJSON(secrets.SETUP_TOKEN_HASH)) }}
```

(append `,"SETUP_TOKEN_HASH":{N}` with the next free index N and `, toJSON(secrets.SETUP_TOKEN_HASH)` as the last format argument). Do not add it to `prod-plan`, `prod-restore-read` or drill jobs; `test_workflow_secrets.py` allows it only under `prod`.

## 4. Apply and use

Run the normal prod release (approved `terraform apply`). The host renders `BUDGET_PLANNER_SETUP_TOKEN_HASH` into the compose env. Open `/setup?token=$TOKEN`; the token is single-use. To rotate or close, clear the secret and apply again.

Drills: unchanged by this prep (drill workflow generation of a per-run token stays a separate step).
