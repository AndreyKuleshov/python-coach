#!/usr/bin/env bash
# Phase-B Coolify deploy for python-coach. Reads COOLIFY_HOST + COOLIFY_API_TOKEN
# from services/api/.env and performs the ordered create/deploy calls documented
# in deploy/COOLIFY_DEPLOY.md.
#
# SAFETY: this script is a DRY-RUN by default. It prints every call it WOULD make
# and exits 0 WITHOUT touching Coolify unless invoked with --go. The docker.sock
# mount (step 4) and creating live infra need explicit owner sign-off first.
#
#   bash deploy/coolify-deploy.sh           # dry-run: print the plan, change nothing
#   bash deploy/coolify-deploy.sh --go      # Phase B: actually create/deploy
#
# Idempotency is NOT guaranteed — read deploy/COOLIFY_DEPLOY.md and confirm the
# inventory before --go. Secrets are entered via env (see SECRETS below), never
# committed.
set -euo pipefail

GO=false
[ "${1:-}" = "--go" ] && GO=true

ROOT="$(git rev-parse --show-toplevel)"
ENV_FILE="$ROOT/services/api/.env"
COOLIFY="bash /tmp/coolify.sh"

# --- confirmed inventory (Phase A read-only probe) -------------------------
SERVER_UUID="h7jfzakz4yaed9fnfgv8q4v0"
PROJECT_UUID="u142qntji7qvazr1qpfdpm4l"
DESTINATION_UUID="gchal4l1ep7hnhsnvvqkctr0"
ENVIRONMENT_NAME="production"
APP_NAME="python-coach"
DB_NAME="python-coach-db"
GIT_REPO="https://github.com/AndreyKuleshov/python-coach"
GIT_BRANCH="main"
DOCKERFILE_LOCATION="/services/api/Dockerfile"
PORTS_EXPOSES="8000"
DOMAIN="https://python-coach.duckdns.org"   # owner must confirm (Decision 3)
PG_IMAGE="postgres:17.2-bookworm"

# --- secrets: supplied via env at run time, NEVER hard-coded here ----------
#   JWT_SECRET, OPENAI_API_KEY, SMTP_PASSWORD are read from the caller's env.
: "${JWT_SECRET:=}"
: "${OPENAI_API_KEY:=}"
: "${SMTP_PASSWORD:=}"

call() {
  # call METHOD PATH [BODY] — prints; only executes under --go.
  local method="$1" path="$2" body="${3:-}"
  if ! $GO; then
    echo "[dry-run] $method $path"
    [ -n "$body" ] && echo "           body: $body"
    return 0
  fi
  $COOLIFY "$method" "$path" "$body"
}

require_approval() {
  if ! $GO; then return 0; fi
  cat >&2 <<'EOF'
!! STOP: this step (docker.sock mount / live infra) needs explicit owner approval.
!! Re-run with --go ONLY after the owner has signed off (see COOLIFY_DEPLOY.md).
EOF
}

echo "=== python-coach Coolify deploy ($([ "$GO" = true ] && echo LIVE || echo DRY-RUN)) ==="

# 1. Create Postgres
call POST /api/v1/databases/postgresql "$(cat <<JSON
{"server_uuid":"$SERVER_UUID","project_uuid":"$PROJECT_UUID","environment_name":"$ENVIRONMENT_NAME","name":"$DB_NAME","image":"$PG_IMAGE","postgres_user":"coach","postgres_db":"coach","instant_deploy":true}
JSON
)"
echo ">> then: GET /api/v1/databases/{db_uuid}; rewrite scheme to postgresql+asyncpg:// for DATABASE_URL"

# 2. Create the application from the public repo
call POST /api/v1/applications/public "$(cat <<JSON
{"project_uuid":"$PROJECT_UUID","environment_name":"$ENVIRONMENT_NAME","server_uuid":"$SERVER_UUID","destination_uuid":"$DESTINATION_UUID","name":"$APP_NAME","git_repository":"$GIT_REPO","git_branch":"$GIT_BRANCH","build_pack":"dockerfile","dockerfile_location":"$DOCKERFILE_LOCATION","ports_exposes":"$PORTS_EXPOSES","domains":"$DOMAIN","instant_deploy":false}
JSON
)"
echo ">> capture returned application uuid as APP_UUID for the steps below"

# 3. Set env (template — APP_UUID + resolved DATABASE_URL filled at run time)
echo ">> for each var in COOLIFY_DEPLOY.md env table:"
echo "   POST /api/v1/applications/{APP_UUID}/envs  {\"key\":\"...\",\"value\":\"...\",\"is_preview\":false}"
echo "   (DATABASE_URL, JWT_SECRET, OPENAI_API_KEY, SMTP_PASSWORD entered as secrets here)"

# 4. docker.sock + host docker CLI mounts — APPROVAL GATE
require_approval
echo ">> attach mounts on {APP_UUID}: /var/run/docker.sock and /usr/bin/docker:ro (Decision 1)"

# 5. Build the sandbox image on the host (over SSH)
echo ">> on host: docker build -t python-coach-sandbox:latest <repo>/services/sandbox"

# 6. Deploy
echo ">> GET /api/v1/deploy?uuid={APP_UUID}&force=false"

# 7. Migrate + seed (inside the app container)
echo ">> in app container: cd /app && alembic upgrade head"
echo ">> seed real methodist fixtures (NOT the placeholder) against the same DATABASE_URL"

# 8. Verify
echo ">> curl $DOMAIN/healthz  -> {\"status\":\"ok\"}"

$GO || echo "=== dry-run complete; nothing changed. Re-run with --go for Phase B. ==="
