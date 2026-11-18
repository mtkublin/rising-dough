# ADR-0121: Path-Filtered Workflows Are Not Required Checks

- **Status**: Accepted
- **Date**: 2026-11-18
- **Amends**: [ADR-0099](0099-release-and-environment-policy.md) (merge gates on `main`), `docs/plans/v3/runbooks/github-settings.md` §3
- **Relates to**: [ADR-0115](0115-drill-vm-is-exclusive-drill-lock.md), [ADR-0120](0120-pre-commit-is-the-local-gate.md)

## Context

- The `protect-main` ruleset required `fmt + validate + lint`, `plan (drill)` and `plan (prod)` from `terraform.yml`.
- `terraform.yml` runs on `pull_request` only when `terraform/**` or the workflow file changes (`paths` filter). A PR that touches neither never posts those checks, and GitHub waits for them forever. PR #23 (ci-speed, no Terraform changes) was the first such PR and stayed blocked with every other check green.
- The operator has no ruleset bypass, by design.
- Rerunning the drill gate for a workflow change in the same PR costs about 15 minutes. The operator declined it, and changed the ruleset by hand on 2026-11-18. This ADR records that change after the fact.

## Decision

1. **A workflow with a `paths` filter is never a required check.** A required check must report on every PR.
2. The `protect-main` ruleset's required checks are: `drill-gate`, `just ci (Python 3.12, ubuntu-latest)`, `uv lock --check`, `pip-audit (uv.lock)`, `trivy fs (repo)`, `trivy image (rising-dough:scan)`.
3. Terraform PRs still run `fmt + validate + lint`, `plan (drill)` and `plan (prod)`. The results show on the PR and the plan comment stays. A red result is a reason not to merge, but it no longer blocks the merge.

## Coverage after the change

| Check | Still enforced by |
|---|---|
| `fmt + validate + lint` | `drill-gate`: `drill.yml` calls `terraform.yml`, whose `fmt-validate` job runs before the drill apply. |
| `plan (drill)` | `drill-gate`: a real drill apply plus the `/ready` smoke check, a stronger check than a plan. |
| `plan (prod)` | Nothing at PR time. The release (`release.yml` → `terraform.yml`) plans prod before the approved apply, so a broken prod plan stops the release, not the merge. |

## Consequences

- PRs without Terraform changes are mergeable again.
- A Terraform change that breaks only the prod plan can merge. It is caught at release, behind the `prod` approval. Accepted: prod and drill share one root module, so most breakage also fails the drill apply.
- If a future workflow becomes required, it must run on every PR. When it only matters for some paths, it detects changes inside a job and skips its other jobs; GitHub counts a skipped required check as passing.

## Alternatives considered

- **Remove the `paths` filter and skip Terraform jobs via an in-job change check.** This keeps the three checks required. Rejected for now: it changes a merge-gate workflow and needs a drill gate rerun to land. Revisit if a prod-plan-only regression ever merges.
- **Keep the checks required and touch a Terraform file in each PR.** Rejected: a workaround, not a fix.
