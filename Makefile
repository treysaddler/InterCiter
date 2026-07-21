# InterCiter — LinkML schema tasks
# Usage: make <target>   (requires `uv`)

SCHEMA := schema/interciter.yaml
GEN    := uv tool run --from linkml
OUT    := schema/generated

.PHONY: help lint pydantic sqlddl jsonschema all clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

lint: ## Validate the schema
	$(GEN) linkml-lint $(SCHEMA)

pydantic: $(OUT) ## Generate Pydantic models
	$(GEN) gen-pydantic $(SCHEMA) > $(OUT)/models.py

sqlddl: $(OUT) ## Generate SQL DDL
	$(GEN) gen-sqlddl $(SCHEMA) > $(OUT)/schema.sql

jsonschema: $(OUT) ## Generate JSON Schema
	$(GEN) gen-json-schema $(SCHEMA) > $(OUT)/schema.json

all: lint pydantic sqlddl jsonschema ## Validate and generate all artifacts

$(OUT):
	mkdir -p $(OUT)

clean: ## Remove generated artifacts
	rm -rf $(OUT)
