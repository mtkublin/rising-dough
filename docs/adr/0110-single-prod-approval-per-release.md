# ADR-0110: One Prod Approval per Release

- **Status**: Accepted
- **Superseded by**: ADR-0111 (no deploy job, so no `prod-deploy` environment)
- **Date**: 2026-11-16
- **Relates to**: ADR-0100 (credential split), ADR-0109 (release trigger), T-D128
- **Amends**: ADR-0099 (release gate: one approval per release instead of one per prod job)

## Context

`release.yml` calls `terraform.yml` (`tf-apply-prod`) and then `deploy.yml` (`deploy-prod`). Both jobs declare `environment: prod`, which has required reviewers, so the operator approves twice per release. ADR-0099 intends a single human gate. The second approval adds no safety: the deploy only starts after the approved apply, from the same tag.

`deploy.yml` (prod) uses only: `DEPLOY_SSH_PRIVATE_KEY`, `DEPLOY_SSH_KNOWN_HOSTS`, `PROD_HOST`, `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET` and the variable `PROD_URL`. It uses no Scaleway key.

## Decision

Option (a): the prod deploy job runs in a second environment, `prod-deploy`, without required reviewers.

1. `deploy.yml` uses environment `prod-deploy` when `inputs.env == 'prod'` (drill unchanged). `release.yml` keeps `deploy-prod` `needs: tf-apply-prod`, so deploy cannot start before the approved apply succeeds.
2. `prod-deploy` holds only the deploy-side values: `DEPLOY_SSH_PRIVATE_KEY`, `DEPLOY_SSH_KNOWN_HOSTS`, `PROD_HOST`, `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`, variable `PROD_URL`. No Scaleway key, no age identity, no `APP_*` keys.
3. Deployment branches and tags policy on `prod-deploy`: `main` and `v*` (the release runs from a `v*` tag, ADR-0109). `prod` gets the same policy (it said `main` only, which cannot match a tag run).
4. `prod` (required reviewers) keeps every Scaleway write credential: ADR-0100's property, that the only prod-write credential lives in the reviewer-gated environment, holds. The terraform apply is the one gate per release.
5. `rollback.yml` stays on `prod` (reviewers): rollback is a manual prod change and keeps its approval. It needs the same SSH/tailnet secrets, so `prod` keeps copies.
6. The ref guard in `deploy.yml` (main, or `v*` tag on main, ADR-0109) is unchanged and backs up the reviewer-less environment.

## Consequences

- One approval per release, at apply. An approved apply always deploys.
- The deploy credentials exist in two environments (`prod`, `prod-deploy`) and are rotated in both (`key-rotation.md`).
- A workflow edit merged to `main` could use `prod-deploy` without approval. Branch protection on `main` (drill-gate, CI) and the `v*` tag ruleset are the controls, and these secrets cannot touch Scaleway infrastructure or data keys.

## Alternatives considered

- **(b) Fold deploy steps into the apply job**: one approval, but `terraform.yml` is reusable and shared with drill, so SSH deploy steps would join the Scaleway-write job (larger blast radius) and drill/prod paths would diverge. Rejected.
- **(c) Dedicated approval-gate job, apply and deploy in reviewer-less environments**: moves the Scaleway prod-write key out of the reviewer-gated environment, breaking ADR-0100. Rejected.
- **Drop reviewers entirely**: removes the gate ADR-0099 requires. Rejected.
