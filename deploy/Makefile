REPO_ROOT := $(shell git rev-parse --show-toplevel)
DEPLOY_DIR := $(REPO_ROOT)/deploy
-include $(DEPLOY_DIR)/.env

# Production API image tag (override: make deploy-image-build IMAGE_TAG=python-coach-api:v1).
IMAGE_TAG ?= python-coach-api:latest

.PHONY: deploy-up deploy-down deploy-logs deploy-image-build deploy-sandbox-build deploy-coolify-plan deploy-coolify-go

deploy-up:
	docker compose --env-file $(DEPLOY_DIR)/.env -f $(DEPLOY_DIR)/docker-compose.yml up -d --wait

deploy-down:
	docker compose -f $(DEPLOY_DIR)/docker-compose.yml down

deploy-logs:
	docker compose -f $(DEPLOY_DIR)/docker-compose.yml logs -f db

# Build the production API image. Context = repo root so the root .dockerignore
# prunes the harness/sources/docs/tests out of the build context.
deploy-image-build:
	docker build -f $(REPO_ROOT)/services/api/Dockerfile -t $(IMAGE_TAG) $(REPO_ROOT)

# Build the per-submission sandbox image (must exist on whatever host runs grading).
deploy-sandbox-build:
	docker build -t python-coach-sandbox:latest $(REPO_ROOT)/services/sandbox

# Coolify deploy plan — dry-run (prints the ordered calls, changes nothing).
deploy-coolify-plan:
	bash $(DEPLOY_DIR)/coolify-deploy.sh

# Coolify deploy — Phase B (LIVE). Only after owner sign-off (docker.sock + infra).
deploy-coolify-go:
	bash $(DEPLOY_DIR)/coolify-deploy.sh --go
