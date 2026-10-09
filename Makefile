# Developer entrypoints. Every target is runnable from the repository root.
API := apps/api
# Most tools need apps/api as their working directory (pytest, alembic, ruff, mypy).
UV  := uv run --directory $(API)
# pre-commit must keep the repository root as its working directory, otherwise the
# file filters in .pre-commit-config.yaml never match.
UVR := uv run --project $(API)

.DEFAULT_GOAL := help

.PHONY: help install run test test-unit lint format typecheck check migrate migration \
        up down logs hooks

help: ## Show available targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "} {printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Install Python dependencies and git hooks
	uv sync --directory $(API) --all-groups
	$(UVR) pre-commit install

run: ## Run the API with hot reload (requires PostgreSQL)
	$(UV) uvicorn compass_api.main:app --reload

test: ## Run the full test suite with coverage
	$(UV) pytest --cov

test-unit: ## Run only the tests that need no infrastructure
	$(UV) pytest -m "not integration"

lint: ## Lint
	$(UV) ruff check .

format: ## Format
	$(UV) ruff format .

typecheck: ## Type-check
	$(UV) mypy

check: lint typecheck test ## Everything CI runs

migrate: ## Apply migrations
	$(UV) alembic upgrade head

migration: ## Autogenerate a migration: make migration m="add goals table"
	$(UV) alembic revision --autogenerate -m "$(m)"

up: ## Start the local stack (API + PostgreSQL + Redis)
	docker compose up --build

down: ## Stop the local stack and remove volumes
	docker compose down -v

logs: ## Tail the API logs
	docker compose logs -f api

hooks: ## Run pre-commit against all files
	$(UVR) pre-commit run --all-files
