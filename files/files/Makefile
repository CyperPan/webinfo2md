.PHONY: help install install-dev lint typecheck test test-unit test-e2e e2e-real dry-run clean

PYTHON ?= python3
PYTHONPATH := src
export PYTHONPATH

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Setup ──────────────────────────────────────────────────────────

install: ## Install runtime dependencies
	$(PYTHON) -m pip install -e "." --quiet

install-dev: install ## Install dev + test dependencies
	$(PYTHON) -m pip install -e ".[dev]" --quiet
	@echo "✓ Dev dependencies installed"

install-browser: ## Install Playwright + Chromium (for --force-playwright)
	$(PYTHON) -m pip install playwright --quiet
	$(PYTHON) -m playwright install chromium
	@echo "✓ Playwright + Chromium installed"

# ── Quality ────────────────────────────────────────────────────────

lint: ## Run ruff linter
	$(PYTHON) -m ruff check src/ tests/

typecheck: ## Run pyright type checker
	$(PYTHON) -m pyright src/

compile-check: ## Verify all .py files compile
	$(PYTHON) -m compileall src tests -q
	@echo "✓ All files compile"

# ── Tests ──────────────────────────────────────────────────────────

test: test-unit ## Run all offline tests (default)

test-unit: ## Run unit + mock tests (no network, no API key needed)
	$(PYTHON) -m pytest tests/ \
		--ignore=tests/test_e2e_real.py \
		-v --tb=short -q

test-all: ## Run ALL tests including real E2E (needs LLM_API_KEY)
	$(PYTHON) -m pytest tests/ -v --tb=short

test-concurrent: ## Run only concurrent extraction tests
	$(PYTHON) -m pytest tests/test_concurrent.py -v

test-playwright: ## Run only Playwright mock tests
	$(PYTHON) -m pytest tests/test_playwright.py -v

test-factory: ## Run only crawler factory tests
	$(PYTHON) -m pytest tests/test_factory.py -v

# ── Real E2E ───────────────────────────────────────────────────────

dry-run: ## Dry-run against a real URL (no LLM call)
	$(PYTHON) -m webinfo2md \
		--url "https://httpbin.org/html" \
		--dry-run --verbose

e2e-real: ## Full E2E with real LLM (needs LLM_API_KEY + provider)
	@test -n "$(LLM_API_KEY)" || (echo "ERROR: set LLM_API_KEY env var" && exit 1)
	$(PYTHON) -m pytest tests/test_e2e_real.py -v -s --tb=long

e2e-manual: ## Manual E2E: crawl a real page, call LLM, produce .md
	@test -n "$(LLM_API_KEY)" || (echo "ERROR: set LLM_API_KEY env var" && exit 1)
	$(PYTHON) -m webinfo2md \
		--url "https://httpbin.org/html" \
		--api-key "$(LLM_API_KEY)" \
		--provider "$(or $(LLM_PROVIDER),openai)" \
		--prompt "提取页面中的关键信息，整理为结构化笔记" \
		--output /tmp/webinfo2md_e2e_test.md \
		--verbose
	@echo ""
	@echo "✓ Output saved to /tmp/webinfo2md_e2e_test.md"
	@head -30 /tmp/webinfo2md_e2e_test.md

# ── Cleanup ────────────────────────────────────────────────────────

clean: ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Cleaned"
