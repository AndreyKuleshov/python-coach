#!/usr/bin/env sh
# Container entrypoint — self-provision on every start, then exec the API.
#
# Runs four ordered steps so a `git push` -> Coolify rebuild needs ZERO manual
# follow-up (no host `docker build`, no `alembic upgrade`, no seed run):
#
#   a. Build/refresh the sandbox grader image on the HOST via the mounted
#      /var/run/docker.sock. Tolerate failure (logged warning) so a transient
#      build problem never stops the API from booting. Docker's layer cache
#      makes this a near-instant no-op when services/sandbox/ is unchanged.
#   b. alembic upgrade head — apply migrations (fail-fast: a broken schema must
#      stop the boot rather than serve against a half-migrated DB).
#   c. Seed published lessons idempotently (upsert-by-slug, safe every start).
#      The placeholder fixture is intentionally NOT shipped, so the glob only
#      ever matches real methodist content.
#   d. exec uvicorn (replaces PID 1 so signals reach the server cleanly).
#
# POSIX sh (the slim image has no bash). The API runs as root here (see the
# socket-access note in deploy/COOLIFY_DEPLOY.md) so it can drive host Docker.
set -eu

log() { echo "[entrypoint] $1"; }

# --- a. sandbox grader image (best-effort; never blocks the API) ------------
if [ -S /var/run/docker.sock ]; then
    log "building sandbox image ${SANDBOX_IMAGE} from /app/sandbox (host docker)"
    if docker build -t "${SANDBOX_IMAGE}" /app/sandbox; then
        log "sandbox image ${SANDBOX_IMAGE} ready"
    else
        log "WARNING: sandbox image build failed; grading will fail until it exists"
    fi
else
    log "WARNING: /var/run/docker.sock not mounted; skipping sandbox build (grading disabled)"
fi

# --- b. migrations (fail-fast) ----------------------------------------------
log "applying migrations: alembic upgrade head"
alembic upgrade head

# --- c. seed published lessons (idempotent upsert-by-slug) ------------------
if [ -d /app/seed-fixtures ]; then
    for f in /app/seed-fixtures/lesson_*.json; do
        # Guard the literal-glob case (no matches) so we don't seed "lesson_*.json".
        [ -e "$f" ] || continue
        log "seeding $(basename "$f")"
        python -m python_coach.seed "$f"
    done
else
    log "no /app/seed-fixtures directory; skipping seed"
fi

# --- d. hand off to uvicorn -------------------------------------------------
log "starting uvicorn"
exec uvicorn python_coach.app:app --host 0.0.0.0 --port 8000
