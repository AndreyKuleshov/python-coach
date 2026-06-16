REPO_ROOT := $(shell git rev-parse --show-toplevel)
SANDBOX_DIR := $(REPO_ROOT)/services/sandbox
SANDBOX_IMAGE ?= python-coach-sandbox:latest

-include $(SANDBOX_DIR)/.env

.PHONY: sandbox-build sandbox-smoke

# Build the sandbox image via the unified compose stack so all Docker definitions
# live in one place. The `--profile build` flag selects the sandbox service without
# starting it as a daemon. The resulting tag matches SANDBOX_IMAGE (and the API default).
sandbox-build:
	docker compose -f $(REPO_ROOT)/deploy/docker-compose.yml --profile build build sandbox

# Smoke test: grade a trivial passing solution outside the API to prove isolation.
sandbox-smoke:
	$(SANDBOX_DIR)/smoke.sh $(SANDBOX_IMAGE)
