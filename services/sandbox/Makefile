REPO_ROOT := $(shell git rev-parse --show-toplevel)
SANDBOX_DIR := $(REPO_ROOT)/services/sandbox
SANDBOX_IMAGE ?= python-coach-sandbox:latest

.PHONY: sandbox-build sandbox-smoke

sandbox-build:
	docker build -t $(SANDBOX_IMAGE) $(SANDBOX_DIR)

# Smoke test: grade a trivial passing solution outside the API to prove isolation.
sandbox-smoke:
	$(SANDBOX_DIR)/smoke.sh $(SANDBOX_IMAGE)
