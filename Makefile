.PHONY: crawl generate fmt build all clean venv

VENV := .venv
PYTHON := $(VENV)/bin/python

venv:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install requests beautifulsoup4 markdownify jinja2

crawl: ## Crawl HTML docs + XML models
	$(PYTHON) crawl_api_docs.py

generate: ## Parse docs, emit Go code
	$(PYTHON) -m generate

fmt: ## Format generated Go
	gofmt -w opnsense/

build: ## Verify Go compiles
	go build ./opnsense/...

all: crawl generate fmt build ## Run full pipeline

clean: ## Remove generated module packages (keeps hand-written core)
	find opnsense -mindepth 1 -type d -exec rm -rf {} + 2>/dev/null || true

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
