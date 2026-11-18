# Workflows

Policy: ADR-0099, ADR-0109 — production releases happen only from a published
GitHub release whose tag is on `main`, through one dependency-ordered pipeline.

```
release published (tag vX.Y.Z)
  release.yml  (concurrency: release-prod)
    guard         -> tag is SemVer and an ancestor of origin/main
    ci            -> ci.yml        (workflow_call)
    build         -> build.yml     (needs ci; also tags the image vX.Y.Z; outputs image-tag, image-digest, image-ref)
    tf-apply-prod -> terraform.yml (needs build; env prod = required reviewers; image_ref = vX.Y.Z@sha256:<digest>;
                                    waits for the host agent status, auto-rollback on failure; ADR-0111)
```

| Workflow | Triggers | Notes |
|---|---|---|
| `release.yml` | release published (tag `vX.Y.Z` on `main`), dispatch (tag input, ADR-0109) | the only prod path; `guard` job first |
| `ci.yml` | pull_request `main`, workflow_call | |
| `build.yml` | workflow_call, dispatch (main or `v*` tag on main) | cosign-signed; no push/tag/release triggers |
| `terraform.yml` | pull_request (fmt/validate/tflint/plan, masked), workflow_call | inputs `env`, `image_ref` (`<tag>@sha256:<digest>`; empty = keep state), `rollback`, `replace`, `destroy`, drill-only `drill_expires_at`, `boot_log_upload`; prod requires `main` or a `v*` tag on main (`scripts/ci/ref_guard.py`); plan masked via `mask_plan.py`, `plan.bin` never uploaded (ADR-0098) |
| `rollback.yml` | dispatch (input `target`: `vX.Y.Z` or `sha-…`; empty = previous ref in state) | an apply through `terraform.yml` with `rollback: true` (ADR-0111); prod only from `main` or a `v*` tag on main |
| `drill.yml` | dispatch only (`mode=gate`\|`explore`) | drill only; gate posts commit status `drill-gate`; env `drill` reviewers optional; smoke + teardown in `drill-teardown` |
| `drill-sweeper.yml` | cron every 15 min, dispatch | destroys expired/orphan drills |
| `drill-destroy.yml` | dispatch | manual teardown |
| `litestream-plaintext-cleanup.yml` | dispatch (`dry_run`, default true) | env `prod` (approval); deletes plaintext Litestream objects from the prod replica after a green restore drill; logic in `scripts/ci/litestream_cleanup.py` (T-D56, ADR-0112) |
| `restore-drill.yml` | monthly schedule, dispatch | concurrency group `drill` |
| `uptime.yml` | cron every 5 min, dispatch | T-D44: prod `/health` + host agent status; opens one issue on failure, closes it on recovery; no secrets |

Drill flows (T-D90, `drill.yml`; concurrency group `drill` shared with
`restore-drill.yml`, `drill-sweeper.yml`, `drill-destroy.yml`):

```
dispatch (mode=gate, default)               dispatch (mode=explore, ttl_minutes, keep, boot_logs)
  gate-start (status pending)                 ci -> build -> ttl -> apply -> smoke
  ci -> build -> ttl -> apply -> smoke        keep=false: + teardown; else up until TTL
  gate-result (apply+smoke -> drill-gate)
  teardown (always() once apply was attempted)
```

PR merge gate (T-D98): branch protection requires status `drill-gate` on the PR head
SHA. Dispatch `gh workflow run drill.yml --ref <pr-branch> -f mode=gate`; a new push
needs a new run. No push or pull_request trigger exists.

```
drill-sweeper.yml  cron */15: Scaleway API server tags expires-at= -> destroy if expired
                   (or tagless and older than 8 h)
drill-destroy.yml  dispatch: destroy now
```

Runbook: `docs/plans/v3/runbooks/drill.md`.

Expected configuration: environments `prod` (required reviewers) and `drill`
(reviewers optional, T-D98), plus ungated `prod-plan`,
`drill-plan` (PR plan legs) and `drill-teardown` (every drill destroy path and the
drill smoke job; ADR-0101). The three drill environments hold identical secrets; secrets as listed in `terraform.yml` / `restore-drill.yml` headers;
var `TAILNET_DNS_NAME` (drill environments; the drill is tailnet-only, ADR-0101,
so `drill.yml` smoke joins the tailnet as `tag:ci` and probes
`https://budget-planner-drill.${TAILNET_DNS_NAME}/ready` plus the host agent status; ACL `tag:ci -> tag:drill:443`).
