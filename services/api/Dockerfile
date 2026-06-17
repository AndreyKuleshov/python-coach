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
# the `docker` CLI (baked into the runtime stage below — see the docker-cli
# stage) against a mounted /var/run/docker.sock — the sandbox image
# (python-coach-sandbox) is built on first start by docker-entrypoint.sh from
# the /app/sandbox build context shipped below. See deploy/COOLIFY_DEPLOY.md for
# the docker.sock security tradeoff + the run-as-root socket-access note.
#
# The docker CLI *client* is baked in (not bind-mounted from the host) because
# Coolify v4 drops the `-v` binds from custom_docker_run_options, so the host
# `/usr/bin/docker` never reaches the container. This image carries ONLY the
# static client binary (no dockerd/containerd/runc); it talks to the host daemon
# over the mounted socket. DOCKER_BIN stays `docker` (resolved on PATH).

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

# === docker-cli =============================================================
# Pull ONLY the static docker *client* binary from the official static bundle.
# Pinned version + sha256 so the download is reproducible and verifiable; the
# extraction toolchain (curl, tar, the tgz) stays in this throwaway stage and
# never reaches the runtime image.
FROM debian:bookworm-slim AS docker-cli

ARG DOCKER_VERSION=28.5.2
ARG DOCKER_SHA256=ea90cfd12e1eeb12aa1c971741adb8bd4ed88e2a574eaac13f5029a1dbc6300d

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    rm -rf /var/lib/apt/lists/*; \
    curl -fsSL -o /tmp/docker.tgz \
        "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_VERSION}.tgz"; \
    echo "${DOCKER_SHA256}  /tmp/docker.tgz" | sha256sum -c -; \
    # Extract only the client binary, flattening the leading docker/ dir.
    tar -xzf /tmp/docker.tgz -C /usr/local/bin --strip-components=1 docker/docker; \
    rm /tmp/docker.tgz; \
    /usr/local/bin/docker --version

# === runtime ================================================================
FROM python:3.13.1-slim-bookworm AS runtime

# Non-root: most hardened orchestrators reject root containers (docker.md).
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

# Static docker *client* binary (no daemon) — the entrypoint + sandbox client
# drive the host daemon through it via the mounted /var/run/docker.sock.
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

# The locked dependency venv from the builder (no uv, no build toolchain here).
# Built at /app/.venv in the builder so the copied path matches the shebangs.
COPY --from=builder /app/.venv /app/.venv

# Application code only: the importable package + the static SPA the app serves.
# app.py resolves static/ as parents[2]/"static" relative to the package file
# (src/python_coach/app.py -> /app/static), so the layout below must hold.
COPY services/api/src /app/src
COPY services/api/static /app/static
# pyproject ships ONLY for its [tool.alembic] config (script_location), which the
# entrypoint's `alembic upgrade head` reads from the cwd. No secrets live here.
COPY services/api/pyproject.toml /app/pyproject.toml

# Sandbox build context: the entrypoint runs `docker build /app/sandbox` on the
# host (mounted socket) at startup, so the tiny, secret-free sandbox sources
# must ship inside this image. They are NOT installed/imported by the API.
COPY services/sandbox /app/sandbox

# Real methodist lessons the entrypoint seeds idempotently on every start.
# Only lesson_*.json — the placeholder fixture is deliberately excluded (both by
# the COPY glob and by .dockerignore).
COPY fixtures/lesson_*.json /app/seed-fixtures/

# Self-provision entrypoint: builds the sandbox image, migrates, seeds, execs uvicorn.
COPY services/api/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# NOTE on user: the entrypoint must drive the host Docker daemon via the mounted
# /var/run/docker.sock (root:docker on the host). A non-root container cannot
# open that socket, so this image is run as ROOT in production via
# custom_docker_run_options (`--user 0`). The socket mount already grants
# effective host-root to this container, so the trust boundary is unchanged —
# see deploy/COOLIFY_DEPLOY.md. The non-root `appuser` (uid 10001) remains
# defined for environments that do not need the socket; the deploy explicitly
# overrides it. We intentionally do NOT `USER appuser` here.

EXPOSE 8000

# Bind 0.0.0.0 so Traefik (Coolify's proxy) can reach the container. One worker:
# grading is synchronous and single-user scale; scale via replicas if needed.
ENTRYPOINT ["docker-entrypoint.sh"]
