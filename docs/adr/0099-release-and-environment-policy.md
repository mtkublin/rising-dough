# ADR-0099: Release and Environment Policy

- **Status**: Accepted
- **Date**: 2026-11-07
- **Relates to**: ADR-0035, ADR-0037, ADR-0094, ADR-0096, ADR-0097, ADR-0098; forward-references ADR-0100 (CI credentials, written by T-D92)

## Context

v3 has two environments, `prod` and `drill` (disposable). Until now nothing stated who may build, apply or deploy to prod, and the existing `deploy.yml` chains `build -> drill -> prod` through `workflow_run`. During bring-up, applies ran from the operator laptop with an admin Scaleway key in `terraform/.env`, and a plan leaked secrets (ADR-0098). Prod holds the only canonical user data, so the release path must be single, auditable and enforced technically, not by convention.

## Decision

1. **Prod releases only via GitHub Actions from `main`.** Nothing builds, applies, deploys or pushes images for prod from anywhere else: not laptops, not other branches, not ad-hoc dispatch on non-`main` refs.
2. **Main pipeline** (dependency tree): push to `main` -> `ci` -> `build` (only if ci is green; publishes the immutable `sha-<short>` image and its cosign signature) -> `terraform apply prod` (GitHub environment `prod`, required reviewer approval; image tag taken from the build output) -> `deploy prod` (SSH image swap over the tailnet, environment `prod`, ADR-0037, ADR-0094) -> smoke `/ready`. Implemented by a new orchestrating `release.yml` that calls reusable (`workflow_call`) ci / build / terraform / deploy workflows (T-D89). There is no drill stage on `main`: the drill is validated pre-merge (item 3).
3. **Drill deploys** (T-D90). One reusable drill pipeline: build -> terraform apply drill (server and tailnet key replaced) -> deploy -> smoke. Triggers:
   - push to any branch matching `*-deploy`, and `workflow_dispatch` on any branch (input `ttl_minutes`, default 60). The drill stays up for the TTL; a scheduled sweeper (every 15 min) destroys expired drills; a manual `drill-destroy` dispatch tears down early.
   - `pull_request` to `main`: pre-merge gate. Ephemeral drill, torn down at the end of that pipeline (success or failure). Required check before merge.
   - There is a single drill environment, so all drill workflows share one concurrency group (`drill`), queued not cancelled. `restore-drill.yml` joins it.
4. **Exceptions** (the only non-GitHub actions allowed):
   a. One-time initial prod bring-up from the operator laptop on 2026-11-07 (terraform apply of prod with image `sha-075f986`, plan reviewed by the user). After it, item 1 applies without exception.
   b. The bootstrap stack (`terraform/bootstrap`, ADR-0096) stays local-only: it creates the state buckets and the CI credentials CI cannot create for itself.
   c. Break-glass for a GitHub outage or stuck state lock: an org-admin Scaleway key kept only in the operator's password manager (never in `terraform/.env`); each use is logged in `docs/CHANGELOG.md` with the reason. Runbook: [break-glass.md](../plans/v3/runbooks/break-glass.md) (written by T-D92).
   d. One-time copy of the local prod DB (`data/budget.sqlite`) to the prod instance once prod is up, before real use: consistent snapshot via `sqlite3 .backup`, transferred over the tailnet, app and Litestream stopped, migrations run on app start, Litestream starts a new generation. Requires explicit in-session user go at execution time (the CLAUDE.md prod-DB rule still applies). Runbook and script: [prod-db-seed.md](../plans/v3/runbooks/prod-db-seed.md) (T-D93).
5. **Enforcement is by credentials, not convention.** After T-D92 the only prod-write credentials live in the GitHub `prod` environment secrets (least-privilege CI IAM application per environment, created by the bootstrap stack, ADR-0100). The leaked admin key is rotated and `terraform/.env` keeps no prod-write key. Manual GitHub settings (checklist, T-D92):
   - environment `prod`: required reviewer, deployment branch policy `main` only;
   - environment `drill`: branches `*-deploy`, `main` and PR refs;
   - branch protection on `main` requiring `ci` and the pre-merge drill check.
6. **CI policy unchanged** (ADR-0097). The temporary `v3` push trigger in `build.yml` (T-D76) is removed by T-D89.

## Consequences

- One auditable path to prod; a laptop or feature branch cannot touch it because it lacks the credentials and the environment branch policy rejects it.
- Every PR to `main` pays one drill cycle (apply, deploy, smoke, destroy) and serialises behind other drill runs.
- `deploy.yml`'s `workflow_run` chain (drill then prod) and the docs describing it are superseded by T-D89 and T-D90; until they land, existing workflows and runbooks describe the old flow.
- Break-glass and the prod DB seed are explicit, logged exceptions rather than silent habits.
- The 1 h default TTL bounds drill cost and the lifetime of drill secrets and break-glass access.

## Alternatives considered

- **Branch suffix `*-deploy` alone**: forces renaming branches to get a drill. Rejected as the only trigger; kept for push-to-deploy.
- **`workflow_dispatch` alone**: loses push-to-deploy. Rejected as the only trigger; kept for any-branch drills.
- **PR label to start a drill**: ties drills to PRs and needs a PR first. Considered and rejected.
- **Drill stage on `main` before prod** (the old `workflow_run` chain): duplicates the pre-merge gate and slows every release. Rejected.
- **Convention only** (documented rule, admin key on laptop): a leaked or stale key already proved this fragile. Rejected in favour of credential scoping.

## Amendment 2026-11-07 (T-D90)

- The drill pipeline smoke-tests instead of calling `deploy.yml`: every drill apply replaces the server, and the fresh boot's cloud-init already runs `app_image_tag` (the freshly built tag), so the SSH swap would be a no-op. The smoke job waits for the public `/ready` (budget 10 min; fresh boot ~3.5 min). `deploy.yml` still accepts `env: drill` for ad-hoc use.
- TTL is stored as the Scaleway server tag `expires-at=<RFC3339 UTC>` (Terraform var `drill_expires_at`, drill-only) so the sweeper needs no state access.
- Destroy runs pass the placeholder `image_tag: sha-0000000`; `app_image_tag` only feeds user-data, which a destroy plan never creates.
