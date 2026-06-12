REPO_ROOT := $(shell git rev-parse --show-toplevel)
DEPLOY_DIR := $(REPO_ROOT)/deploy
-include $(DEPLOY_DIR)/.env

.PHONY: deploy-up deploy-down deploy-logs

deploy-up:
	docker compose --env-file $(DEPLOY_DIR)/.env -f $(DEPLOY_DIR)/docker-compose.yml up -d

deploy-down:
	docker compose -f $(DEPLOY_DIR)/docker-compose.yml down

deploy-logs:
	docker compose -f $(DEPLOY_DIR)/docker-compose.yml logs -f db
