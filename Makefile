.PHONY: crawl generate fmt build build-cli all clean venv generate-cli

VENV := .venv
PYTHON := $(VENV)/bin/python

venv:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install requests beautifulsoup4 markdownify jinja2

crawl: ## Crawl HTML docs + XML models
	$(PYTHON) crawl_api_docs.py

generate: ## Parse docs, emit Go SDK + CLI code
	$(PYTHON) -m generate

generate-cli: ## Emit CLI commands only (requires existing docs/)
	$(PYTHON) -m generate

fmt: ## Format generated Go
	gofmt -w opnsense/ internal/cli/gen/

build: ## Verify Go SDK compiles
	go build ./opnsense/...

build-cli: ## Build the opn CLI binary
	go build -o opn ./cmd/opn/

all: crawl generate fmt build build-cli ## Run full pipeline

clean: ## Remove generated module packages (keeps hand-written core)
	find opnsense -mindepth 1 -type d -exec rm -rf {} + 2>/dev/null || true
	find internal/cli/gen -name '*.go' -delete 2>/dev/null || true

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
