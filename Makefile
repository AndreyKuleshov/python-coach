# Root dispatcher — include only. Real targets live in domain Makefiles.
.DEFAULT_GOAL := help

include services/api/Makefile
include services/sandbox/Makefile
include deploy/Makefile

.PHONY: help
help:
	@echo "Domains: api-* (services/api), sandbox-* (services/sandbox), deploy-* (deploy)"
	@echo "Quick start: make deploy-up && make api-migrate && make sandbox-build && make api-seed && make api-run"
