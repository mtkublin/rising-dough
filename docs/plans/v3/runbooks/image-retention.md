# Runbook: GHCR image retention (T-D126, ADR-0099)

## Context
Every release and drill gate pushes a `sha-...` image, its untagged child manifests (provenance, SBOM) and cosign signature artifacts (`sha256-<digest>.sig`) to `ghcr.io/mtkublin/budget-planner`. `image-retention.yml` prunes them weekly (Monday 03:17 UTC) with `scripts/ghcr_retention.py`.

Keep: newest 20 `sha-*` versions; anything tagged `main` or `v*`; every version younger than 7 days; child manifests of kept images; signatures of kept images. Delete (older than 7 days): untagged versions, orphaned `.sig`/`.att`/`.sbom` artifacts, `sha-*` beyond the newest 20. Unrecognised tags are kept.

Assumption: prod's current and previous images are within the newest 20 `sha-*` (rollback depth 1; ~20 releases/drill gates would have to land between two weekly runs to break it). `main`/`v*` tags also protect the latest release.

## Preconditions
- Package `budget-planner` is linked to the repo with Actions role Write (package settings > Manage Actions access).
- Operator `gh` token has `read:packages` for the read-only check (`gh auth refresh -s read:packages`).

## Procedure
1. Dry run: Actions > image-retention > Run workflow with `dry_run` left true. Read the plan in the step summary (every `DELETE` line has a reason).
2. Optional: `gh api /users/mtkublin/packages/container/budget-planner` for visibility and version count.
3. One manual real run: dispatch with `dry_run=false`; confirm prod still pulls (`deploy.md` smoke) and `cosign verify` of the kept `main` image still works.
4. Enable the schedule: repo Settings > Secrets and variables > Actions > Variables: `IMAGE_RETENTION_ENABLED=true`. Remove it (or set anything else) to return to dry-run.

## Verification
Step summary shows `mode: APPLY` and `deleted <id>` lines; the package version count drops; a new release still builds and deploys.

## Troubleshooting
- 403/404 on listing or delete: package not linked to the repo or Actions access is not Write.
- Plan refuses with "no versions found" / "kept nothing": nothing is deleted by design.

## Rollback
Deleted versions cannot be restored. Rebuild an image from its commit via `build.yml` if needed.
