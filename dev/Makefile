# Cross-domain orchestration: start / stop the full local environment.
# Real per-domain work stays in services/api/Makefile, services/sandbox/Makefile,
# and deploy/Makefile.  This Makefile sequences them.
REPO_ROOT := $(shell git rev-parse --show-toplevel)

.PHONY: dev-up dev-down dev

# dev-up — bring up the full local environment in the correct order:
#   1. Postgres (deploy-up --wait blocks until the healthcheck passes, so no race)
#   2. Alembic migrations
#   3. Sandbox Docker image
#   4. Seed the placeholder lesson (upsert-by-slug — safe to repeat)
#   5. uvicorn in the foreground (blocking — this is the "it's running" step)
dev-up:
	@echo "==> [1/5] Starting Postgres and waiting for it to be healthy..."
	$(MAKE) -C $(REPO_ROOT) deploy-up
	@echo "==> [2/5] Running Alembic migrations..."
	$(MAKE) -C $(REPO_ROOT) api-migrate
	@echo "==> [3/5] Building sandbox Docker image..."
	$(MAKE) -C $(REPO_ROOT) sandbox-build
	@echo "==> [4/5] Seeding placeholder lesson..."
	$(MAKE) -C $(REPO_ROOT) api-seed
	@echo "==> [5/5] Starting API (uvicorn on :8000)..."
	$(MAKE) -C $(REPO_ROOT) api-run

# dev-down — tear down the compose stack (data volume is preserved).
dev-down:
	$(MAKE) -C $(REPO_ROOT) deploy-down

# Short alias mirroring the prefix — one canonical "run" verb (makefile.md exception).
dev: dev-up
