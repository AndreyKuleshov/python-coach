# Root dispatcher — include only. Real targets live in domain Makefiles.
.DEFAULT_GOAL := help

include services/api/Makefile
include services/sandbox/Makefile
include deploy/Makefile
include dev/Makefile

.PHONY: help dev
help:
	@echo "Domains: api-* (services/api), sandbox-* (services/sandbox), deploy-* (deploy), dev-* (dev)"
	@echo "One-command start: make dev      (alias for dev-up)"
	@echo "One-command stop:  make dev-down (stop and remove compose stack)"
