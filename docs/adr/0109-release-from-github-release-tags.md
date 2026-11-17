# ADR-0109: Prod Releases Triggered by GitHub Releases on `main`

- **Status**: Accepted
- **Date**: 2026-11-16
- **Relates to**: ADR-0099 (release and environment policy), ADR-0100, T-D125, T-D126
- **Amends**: ADR-0099 (release trigger: push to `main` → published GitHub release whose tag is on `main`)

## Context

ADR-0099 releases prod on every push to `main` (`release.yml`: ci → build → tf-apply-prod with approval → deploy-prod → smoke). Merging and releasing are therefore one act: several PRs cannot be batched, prod versions are only commit SHAs, and there are no release notes.

## Decision

1. **Trigger.** `release.yml` runs on `release: types: [published]` (plus `workflow_dispatch` for re-running a given tag). It no longer runs on `push` to `main`. Merging to `main` builds nothing for prod.
2. **Guard: prod only from `main`.** The first job checks out the tag and fails unless `git merge-base --is-ancestor <tag commit> origin/main`. The `GITHUB_REF == refs/heads/main` checks in `build.yml`, `terraform.yml` and `deploy.yml` become "ref is `main` or a `v*` tag whose commit is on `main`" (one shared script, tested).
3. **Versions.** Tags are SemVer `vMAJOR.MINOR.PATCH`. `build.yml` pushes the image as `sha-<short>` and `v…`; the deploy script records the version tag for `current`/`previous`. Rollback (`rollback.yml`) accepts a version or a SHA tag.
4. **Tag protection.** A tag ruleset on `v*`: creation by the operator only, no deletion, no update (tags are immutable).
5. **Unchanged.** The PR gate (`drill-gate` + checks via `protect-main`), the `prod` environment approval and ADR-0100 credentials.

## Implementation notes (T-D125, 2026-11-16)

- One tested script, `scripts/ci/ref_guard.py`, holds the rule: `ref` (main, or `refs/tags/vX.Y.Z` whose commit is an ancestor of `origin/main`), `deploy-tag` (`sha-<hex>` or `vX.Y.Z`), `rollback-target` (version, `sha-<hex>` or bare SHA). `release.yml`, `build.yml` (direct dispatch), `terraform.yml` (prod), `deploy.yml` (prod) and `rollback.yml` (prod) call it after a full-history checkout.
- `release.yml` has a `guard` job first. A `workflow_dispatch` re-run needs "Use workflow from" set to the tag and the `tag` input equal to it, so the built commit is always the tag commit.
- The version tag reaches terraform and deploy only through the existing `image_tag` inputs. The on-host deploy script already accepts `vX.Y.Z` (tag regex), so no host change is needed. `drill.yml` keeps passing `sha-<short>`.
- `rollback.yml` input `image_sha` is replaced by `target`.

## Consequences

- Prod can lag `main`; release notes on GitHub describe each version.
- One extra manual step per release (create the release); the approval gate stays.
- The merge of the PR implementing this ADR is the last merge-triggered release.

## Alternatives considered

- **Keep merge = release** (status quo): simplest, `main` always equals prod, no versions.
- **Tag push without a GitHub release** (`push: tags: [v*]`): same mechanics, no release notes; a published release gives notes for free.
