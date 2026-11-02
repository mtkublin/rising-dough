# syntax=docker/dockerfile:1.7
# Rising Dough v3 — multi-stage, non-root runtime image.
# See docs/adr/0032-v3-remote-deployment-scaleway-stardust-warsaw.md §2
# and docs/adr/0034-v3-sqlite-replication-litestream.md.

# ---------------------------------------------------------------------------
# Stage 1 — builder: resolves and compiles the venv with `uv`.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1

# Build toolchain only lives in this stage. The final stage carries just
# the resolved venv, so none of these binaries ship.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app

# Copy only the lockfile + project metadata first so `uv sync` is cache-friendly.
COPY pyproject.toml uv.lock ./

# Resolve a production venv at /app/.venv. --no-install-project keeps the
# source tree out of the venv so we can mount it fresh in the runtime stage
# without triggering a reinstall.
RUN uv sync \
    --frozen \
    --no-dev \
    --no-install-project \
    --compile-bytecode

# ---------------------------------------------------------------------------
# Stage 2 — runtime: minimal non-root image.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# `curl` for the container healthcheck (hits /health, see T-D01).
# `ca-certificates` so outbound HTTPS (frankfurter FX etc.) works.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Dedicated non-root account. uid/gid 10001 is high enough to avoid
# collisions with host-provided accounts and matches ADR-0032 §2.
RUN groupadd --system --gid 10001 app \
    && useradd \
        --system \
        --uid 10001 \
        --gid 10001 \
        --home-dir /app \
        --shell /usr/sbin/nologin \
        app

WORKDIR /app

# Bring in the resolved venv from the builder stage. Owned by app so the
# runtime user can read it without extra chmod shuffling.
COPY --from=builder --chown=app:app /app/.venv /app/.venv

# Application source + migrations. Tests, docs, local scratch, and `.claude/`
# are kept out of the image via .dockerignore.
COPY --chown=app:app src /app/src
COPY --chown=app:app migrations /app/migrations

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# /data holds the SQLite file and Litestream metadata on the host (see
# ADR-0034). Pre-create it so a cold boot before Litestream populates the
# volume still gives FastAPI a usable directory. Mode 0700 matches the
# host-mounted volume contract in ADR-0032 §2.
RUN mkdir -p /data \
    && chown app:app /data \
    && chmod 0700 /data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "budget_planner.web.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--forwarded-allow-ips=*"]
