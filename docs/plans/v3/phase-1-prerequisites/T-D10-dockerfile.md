# T-D10 — Dockerfile (multi-stage, non-root)

- **Phase**: 1 — App Prerequisites
- **Parallel-safe**: yes
- **Depends on**: nothing
- **Blocks**: T-D11 (docker-compose), T-D13 (CI security scans), T-D23 (cloud-init), T-D30 (build workflow)
- **References**: ADR-0032 §2 (application packaging), ADR-0034 (volume shape for `/data`)

## Context

Rising Dough v3 ships to Scaleway Stardust as an OCI image pulled from GHCR
(ADR-0032 §2). The image must be:

- **Multi-stage** — build layer isolates `uv`, `pip`, and build toolchain; the
  final layer carries only the runtime venv + source + `curl` for the
  healthcheck. Keeps the shipped image small and the attack surface minimal
  (no shell package manager, no compilers).
- **Non-root** — the final layer runs as `app` (uid/gid `10001`) with
  `/usr/sbin/nologin`. The container never needs root at runtime; Litestream
  is a sibling container (not a sidecar in this image) per ADR-0034 §Design.
- **`/data`-aware** — ADR-0034 pins the DB file at `/data/budget.db` and the
  host mounts the volume at `/data` mode `0700` owned by `app`. The image
  pre-creates the directory with the right ownership so a fresh VM boot
  succeeds even before any file lands in the volume.
- **Health-probing** — exposes a `HEALTHCHECK` that curls `/health` (T-D01).
  Caddy and the deploy workflow rely on container-level health before
  flipping traffic.

## Deliverables

1. `Dockerfile` at repo root with two named stages:
   - `builder` (`python:3.12-slim-bookworm`): installs `build-essential` +
     `pip install uv`; copies `pyproject.toml` + `uv.lock`; runs
     `uv sync --frozen --no-dev --no-install-project --compile-bytecode`
     into `/app/.venv`.
   - `runtime` (`python:3.12-slim-bookworm`): installs only `curl` +
     `ca-certificates` (apt lists cleaned); creates `app` uid/gid `10001`
     with `/usr/sbin/nologin`; copies venv from `builder`; copies `src/`
     and `migrations/` with `--chown=app:app`; `ENV PATH`, `PYTHONPATH`,
     `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`; creates `/data`
     mode `0700` owned by `app`; `USER app`; `EXPOSE 8000`;
     `HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS
     http://127.0.0.1:8000/health || exit 1`;
     `CMD ["uvicorn", "budget_planner.web.app:app", "--host", "0.0.0.0",
     "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]`.
2. `.dockerignore` at repo root excluding anything that bloats the build
   context or risks shipping local state / credentials: `tests/`, `docs/`,
   `local/`, `.claude/`, `data/`, `.git/`, `.github/`, `.venv/`,
   `node_modules/`, `terraform/`, `*.sqlite*`, `.ruff_cache/`,
   `.pytest_cache/`, `.mypy_cache/`, `__pycache__/`, `.DS_Store`, `.env*`
   (keep `.env.example` tracked so the image can be re-derived from the
   repo alone).
3. `justfile` recipe `docker-build` → `docker build -t rising-dough:dev .`.

## Acceptance criteria

- `docker build -t rising-dough:dev .` succeeds on a clean checkout.
- `docker run --rm rising-dough:dev id` prints `uid=10001(app) gid=10001(app)`.
- `docker image inspect rising-dough:dev` shows:
  - `Config.User` = `app`.
  - `Config.ExposedPorts` includes `8000/tcp`.
  - A non-empty `Config.Healthcheck` block pointing at `/health`.
- The final image contains no apt lists (`/var/lib/apt/lists` is empty) and
  no `uv` binary in `$PATH` (the builder-only toolchain does not leak). `pip`
  stays as shipped by `python:3.12-slim-bookworm`; stripping it adds no
  meaningful security benefit for a non-root image.
- `.dockerignore` keeps the build context under 10 MB (smoke-check via
  `docker build --progress=plain .` showing the sent context size).

## Validation hook

- `just docker-build` from a fresh clone on a host with Docker running.
- Follow-up tasks (T-D11, T-D30) consume this image unchanged.

## Scope boundary

- No `docker-compose.yml`, Caddy config, or Litestream config here — those
  belong to T-D11.
- No application code changes. T-D01 already provides `/health`; this task
  only wires the container's healthcheck to it.
