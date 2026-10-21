# Workspace commands always take an explicit PROFILE; nothing here uses the default CLI profile.
SHELL := /bin/bash
.DEFAULT_GOAL := help

export PYTHONPATH := .
export MLFLOW_DISABLE_AGENT_HINT := 1

UV_RUN := uv run --frozen --all-groups
NPM := npm --prefix frontend
DOCS_NPM := npm --prefix docs
BUNDLE = databricks bundle

.PHONY: help init setup dev agent db-stop lint fmt test contract contract-live build api-types \
	migration lock check-lock docs docs-build deploy ci-deploy destroy eval eval-dataset

help: ## Show the available targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-z-]+:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

init: ## Fill in placeholders: make init NAME=... ADMINS=... DEV_HOST=... LLM_ENDPOINT=... [TITLE= TEST_HOST= PROD_HOST=]
	python3 scripts/init_project.py \
		$(if $(NAME),--name "$(NAME)") $(if $(TITLE),--title "$(TITLE)") \
		$(if $(ADMINS),--admins "$(ADMINS)") $(if $(LLM_ENDPOINT),--llm-endpoint "$(LLM_ENDPOINT)") \
		$(if $(DEV_HOST),--dev-host "$(DEV_HOST)") $(if $(TEST_HOST),--test-host "$(TEST_HOST)") \
		$(if $(PROD_HOST),--prod-host "$(PROD_HOST)")

setup: ## Install Python and Node dependencies from the lockfiles
	uv sync --frozen --all-groups
	$(NPM) ci

# ---- local development -----------------------------------------------------------------------

dev: ## API (auto-reload) + Vite on a local Postgres, fake agent in-process; optional PROFILE= LLM_ENDPOINT=
	scripts/dev.sh

agent: ## Run the agent on its own on :9000 (fake unless LLM_ENDPOINT is set), for split-mode work
	$(if $(PROFILE),DATABRICKS_CONFIG_PROFILE=$(PROFILE)) $(UV_RUN) uvicorn \
		backend.agents.server:create_agent_app --factory --reload \
		--reload-dir backend/agents --reload-dir backend/contracts --reload-dir contracts --port 9000

db-stop: ## Stop the local Postgres started by `make dev`
	$(UV_RUN) python scripts/localdb.py stop

# ---- checks ------------------------------------------------------------------------------------

lint: ## Ruff, mypy, ESLint, Prettier and the TypeScript compiler
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .
	$(UV_RUN) mypy
	$(NPM) run lint
	$(NPM) run typecheck

fmt: ## Format and auto-fix Python and frontend code
	$(UV_RUN) ruff check --fix .
	$(UV_RUN) ruff format .
	$(NPM) run fmt

test: ## Python tests against real Postgres (pgserver) and frontend tests
	$(UV_RUN) pytest
	$(NPM) test

contract: ## The agent contract tests only: golden record, catalog, runtime, boundary
	$(UV_RUN) pytest tests/contracts tests/agents

contract-live: guard-AGENT_API_BASE ## Check a running agent: make contract-live AGENT_API_BASE=http://localhost:9000 [PROFILE=]
	$(if $(PROFILE),DATABRICKS_CONFIG_PROFILE=$(PROFILE)) AGENT_API_BASE=$(AGENT_API_BASE) \
		$(UV_RUN) pytest tests/contracts/test_live_agent.py -v

eval: ## Evaluate the agent: make eval DEV=1 (offline, fake agent) or make eval PROFILE=... LLM_ENDPOINT=...
ifeq ($(DEV),1)
	$(UV_RUN) python -m evals.run --dev
else
	@test -n "$(PROFILE)" -a -n "$(LLM_ENDPOINT)" || { echo "Set PROFILE and LLM_ENDPOINT, or DEV=1 to run offline"; exit 1; }
	DATABRICKS_CONFIG_PROFILE=$(PROFILE) LLM_ENDPOINT=$(LLM_ENDPOINT) $(UV_RUN) python -m evals.run
endif

eval-dataset: guard-PROFILE guard-EXPERIMENT ## Rows from users' feedback: make eval-dataset PROFILE=... EXPERIMENT=<id or path> [DAYS=30] [UC_TABLE=]
	DATABRICKS_CONFIG_PROFILE=$(PROFILE) $(UV_RUN) python -m evals.from_feedback \
		--experiment "$(EXPERIMENT)" --days $(or $(DAYS),30) $(if $(UC_TABLE),--uc-table "$(UC_TABLE)")

# ---- build -------------------------------------------------------------------------------------

build: ## Build the frontend into backend/static
	$(NPM) run build

api-types: ## Regenerate frontend/src/api/schema.d.ts from the FastAPI schema
	$(UV_RUN) python scripts/export_openapi.py .build/openapi.json
	$(NPM) run api-types

migration: ## Generate a migration from model changes: make migration MSG="add widgets"
	@test -n "$(MSG)" || { echo 'Usage: make migration MSG="describe the change"'; exit 1; }
	DATABASE_URL="$$($(UV_RUN) python scripts/localdb.py url)" bash -c '\
		$(UV_RUN) alembic -c alembic.ini upgrade head && \
		$(UV_RUN) alembic -c alembic.ini revision --autogenerate -m "$(MSG)"'

lock: ## Update the lockfiles (public registry URLs only)
	scripts/relock.sh
	$(NPM) install --package-lock-only --no-audit --no-fund
	$(DOCS_NPM) install --package-lock-only --no-audit --no-fund
	scripts/check_lockfiles.sh

check-lock: ## Fail if a lockfile points at a private mirror
	scripts/check_lockfiles.sh

docs: ## Serve the documentation site with live reload on :3000
	$(DOCS_NPM) ci
	$(DOCS_NPM) start

docs-build: ## Build the documentation site; fails on broken links
	$(DOCS_NPM) ci
	$(DOCS_NPM) run build

# ---- deploy ------------------------------------------------------------------------------------

deploy: guard-TARGET guard-PROFILE ## Build and deploy: make deploy TARGET=dev PROFILE=<cli-profile>
	python3 scripts/init_project.py --check
	$(MAKE) build
	$(BUNDLE) validate --strict -t $(TARGET) --profile $(PROFILE)
	$(BUNDLE) deploy -t $(TARGET) --profile $(PROFILE)
	$(BUNDLE) run app -t $(TARGET) --profile $(PROFILE)

ci-deploy: guard-TARGET ## Deploy from a CI pipeline, authenticated through environment variables
	@test -n "$$CI" || { echo "ci-deploy is for pipelines. Locally: make deploy TARGET=... PROFILE=..."; exit 1; }
	@test -z "$$DATABRICKS_CONFIG_PROFILE" || { echo "Unset DATABRICKS_CONFIG_PROFILE in CI."; exit 1; }
	python3 scripts/init_project.py --check
	$(MAKE) build
	$(BUNDLE) validate --strict -t $(TARGET)
	$(BUNDLE) deploy -t $(TARGET) --auto-approve
	$(BUNDLE) run app -t $(TARGET)

destroy: guard-TARGET guard-PROFILE ## Delete a target's app, database and experiment (asks to confirm)
	$(BUNDLE) destroy -t $(TARGET) --profile $(PROFILE)

guard-%:
	@test -n "$($*)" || { echo "Set $*, e.g. make $(firstword $(MAKECMDGOALS)) $*=<value>"; exit 1; }
