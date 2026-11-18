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

1. New workflow `.github/workflows/drill-gate-skip.yml` runs on `pull_request_target` to `main` (opened, synchronize, reopened, ready_for_review) with `statuses: write`, `contents: read` and `pull-requests: read` only. With `pull_request_target` the workflow file and the classifier both come from the base branch, so a PR cannot edit them to approve itself.
2. It lists the PR's changed files through the GitHub API (paginated; renames contribute both old and new path) and feeds them to `scripts/ci/drill_gate_skip.py`.
3. The classifier is an **allowlist** and fails closed. Every changed path must be: under `docs/`, `.claude/` or `tests/`; a top-level `LICENSE*`; or a `*.md` file outside `.github/`, `src/`, `terraform/`, `deploy/`, `scripts/` and `migrations/`. Everything else, including `.github/**`, `scripts/**`, `src/**`, `migrations/**`, `terraform/**`, `deploy/**`, `Dockerfile`, `.dockerignore`, `pyproject.toml`, `uv.lock`, `justfile`, `.pre-commit-config.yaml` and unknown paths, means `gate`. An empty diff, a path with `..` or an absolute path, and a file list at the API cap (3000) mean `gate`.
4. On `skip` it posts `drill-gate` = `success` with description `skipped: no deploy-relevant changes (ADR-0121)` on the PR head SHA. On `gate` it posts nothing and logs the paths that need the real gate. It never posts `pending` or `failure`.

## Consequences and threat model

- The workflow cannot approve edits to itself: it runs from the base branch, and `.github/**` and `scripts/**` are never skip-safe, so such PRs always need the real gate.
- `pull_request_target` is only safe if no PR code runs, so: the checkout is the base SHA with `persist-credentials: false`; the file list comes from `gh api --paginate`; the status goes on `pull_request.head.sha`; PR-controlled values (numbers, SHAs) reach scripts only through `env:`, never interpolated into `run:`; file names are read from files and stdin. Tests enforce this.
- A real gate run (`drill.yml`, `mode=gate`) can always overwrite the status for a SHA, since the skip never posts a terminal failure that would stick.
- Threat model: single-owner repository with no outside contributors holding write access; a malicious change merged to `main` itself is out of scope.
- The PR that first adds the workflow gets no run (the base has no workflow yet), so it needs a real gate.

## Alternatives rejected

- Path filters in `on.pull_request.paths-ignore`: a skipped workflow posts no status, which is the blocking problem.
- Denylist of deploy paths: a new deploy-relevant path would silently skip.
