.PHONY: help install install-dev install-browser lint typecheck compile-check test test-unit test-all test-concurrent test-playwright test-factory dry-run e2e-real e2e-manual clean

PYTHON ?= python3
PYTHONPATH := src
export PYTHONPATH

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install runtime dependencies
	$(PYTHON) -m pip install -e "."

install-dev: install ## Install dev and test dependencies
	$(PYTHON) -m pip install -e ".[dev]"

install-browser: ## Install Playwright and Chromium
	$(PYTHON) -m pip install playwright
	$(PYTHON) -m playwright install chromium

lint: ## Run ruff
	$(PYTHON) -m ruff check src tests

typecheck: ## Run pyright
	$(PYTHON) -m pyright src

compile-check: ## Verify Python files compile
	$(PYTHON) -m compileall src tests scripts

test: test-unit ## Run all offline tests

test-unit: ## Run tests that do not require network or API keys
	$(PYTHON) -m pytest tests --ignore=tests/test_e2e_real.py -q --tb=short

test-all: ## Run the full test suite
	$(PYTHON) -m pytest tests -q --tb=short

test-concurrent: ## Run concurrent extraction tests
	$(PYTHON) -m pytest tests/test_concurrent.py -q

test-playwright: ## Run Playwright mock tests
	$(PYTHON) -m pytest tests/test_playwright.py -q

test-factory: ## Run crawler factory tests
	$(PYTHON) -m pytest tests/test_factory.py -q

dry-run: ## Dry-run against a real URL without LLM calls
	$(PYTHON) -m webinfo2md \
		--url "https://httpbin.org/html" \
		--dry-run \
		--verbose

e2e-real: ## Run real end-to-end pytest cases
	@test -n "$(LLM_API_KEY)" || (echo "ERROR: set LLM_API_KEY" && exit 1)
	$(PYTHON) -m pytest tests/test_e2e_real.py -v -s --tb=long

e2e-manual: ## Run one real CLI end-to-end example
	@test -n "$(LLM_API_KEY)" || (echo "ERROR: set LLM_API_KEY" && exit 1)
	$(PYTHON) -m webinfo2md \
		--url "https://httpbin.org/html" \
		--api-key "$(LLM_API_KEY)" \
		--provider "$(or $(LLM_PROVIDER),openai)" \
		$(if $(LLM_MODEL),--model "$(LLM_MODEL)",) \
		--prompt "提取页面中的关键信息，整理为结构化笔记" \
		--output /tmp/webinfo2md_e2e_test.md \
		--verbose
	@echo "Output: /tmp/webinfo2md_e2e_test.md"

clean: ## Remove Python build artifacts
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
