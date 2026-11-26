# ADR-0152: Python Upgrade (3.15, Fallback 3.14) and a Native arm64 Dev Interpreter

- **Status**: Proposed (accepted once the T-SC08 feasibility probe passes; it names the chosen version)
- **Date**: 2026-11-26
- **Amends**: `requirements.md` §3.1 ("Python 3.12") and §3.6 (CI matrix row) once accepted; [ADR-0018](0018-ci-single-matrix-row.md) (Python version of the single row); [ADR-0067](0067-auth-backend-sessions-and-passkey-challenges.md) (macOS x86_64 dependency caps)
- **Relates to**: [ADR-0004](0004-package-manager-uv.md), [ADR-0151](0151-capacity-and-scaling-strategy-per-distribution-stage.md) §3, [ADR-0153](0153-native-hot-paths-via-pyo3.md)
- **Plan**: [`docs/plans/scaling/tasks.md`](../plans/scaling/tasks.md) T-SC07, T-SC08

## Context

- `pyproject.toml` pins `requires-python = ">=3.12,<3.13"`, set at scaffolding (T-001) and never revisited. `.python-version`, the `Dockerfile` and the workflows (`ci.yml`, `e2e.yml`, `security.yml`, `a11y-perf.yml`, `mutation.yml`) carry 3.12.
- Python 3.15 is the latest stable release (about two months old on 2026-11-26); 3.14 is a year old. Newer interpreters are faster with no code change, which raises the per-host CPU ceiling (ADR-0151 §1).
- The developer machine is an arm64 Mac, but the dev toolchain is x86_64 under Rosetta: `uv` comes from Anaconda (`/opt/anaconda3/bin/uv`, `x86_64-apple-darwin`), so every uv-managed Python and `.venv` is x86_64. ADR-0067 caps `cbor2<6` (everywhere) and `cryptography<49` (macOS x86_64 only) because those projects ship no macOS x86_64 wheels. More projects drop Intel-Mac wheels with each release, so an upgrade on x86_64 hits the same wall again. A first attempt to install a native uv on 2026-11-26 failed; it is retried in T-SC07.

## Decision

1. **Native arm64 dev toolchain first (T-SC07).** Install an arm64 `uv` that wins on `PATH` over Anaconda's (`uv --version` reports `aarch64-apple-darwin`), reinstall the managed interpreters, recreate `.venv` in the main checkout and every active worktree, and run `pre-commit clean` before reinstalling hooks (hook environments are cached per architecture). The fallback without replacing uv is an explicit request key (`--python cpython-3.12-macos-aarch64-none` or `UV_PYTHON`) used locally only. **The arch-specific key never goes into `.python-version`**, which Linux CI and the Docker build read.
2. **Upgrade target 3.15, fallback 3.14 (T-SC08).** Feasibility probe on a branch: `uv lock --python 3.15`, `uv sync`, all pre-commit hooks, the full suite in CI. Native-extension dependencies are the risk: cryptography, cbor2, pydantic-core, argon2-cffi, libcst (pinned `<1.9`), and the tooling (mypy, mutmut, pytest-testmon, import-linter). Any blocker without a wheel or a fix falls back to 3.14 and is recorded, with a revisit date.
3. **One change moves every pin**: `requires-python`, `.python-version`, `Dockerfile` base image, every workflow `python-version`, ruff `target-version` and mypy `python_version`. ADR-0018 keeps a single matrix row.
4. **Dependency caps are revisited** in the same change. On arm64 the `cryptography<49` marker no longer applies; `cbor2<6` is removed if nothing else needs it. ADR-0067 gets an amendment.
5. **Measured, not assumed.** The T-SC05 load baseline is re-run after the upgrade; the gain is recorded in the plan's baseline file.

## Consequences

- Faster interpreter in prod and in CI; faster local test runs without Rosetta.
- Fewer dependency caps; fewer surprises from dropped Intel-Mac wheels.
- One-time cost: environment rebuilds in every worktree, a testmon full rerun, possible small fixes for deprecations removed in 3.13–3.15.

## Alternatives considered

- **Stay on 3.12**: leaves free speed on the table, and 3.12 reaches end of security support in 2028.
- **Upgrade on the x86_64 dev toolchain**: repeats the ADR-0067 wheel problem.
- **Commit an arch-specific `.python-version`**: breaks the Linux CI and Docker builds.
