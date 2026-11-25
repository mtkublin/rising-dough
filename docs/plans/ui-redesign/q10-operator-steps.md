# Q10 operator steps: setup-token hash for prod (T-UR21a)

Decision: [operator decisions](operator-decisions-2026-11-25.md) Q10; ADR-0134 §9, ADR-0099, ADR-0100, ADR-0111.
Everything in the repo is merged: docs, `ci_environments.toml`, `scripts/ci/tf_env.py` (prod-only input `setup_token_hash`), the Terraform variable and the compose env. `terraform.yml` already passes `toJSON(secrets)`, so no workflow edit is needed.

## 1. Compute the hash

```sh
TOKEN="$(openssl rand -base64 24)"      # keep it, you type it into /setup?token=...
printf %s "$TOKEN" | sha256sum | cut -d' ' -f1
```

Only the 64-char lowercase hex digest is stored. Never store or commit the token.

## 2. Add the secret

GitHub repo, Settings, Environments, `prod`, add environment secret `SETUP_TOKEN_HASH` = the hex digest. Do not add it to `prod-plan`, `prod-restore-read` or drill environments.

## 3. Apply

Run the normal approved prod `terraform apply`. The host renders `BUDGET_PLANNER_SETUP_TOKEN_HASH` into the compose env. Open `/setup?token=$TOKEN`; the token is single-use. To rotate or close, clear the secret and apply again.

Note: the PR prod-plan job (environment `prod-plan`) has no such secret and plans with an empty value, so the plan shows a display-only difference for this variable.
