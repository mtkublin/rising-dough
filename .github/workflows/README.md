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
| `terraform.yml` | pull_request (fmt/validate/tflint/plan, masked), workflow_call | inputs `env`, `image_tag`, `replace`, `destroy`, drill-only `drill_expires_at`, `boot_log_upload`; prod requires `main`; plan masked via `mask_plan.py`, `plan.bin` never uploaded (ADR-0098) |
| `deploy.yml` | workflow_call | inputs `env` (drill\|prod), `image_tag`; tailnet SSH, `/ready` probe, rollback on failure |
| `rollback.yml` | dispatch | prod only from `main` |
| `drill.yml` | push `*-deploy`, dispatch, PR to `main` | drill only; apply gated by env `drill` reviewers; smoke + teardown in `drill-teardown` |
| `drill-sweeper.yml` | cron every 15 min, dispatch | destroys expired/orphan drills |
| `drill-destroy.yml` | dispatch | manual teardown |
| `restore-drill.yml` | monthly schedule, dispatch | concurrency group `drill` |

Drill flows (T-D90, `drill.yml`; concurrency group `drill` shared with
`restore-drill.yml`, `drill-sweeper.yml`, `drill-destroy.yml`):

```
push *-deploy / dispatch (ttl_minutes, keep, boot_logs)
  ci -> build -> ttl -> apply (terraform.yml env drill, replace server + tailnet key,
                              drill_expires_at) -> smoke (/ready, 10 min)
  dispatch keep=false: + teardown (destroy)       otherwise up until TTL

pull_request -> main (ci.yml runs separately)
  build -> ttl -> apply -> smoke -> teardown (always() once apply was attempted)

drill-sweeper.yml  cron */15: Scaleway API server tags expires-at= -> destroy if expired
                   (or tagless and older than 8 h)
drill-destroy.yml  dispatch: destroy now
```

Runbook: `docs/plans/v3/runbooks/drill.md`.

Expected configuration: environments `prod` and `drill` (both with required
reviewers: every prod/drill apply waits for approval), plus ungated `prod-plan`,
`drill-plan` (PR plan legs) and `drill-teardown` (every drill destroy path and the
drill smoke job; ADR-0101). The three drill environments hold identical secrets; secrets as listed in `terraform.yml` / `deploy.yml` headers;
vars `PROD_URL`, `TAILNET_DNS_NAME` (drill environments; the drill is tailnet-only, ADR-0101,
so `drill.yml` smoke joins the tailnet as `tag:ci` and probes
`https://budget-planner-drill.${TAILNET_DNS_NAME}/ready`; ACL `tag:ci -> tag:drill:443`),
`DRILL_URL` (only for ad-hoc `deploy.yml`/`rollback.yml` on drill).
