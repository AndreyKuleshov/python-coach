# Production image for the python-coach API (FastAPI + static SPA).
#
# Multi-stage per .claude/rules/docker.md: a builder stage installs the LOCKED
# runtime dependencies into a venv with uv; the runtime stage is a clean slim
# image that copies only that venv + the application source (src/ + static/).
# No uv, no compilers, no dev/test deps, no harness, sources, docs or tests in
# the runtime layer (those are also excluded by the repo .dockerignore).
#
# Build context = repo root (the .dockerignore lives there and prunes the
# context). Build with:
#   docker build -f services/api/Dockerfile -t python-coach-api:<tag> .
#
# NOTE: this image runs ONLY the API. It spawns the grading sandbox by calling
# the host `docker` CLI against a mounted /var/run/docker.sock — the sandbox
# image (python-coach-sandbox) must already exist on the host. See
# deploy/COOLIFY_DEPLOY.md for the docker.sock security tradeoff.

# === builder ================================================================
FROM python:3.13.1-slim-bookworm AS builder

# uv copied from its own pinned image — no curl|sh, reproducible.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    # Build the venv at the SAME path it will occupy at runtime so console-script
    # shebangs (alembic, uvicorn) point at /app/.venv/bin/python, not /build/...
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /build

# Least- to most-volatile: lockfiles first so dependency resolution caches
# independently of source changes. The workspace root pyproject + lock pin the
# exact dependency set; the API member pyproject declares the runtime deps.
COPY pyproject.toml uv.lock ./
COPY services/api/pyproject.toml services/api/pyproject.toml

# Install ONLY the locked runtime deps (no dev group, no editable project) into
# a standalone venv. --no-install-project: the app code is copied in plain at
# runtime, not installed, so a source change does not bust the dependency layer.
RUN uv sync --frozen --no-dev --no-install-project --package python-coach

# === runtime ================================================================
FROM python:3.13.1-slim-bookworm AS runtime

# Non-root: most hardened orchestrators reject root containers (docker.md).
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

# The locked dependency venv from the builder (no uv, no build toolchain here).
# Built at /app/.venv in the builder so the copied path matches the shebangs.
COPY --from=builder /app/.venv /app/.venv

# Application code only: the importable package + the static SPA the app serves.
# app.py resolves static/ as parents[2]/"static" relative to the package file
# (src/python_coach/app.py -> /app/static), so the layout below must hold.
COPY services/api/src /app/src
COPY services/api/static /app/static
# pyproject ships ONLY for its [tool.alembic] config (script_location), which the
# release-step `alembic upgrade head` reads from the cwd. No secrets live here.
COPY services/api/pyproject.toml /app/pyproject.toml

USER appuser

EXPOSE 8000

# Bind 0.0.0.0 so Traefik (Coolify's proxy) can reach the container. One worker:
# grading is synchronous and single-user scale; scale via replicas if needed.
CMD ["uvicorn", "python_coach.app:app", "--host", "0.0.0.0", "--port", "8000"]
