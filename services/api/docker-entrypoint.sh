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
#   c. Seed published lessons ONCE, on a fresh DB only. The seed CLI replaces a
#      lesson via delete+insert (cascade), so re-running it on a populated DB
#      reassigns exercise IDs and cascade-deletes learners' submissions/progress.
#      We therefore guard on the lesson count: seed only when the table is empty.
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

# --- c. seed published lessons (first-time only; never wipe existing data) --
# Count existing lessons through the app's own DB layer (honours DATABASE_URL /
# asyncpg). A non-empty table means a real DB with learner progress, which the
# delete+insert seed would clobber, so we skip seeding entirely on redeploys.
lesson_count=$(python -c '
import asyncio
from sqlalchemy import func, select
from python_coach.storage.db import session_factory
from python_coach.storage.models.lesson import Lesson


async def _count() -> int:
    async with session_factory()() as session:
        # exec() wraps the aggregate in a Row; [0] unwraps the scalar count.
        result = await session.exec(select(func.count()).select_from(Lesson))
        return result.one()[0]


print(asyncio.run(_count()))
')

if [ "$lesson_count" -gt 0 ]; then
    log "lessons present ($lesson_count); skipping seed to preserve progress"
elif [ -d /app/seed-fixtures ]; then
    log "empty DB; seeding published lessons (first-time only)"
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
