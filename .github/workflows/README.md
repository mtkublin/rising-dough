# Workflows

Policy: ADR-0099 — production releases happen only from `main`, through one
dependency-ordered pipeline.

```
push to main
  release.yml  (concurrency: release-prod)
    ci            -> ci.yml        (workflow_call)
    build         -> build.yml     (needs ci; outputs image-tag, image-digest, image-ref)
    tf-apply-prod -> terraform.yml (needs build; env prod = required reviewers; -var app_image_tag)
    deploy-prod   -> deploy.yml    (needs build, tf-apply-prod; env prod; smoke GET /ready)
```

| Workflow | Triggers | Notes |
|---|---|---|
| `release.yml` | push `main`, dispatch (main only) | the only prod path |
| `ci.yml` | pull_request `main`, workflow_call | |
| `build.yml` | workflow_call, dispatch (main only) | cosign-signed; no push/tag/release triggers |
| `terraform.yml` | pull_request (fmt/validate/tflint/plan, masked), workflow_call | inputs `env`, `image_tag`, `replace`, `destroy`; prod requires `main`; plan masked via `mask_plan.py`, `plan.bin` never uploaded (ADR-0098) |
| `deploy.yml` | workflow_call | inputs `env` (drill\|prod), `image_tag`; tailnet SSH, `/ready` probe, rollback on failure |
| `rollback.yml` | dispatch | prod only from `main` |
| `restore-drill.yml` | monthly schedule, dispatch | concurrency group `drill` |

Drill is not part of the main pipeline; it is validated pre-merge (T-D90) by
calling `terraform.yml` / `deploy.yml` with `env: drill`.

Expected configuration: environments `drill`, `prod` (required reviewers),
`prod-plan`; secrets as listed in `terraform.yml` / `deploy.yml` headers;
vars `DRILL_URL`, `PROD_URL`.
