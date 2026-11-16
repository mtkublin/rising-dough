# T-D31 — Deploy workflow (SSH drill, prod via env approval)

> **Superseded by ADR-0099 (2026-11-07).** The `workflow_run` chain (build, drill deploy, then prod approval) is replaced: `deploy.yml` is now a reusable `workflow_call` workflow driven by `release.yml` (prod, from `main`) and `drill.yml` (drill). See [`runbooks/deploy.md`](../runbooks/deploy.md) and [`runbooks/drill.md`](../runbooks/drill.md). The text below is the original spec, kept as written.

- **Phase**: 3 — Deployment pipeline
- **Sequential**: after T-D30
- **Depends on**: T-D27 (prod infra up), T-D30 (build + cosign)
- **References**: ADR-0037 §1, §3

## Deliverables

`.github/workflows/deploy.yml`:

```yaml
name: deploy
on:
  workflow_run:
    workflows: [build]
    types: [completed]
    branches: [main]

permissions:
  contents: read
  deployments: write
  packages: read

jobs:
  deploy-drill:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    environment:
      name: drill
      url: https://drill.budget.${{ vars.DOMAIN }}
    steps:
      - uses: actions/checkout@v4
      - name: Install SSH key
        env:
          KEY: ${{ secrets.DEPLOY_SSH_PRIVATE_KEY }}
        run: |
          mkdir -p ~/.ssh
          chmod 700 ~/.ssh
          printf '%s\n' "$KEY" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          ssh-keyscan -H ${{ secrets.DEPLOY_HOST_DRILL }} >> ~/.ssh/known_hosts
      - name: Deploy
        run: |
          SHORT=${GITHUB_SHA::7}
          ssh deploy@${{ secrets.DEPLOY_HOST_DRILL }} "deploy sha-$SHORT"
      - name: Post-deploy probe
        run: |
          for i in $(seq 1 30); do
            curl -fsS https://drill.budget.${{ vars.DOMAIN }}/ready && exit 0
            sleep 1
          done
          exit 1

  deploy-prod:
    needs: deploy-drill
    runs-on: ubuntu-latest
    environment:
      name: prod                    # requires manual approval
      url: https://budget.${{ vars.DOMAIN }}
    steps:
      - uses: actions/checkout@v4
      - name: Install SSH key
        env:
          KEY: ${{ secrets.DEPLOY_SSH_PRIVATE_KEY }}
        run: |
          mkdir -p ~/.ssh && chmod 700 ~/.ssh
          printf '%s\n' "$KEY" > ~/.ssh/id_ed25519 && chmod 600 ~/.ssh/id_ed25519
          ssh-keyscan -H ${{ secrets.DEPLOY_HOST_PROD }} >> ~/.ssh/known_hosts
      - name: Deploy prod
        run: |
          SHORT=${GITHUB_SHA::7}
          ssh deploy@${{ secrets.DEPLOY_HOST_PROD }} "deploy sha-$SHORT"
      - name: Post-deploy probe
        run: |
          for i in $(seq 1 30); do
            curl -fsS https://budget.${{ vars.DOMAIN }}/ready && exit 0
            sleep 1
          done
          exit 1
```

## Secrets / variables

- Secrets: `DEPLOY_SSH_PRIVATE_KEY`, `DEPLOY_HOST_DRILL`, `DEPLOY_HOST_PROD` (host names). <!-- pragma: allowlist secret -->
- Variable: `DOMAIN` (e.g. `example.com`).

## Acceptance criteria

- Merge to `main` triggers `build`, then `deploy` to `drill` automatically.
- `prod` requires explicit approval of the `prod` environment in the GitHub UI.
- A probe failure fails the job, and the `deploy-budget-planner` script has already rolled back on the host (ADR-0037 §3).
- GitHub Deployments appear in the repo with correct target URLs.

## Validation hook

- Watch a real merge land on drill. Confirm `/ready` 200 after the probe step.
- Approve prod and watch the same.
