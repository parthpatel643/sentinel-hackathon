# Sentinel Platform — developer entry points.
# `make up && make api` is the five-minute quickstart a reviewer should be able
# to run on a clean machine.

COMPOSE := docker compose -f infra/compose/docker-compose.yml

.DEFAULT_GOAL := help
.PHONY: help install up down logs ps api test lint fmt types check clean

help: ## Show available targets
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Install all workspace dependencies
	uv sync --all-packages

up: ## Start the local infrastructure stack
	$(COMPOSE) up -d
	@echo "postgres :15432  valkey :16379  nats :14222  minio :19000 (console :19001)"
	@echo "relay    rtsp :8554  hls :8888  whep :8889  api :9997"

down: ## Stop the stack (volumes are preserved)
	$(COMPOSE) down

logs: ## Tail stack logs
	$(COMPOSE) logs -f

ps: ## Show stack status
	$(COMPOSE) ps

api: ## Run the core API with reload
	uv run uvicorn core_api.app:app --reload --port 18080

test: ## Run the test suite
	uv run pytest

lint: ## Lint
	uv run ruff check .

fmt: ## Format
	uv run ruff format .

types: ## Type-check
	uv run mypy packages services tests

check: lint types test ## Everything CI runs

clean: ## Stop the stack and delete its volumes
	$(COMPOSE) down -v
