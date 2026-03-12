#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

RUN_E2E=false
RUN_BROWSER=false

for arg in "$@"; do
    case "$arg" in
        --e2e) RUN_E2E=true ;;
        --browser) RUN_BROWSER=true ;;
        --all) RUN_E2E=true; RUN_BROWSER=true ;;
        -h|--help)
            echo "Usage: $0 [--e2e] [--browser] [--all]"
            exit 0
            ;;
    esac
done

PASS=0
FAIL=0
PYTHON="${PYTHON:-python3}"

step() {
    echo ""
    echo -e "${CYAN}━━━ $1 ━━━${NC}"
}

ok() {
    echo -e "  ${GREEN}✓${NC} $1"
    PASS=$((PASS + 1))
}

fail() {
    echo -e "  ${RED}✗${NC} $1"
    FAIL=$((FAIL + 1))
}

warn() {
    echo -e "  ${YELLOW}⚠${NC} $1"
}

step "Step 1: Python environment"
if $PYTHON -c "import sys; assert sys.version_info >= (3, 11)" 2>/dev/null; then
    ok "Python >= 3.11"
else
    fail "Python >= 3.11 required"
fi

step "Step 2: Install dependencies"
if $PYTHON -m pip install -e ".[dev]" >/dev/null 2>&1; then
    ok "Installed package with dev dependencies"
else
    fail "Failed to install dev dependencies"
fi

if $RUN_BROWSER; then
    step "Step 2b: Install Playwright"
    if $PYTHON -m pip install playwright >/dev/null 2>&1 && $PYTHON -m playwright install chromium >/dev/null 2>&1; then
        ok "Installed Playwright and Chromium"
    else
        fail "Failed to install Playwright or Chromium"
        RUN_BROWSER=false
    fi
fi

step "Step 3: Compile check"
if $PYTHON -m compileall src tests scripts >/dev/null 2>&1; then
    ok "Compilation check passed"
else
    fail "Compilation check failed"
fi

step "Step 4: CLI smoke test"
export PYTHONPATH=src
if $PYTHON -m webinfo2md --help >/tmp/webinfo2md_help.txt 2>&1; then
    ok "CLI help works"
else
    fail "CLI help failed"
fi

for flag in "--concurrency" "--force-playwright" "--cookie-file" "--dry-run"; do
    if grep -q -- "$flag" /tmp/webinfo2md_help.txt; then
        ok "Found CLI flag $flag"
    else
        fail "Missing CLI flag $flag"
    fi
done

step "Step 5: Offline tests"
for test_file in \
    tests/test_chunker.py \
    tests/test_writer.py \
    tests/test_pipeline.py \
    tests/test_concurrent.py \
    tests/test_playwright.py \
    tests/test_factory.py \
    tests/test_e2e.py \
    tests/test_cli.py
do
    if [ -f "$test_file" ]; then
        if $PYTHON -m pytest "$test_file" -q --tb=short >/dev/null 2>&1; then
            ok "$test_file passed"
        else
            fail "$test_file failed"
        fi
    else
        warn "$test_file not found"
    fi
done

step "Step 6: Real dry-run"
if $PYTHON -m webinfo2md --url "https://httpbin.org/html" --dry-run --verbose > /tmp/webinfo2md_dryrun.log 2>&1; then
    if grep -Eq "Dry run 完成|\[dry-run\]" /tmp/webinfo2md_dryrun.log; then
        ok "Dry-run completed"
    else
        warn "Dry-run command returned successfully but output was unexpected"
    fi
else
    warn "Dry-run failed, likely due to network restrictions"
fi

if $RUN_E2E; then
    step "Step 7: Real E2E"
    if [ -z "${LLM_API_KEY:-}" ]; then
        fail "LLM_API_KEY not set"
    else
        if $PYTHON -m pytest tests/test_e2e_real.py -v -s --tb=long; then
            ok "Real E2E tests passed"
        else
            fail "Real E2E tests failed"
        fi
    fi
else
    step "Step 7: Real E2E"
    warn "Skipped. Use --e2e or --all"
fi

if $RUN_BROWSER; then
    step "Step 8: Real Playwright E2E"
    if $PYTHON -m pytest tests/test_e2e_real.py::TestPlaywrightReal -v -s --tb=long; then
        ok "Playwright real tests passed"
    else
        fail "Playwright real tests failed"
    fi
else
    step "Step 8: Real Playwright E2E"
    warn "Skipped. Use --browser or --all"
fi

echo ""
echo -e "${CYAN}━━━ Summary ━━━${NC}"
echo -e "  ${GREEN}Passed: $PASS${NC}"
echo -e "  ${RED}Failed: $FAIL${NC}"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
