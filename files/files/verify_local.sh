#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# webinfo2md — 本地完整验证脚本
#
# 用法：
#   ./scripts/verify_local.sh              # 跑所有离线测试
#   ./scripts/verify_local.sh --e2e        # 加上真实 E2E（需要 API key）
#   ./scripts/verify_local.sh --browser    # 加上 Playwright 测试
#   ./scripts/verify_local.sh --all        # 全部
#
# 环境变量：
#   LLM_API_KEY     — 真实 LLM API key（E2E 必需）
#   LLM_PROVIDER    — openai / anthropic / deepseek（默认 openai）
#   LLM_MODEL       — 具体模型名（可选，用 provider 默认）
# ============================================================

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
    case $arg in
        --e2e)      RUN_E2E=true ;;
        --browser)  RUN_BROWSER=true ;;
        --all)      RUN_E2E=true; RUN_BROWSER=true ;;
        -h|--help)
            echo "Usage: $0 [--e2e] [--browser] [--all]"
            echo "  --e2e      Run real LLM E2E tests (needs LLM_API_KEY)"
            echo "  --browser  Install Playwright and run browser tests"
            echo "  --all      Run everything"
            exit 0
            ;;
    esac
done

PASS=0
FAIL=0

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

# ── Step 1: Environment ───────────────────────────────────────────

step "Step 1: Checking Python environment"

PYTHON="${PYTHON:-python3}"
PY_VERSION=$($PYTHON --version 2>&1)
echo "  Python: $PY_VERSION"

if $PYTHON -c "import sys; assert sys.version_info >= (3, 10)" 2>/dev/null; then
    ok "Python >= 3.10"
else
    fail "Python >= 3.10 required"
fi

# ── Step 2: Install dependencies ──────────────────────────────────

step "Step 2: Installing dependencies"

# Install the package in dev mode
if $PYTHON -m pip install -e ".[dev]" --quiet 2>/dev/null; then
    ok "Package + dev dependencies installed"
else
    warn "pip install failed, trying individual packages..."
    $PYTHON -m pip install httpx beautifulsoup4 pyyaml markdownify click rich \
        pytest pytest-asyncio --quiet 2>/dev/null || true
    # Check critical deps
    for pkg in httpx bs4 yaml click pytest; do
        if $PYTHON -c "import $pkg" 2>/dev/null; then
            ok "$pkg available"
        else
            fail "$pkg missing"
        fi
    done
fi

if $RUN_BROWSER; then
    step "Step 2b: Installing Playwright"
    if $PYTHON -m pip install playwright --quiet 2>/dev/null; then
        $PYTHON -m playwright install chromium 2>/dev/null
        ok "Playwright + Chromium installed"
    else
        fail "Playwright install failed"
        RUN_BROWSER=false
    fi
fi

# ── Step 3: Compile check ─────────────────────────────────────────

step "Step 3: Compile check"

if $PYTHON -m compileall src tests -q 2>/dev/null; then
    ok "All .py files compile"
else
    fail "Compilation errors found"
fi

# ── Step 4: CLI check ─────────────────────────────────────────────

step "Step 4: CLI smoke test"

export PYTHONPATH=src

if $PYTHON -m webinfo2md --help > /dev/null 2>&1; then
    ok "webinfo2md --help works"
else
    fail "webinfo2md --help failed"
fi

# Check that new P2 flags are present
HELP_OUTPUT=$($PYTHON -m webinfo2md --help 2>&1)
for flag in "--concurrency" "--force-playwright" "--cookie-file" "--dry-run"; do
    if echo "$HELP_OUTPUT" | grep -q -- "$flag"; then
        ok "CLI flag $flag present"
    else
        fail "CLI flag $flag missing"
    fi
done

# ── Step 5: Unit tests ────────────────────────────────────────────

step "Step 5: Running unit & mock tests"

PYTEST_ARGS="-v --tb=short -q"

# Run each test file individually for better error reporting
for test_file in tests/test_chunker.py tests/test_writer.py tests/test_pipeline.py \
                 tests/test_concurrent.py tests/test_playwright.py tests/test_factory.py \
                 tests/test_e2e.py tests/test_cli.py; do
    if [ -f "$test_file" ]; then
        if $PYTHON -m pytest "$test_file" $PYTEST_ARGS 2>/dev/null; then
            ok "$test_file passed"
        else
            fail "$test_file FAILED"
        fi
    else
        warn "$test_file not found (skipped)"
    fi
done

# ── Step 6: Dry-run against httpbin ───────────────────────────────

step "Step 6: Dry-run against real URL"

if $PYTHON -m webinfo2md \
    --url "https://httpbin.org/html" \
    --dry-run --verbose 2>&1 | tee /tmp/webinfo2md_dryrun.log | tail -5; then
    if grep -q "Dry-run complete" /tmp/webinfo2md_dryrun.log 2>/dev/null; then
        ok "Dry-run succeeded"
    else
        # might have network issues
        warn "Dry-run ran but may not have completed fully"
    fi
else
    fail "Dry-run failed"
fi

# ── Step 7: Real E2E (optional) ──────────────────────────────────

if $RUN_E2E; then
    step "Step 7: Real E2E test (with LLM API)"

    if [ -z "${LLM_API_KEY:-}" ]; then
        fail "LLM_API_KEY not set — cannot run E2E"
    else
        PROVIDER="${LLM_PROVIDER:-openai}"
        echo "  Provider: $PROVIDER"
        echo "  Model: ${LLM_MODEL:-default}"

        if $PYTHON -m pytest tests/test_e2e_real.py -v -s --tb=long 2>&1; then
            ok "Real E2E tests passed"
        else
            fail "Real E2E tests FAILED"
        fi

        # Also do a manual E2E
        echo ""
        echo "  Running manual E2E..."
        OUTPUT_FILE="/tmp/webinfo2md_verify_e2e.md"
        if $PYTHON -m webinfo2md \
            --url "https://httpbin.org/html" \
            --api-key "$LLM_API_KEY" \
            --provider "$PROVIDER" \
            --prompt "提取页面中的关键信息，整理为结构化笔记" \
            --output "$OUTPUT_FILE" \
            --verbose -j 2 2>&1; then

            if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
                ok "Manual E2E produced output ($OUTPUT_FILE)"
                echo ""
                echo -e "${CYAN}  ── Output preview (first 20 lines) ──${NC}"
                head -20 "$OUTPUT_FILE" | sed 's/^/    /'
                echo -e "${CYAN}  ─────────────────────────────────────${NC}"
            else
                fail "Manual E2E produced empty or no output"
            fi
        else
            fail "Manual E2E command failed"
        fi
    fi
else
    step "Step 7: Real E2E (skipped — use --e2e to enable)"
    warn "Skipped. Run with: LLM_API_KEY=sk-xxx $0 --e2e"
fi

# ── Step 8: Playwright real test (optional) ───────────────────────

if $RUN_BROWSER; then
    step "Step 8: Playwright browser test"

    if $PYTHON -c "import playwright.async_api" 2>/dev/null; then
        if $PYTHON -m pytest tests/test_e2e_real.py::TestPlaywrightReal -v -s --tb=long 2>&1; then
            ok "Playwright real tests passed"
        else
            fail "Playwright real tests FAILED"
        fi
    else
        fail "Playwright not importable"
    fi
else
    step "Step 8: Playwright browser test (skipped — use --browser to enable)"
    warn "Skipped. Run with: $0 --browser"
fi

# ── Summary ───────────────────────────────────────────────────────

echo ""
echo -e "${CYAN}━━━ Summary ━━━${NC}"
echo -e "  ${GREEN}Passed: $PASS${NC}"
if [ $FAIL -gt 0 ]; then
    echo -e "  ${RED}Failed: $FAIL${NC}"
    echo ""
    exit 1
else
    echo -e "  ${RED}Failed: $FAIL${NC}"
    echo ""
    echo -e "  ${GREEN}All checks passed!${NC}"
    exit 0
fi
