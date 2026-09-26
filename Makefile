# Sentinel Platform — developer entry points.
# `make up && make api` is the five-minute quickstart a reviewer should be able
# to run on a clean machine.

SHELL := /bin/bash
COMPOSE := docker compose -f infra/compose/docker-compose.yml

.DEFAULT_GOAL := help
.PHONY: help install up down logs ps api web worker deck seed test lint fmt types check audit secrets-scan sbom clean

help: ## Show available targets
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Install all workspace dependencies
	uv sync --all-packages
	cd apps/web && npm install

up: ## Start the local infrastructure stack
	$(COMPOSE) up -d
	@echo "postgres :15432  valkey :16379  nats :14222"
	@echo "relay    rtsp :8554  hls :8888  whep :8889  api :9997"
	@echo "(object store is opt-in: add --profile object-store)"

down: ## Stop the stack (volumes are preserved)
	$(COMPOSE) down

logs: ## Tail stack logs
	$(COMPOSE) logs -f

ps: ## Show stack status
	$(COMPOSE) ps

# 18000, not 18080: apps/web/.env and sentinel_core.config's `core_api_url`
# both default here, so binding anything else gives a stack whose own parts
# cannot reach each other.
api: ## Run the core API with reload
	uv run --package core_api uvicorn core_api.app:app --reload --port 18000

web: ## Run the operator console (Vite dev server)
	cd apps/web && npm run dev

worker: ## Run an edge worker (SOURCE=gov CAMERAS=cam06,cam30 STRIDE=3 for the real grid)
	uv run --package edge-agent python -m edge_agent.worker \
	  --source $(or $(SOURCE),synthetic) \
	  $(if $(CAMERAS),--cameras $(CAMERAS),) \
	  $(if $(STRIDE),--frame-stride $(STRIDE),)

deck: ## Build the submission deck (docs/Sentinel-Platform-Deck.pptx)
	NODE_PATH=$$(npm root -g) node scripts/build_deck.mjs

hld: ## Build the HLD PDF from docs/ (docs/Sentinel-Platform-HLD.pdf)
	cd apps/web && npm run docs:pdf

workflow-diagram: ## Build the Workflow/Integration Diagram PDF (docs/Sentinel-Platform-Workflow-Integration-Diagram.pdf)
	cd apps/web && npm run docs:diagram

doctor: ## Diagnose why the camera feed is not coming (--gov for the real grid)
	uv run python scripts/diagnose.py $(if $(GOV),--gov,)

seed: ## Create the default operator login
	uv run --package core_api python scripts/seed_admin_user.py

test: ## Run the test suite
	uv run pytest

lint: ## Lint
	uv run ruff check .

fmt: ## Format
	uv run ruff format .

types: ## Type-check
	uv run mypy packages services tests

check: lint types test ## Everything CI runs

audit: ## M12: dependency vulnerability scan (Python + frontend)
	uvx pip-audit --requirement <(uv export --no-hashes --all-packages 2>/dev/null)
	cd apps/web && npm audit

secrets-scan: ## M12: scan source for accidentally-committed secrets
	uvx --from detect-secrets detect-secrets scan \
		--exclude-files '(node_modules|\.venv|dist|__pycache__|package-lock\.json|models/weights|data/|\.ruff_cache|\.mypy_cache|\.pytest_cache)/' \
		packages services apps scripts docs infra Makefile pyproject.toml

sbom: ## M12: generate CycloneDX SBOMs (not committed — regenerate per release)
	mkdir -p sbom
	uv export --no-hashes --all-packages > sbom/requirements-frozen.txt
	uvx --from cyclonedx-bom cyclonedx-py requirements sbom/requirements-frozen.txt \
		--output-format json --output-file sbom/python.cdx.json
	cd apps/web && npx --yes @cyclonedx/cyclonedx-npm --output-file ../../sbom/frontend.cdx.json
	@echo "SBOMs written to sbom/ (gitignored — regenerate fresh per release, don't ship a stale one)"

clean: ## Stop the stack and delete its volumes
	$(COMPOSE) down -v
