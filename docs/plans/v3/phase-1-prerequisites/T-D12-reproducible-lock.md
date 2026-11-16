# T-D12 — Reproducible dependency lock

- **Phase**: 1 — App Prerequisites
- **Parallel-safe**: yes
- **Depends on**: nothing
- **Blocks**: T-D30 (CI image build consumes the frozen lock)
- **References**: ADR-0004 (uv as package manager)

## Context

Reproducible builds require `uv.lock` to be the sole source of truth for versions. `just install` uses `uv sync --group dev` today, which may drift when transitive versions change. CI must fail on an out-of-date lock before an image build consumes it.

## Deliverables

1. Verify `uv.lock` is committed and current.
2. `justfile` `install` recipe switches to `uv sync --frozen --group dev` so local installs match CI exactly.
3. `.github/workflows/lock-check.yml` runs `uv lock --check` on every PR. Minimal workflow (checkout + setup-uv + lock check), with actions pinned by SHA for supply-chain safety.

## Acceptance criteria

- `just install` fails if the lock drifts from `pyproject.toml`.
- `lock-check.yml` runs on `pull_request` targeting `main` and `v3`.
- Removing a line from `uv.lock` and opening a PR reproduces the failure (manual check during review).

## Validation hook

```sh
uv lock --check
```
