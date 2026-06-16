REPO_ROOT := $(shell git rev-parse --show-toplevel)
API_DIR := $(REPO_ROOT)/services/api
-include $(API_DIR)/.env

# Non-standard port to avoid clashing with other local projects (e.g. vite/uvicorn
# defaults on 8000). Override with `make api-run API_PORT=xxxx`.
API_PORT ?= 8077

.PHONY: api-install api-run api-migrate api-makemigration api-seed api-test api-lint api-typecheck api-contracts

api-install:
	uv sync

api-run:
	uv run --directory $(API_DIR) uvicorn python_coach.app:app --reload --host 127.0.0.1 --port $(API_PORT)

api-migrate:
	uv run --directory $(API_DIR) alembic upgrade head

api-makemigration:
	uv run --directory $(API_DIR) alembic revision --autogenerate -m "$(m)"

api-seed:
	uv run --directory $(API_DIR) python -m python_coach.seed $(REPO_ROOT)/fixtures/placeholder_lesson.json

api-test:
	uv run --directory $(API_DIR) pytest

api-lint:
	uv run ruff check $(API_DIR)/src
	uv run ruff format --check $(API_DIR)/src

api-typecheck:
	uv run pyright $(API_DIR)/src

api-contracts:
	uv run lint-imports
