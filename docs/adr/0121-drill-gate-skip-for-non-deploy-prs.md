# ADR-0121: Drill-Gate Skip for Non-Deploy PRs

- **Status**: Accepted
- **Date**: 2026-11-18
- **Amends**: ADR-0099 (PR merge gate)
- **Relates to**: ADR-0115
- **Task**: T-D147

## Context

ADR-0099 requires a passing `drill-gate` commit status on every PR head SHA. A docs-only PR cannot change what is deployed, yet it needs a full drill (VM apply, smoke, teardown). The owner decided on 2026-11-18 that this is overkill.

The image copies only `pyproject.toml`, `uv.lock`, `src`, `migrations` and `deploy/docker-entrypoint.sh` (`Dockerfile`), and `.dockerignore` excludes `tests/`, `docs/` and `.claude/`.

## Decision

1. New workflow `.github/workflows/drill-gate-skip.yml` runs on `pull_request` to `main` (opened, synchronize, reopened, ready_for_review) with `statuses: write` and `contents: read` only.
2. It lists the PR's changed files through the GitHub API (paginated; renames contribute both old and new path) and feeds them to `scripts/ci/drill_gate_skip.py`.
3. The classifier is an **allowlist** and fails closed. Every changed path must be: under `docs/`, `.claude/` or `tests/`; a top-level `LICENSE*`; or a `*.md` file outside `.github/`, `src/`, `terraform/`, `deploy/`, `scripts/` and `migrations/`. Everything else, including `.github/**`, `scripts/**`, `src/**`, `migrations/**`, `terraform/**`, `deploy/**`, `Dockerfile`, `.dockerignore`, `pyproject.toml`, `uv.lock`, `justfile`, `.pre-commit-config.yaml` and unknown paths, means `gate`. An empty diff, a path with `..` or an absolute path, and a file list at the API cap (3000) mean `gate`.
4. On `skip` it posts `drill-gate` = `success` with description `skipped: no deploy-relevant changes (ADR-0121)` on the PR head SHA. On `gate` it posts nothing and logs the paths that need the real gate. It never posts `pending` or `failure`.

## Consequences and threat model

- The workflow cannot approve edits to itself: `.github/**` and `scripts/**` are never skip-safe, so changing the workflow or the classifier always needs the real gate. The classifier is also checked out from the PR base commit, so a PR cannot loosen the rule that judges it.
- A real gate run (`drill.yml`, `mode=gate`) can always overwrite the status for a SHA, since the skip never posts a terminal failure that would stick.
- Threat model: single-owner repository. The `pull_request` trigger gets a read-only token for forks and no secrets, and there are no outside contributors with write access. The workflow file itself is read from the PR merge ref; a PR that edits it is `gate` by rule 3, and a malicious owner-authored workflow edit is out of scope.
- The first PR that adds the classifier runs without it on base, so the step fails and no status is posted (fail closed).

## Alternatives rejected

- Path filters in `on.pull_request.paths-ignore`: a skipped workflow posts no status, which is the blocking problem.
- Denylist of deploy paths: a new deploy-relevant path would silently skip.
