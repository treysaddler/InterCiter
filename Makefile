# InterCiter — project tasks
# Usage: make <target>   (requires `uv`; frontend targets require Node/npm;
#                          docs targets require `quarto`)

SCHEMA   := schema/interciter.yaml
GEN      := uv tool run --from linkml
OUT      := schema/generated
BACKEND  := backend
FRONTEND := frontend
DOCS     := docs

.PHONY: help \
	lint pydantic sqlddl jsonschema all clean \
	be-install be-test be-seed be-serve \
	fe-install fe-dev fe-build fe-typecheck fe-test \
	docs-render docs-preview \
	test

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# --- Schema (LinkML) --------------------------------------------------------

lint: ## Validate the schema
	$(GEN) linkml-lint $(SCHEMA)

pydantic: $(OUT) ## Generate Pydantic models
	$(GEN) gen-pydantic $(SCHEMA) > $(OUT)/models.py

sqlddl: $(OUT) ## Generate SQL DDL
	$(GEN) gen-sqlddl $(SCHEMA) > $(OUT)/schema.sql

jsonschema: $(OUT) ## Generate JSON Schema
	$(GEN) gen-json-schema $(SCHEMA) > $(OUT)/schema.json

all: lint pydantic sqlddl jsonschema ## Validate and generate all schema artifacts

$(OUT):
	mkdir -p $(OUT)

clean: ## Remove generated schema artifacts
	rm -rf $(OUT)

# --- Backend (FastAPI API) --------------------------------------------------

be-install: ## Create the backend venv and install (editable, with dev extras)
	cd $(BACKEND) && uv venv --python 3.13 && uv pip install -e '.[dev]'

be-test: ## Run the backend test suite
	cd $(BACKEND) && uv run pytest

be-seed: ## Seed the bundled sample corpus into the dev database
	cd $(BACKEND) && uv run interciter seed

be-serve: ## Run the API with reload (http dev: cookies non-Secure so UI login works)
	cd $(BACKEND) && INTERCITER_SESSION_COOKIE_SECURE=false uv run interciter serve --reload

# --- Frontend (React + Vite + USWDS) ----------------------------------------

fe-install: ## Install frontend dependencies
	cd $(FRONTEND) && npm install

fe-dev: ## Run the frontend dev server (proxies /v1 + /health to :8000)
	cd $(FRONTEND) && npm run dev

fe-build: ## Typecheck and build the frontend to dist/
	cd $(FRONTEND) && npm run build

fe-typecheck: ## Typecheck the frontend without emitting
	cd $(FRONTEND) && npm run typecheck

fe-test: ## Run the frontend test suite (Vitest)
	cd $(FRONTEND) && npm test

# --- Docs (Quarto site) -----------------------------------------------------

docs-render: ## Render the Quarto site to docs/_site
	cd $(DOCS) && quarto render

docs-preview: ## Live-reloading preview of the Quarto site
	cd $(DOCS) && quarto preview

# --- Aggregate --------------------------------------------------------------

test: be-test fe-test ## Run backend + frontend test suites
