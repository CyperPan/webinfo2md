"""Real end-to-end test: actual HTTP fetch + actual LLM API call.

This test is SKIPPED by default unless LLM_API_KEY is set.
Run with:
    LLM_API_KEY=sk-xxx pytest tests/test_e2e_real.py -v -s

Or via Makefile:
    LLM_API_KEY=sk-xxx make e2e-real
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

# Skip entire module if no API key
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai")
LLM_MODEL = os.environ.get("LLM_MODEL", "")

pytestmark = pytest.mark.skipif(
    not LLM_API_KEY,
    reason="LLM_API_KEY not set — skipping real E2E tests",
)


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def output_dir():
    """Create a temp dir for test outputs."""
    with tempfile.TemporaryDirectory(prefix="webinfo2md_e2e_") as d:
        yield Path(d)


# ── Test: httpx fetch + real LLM ──────────────────────────────────


class TestRealE2E:
    """Full pipeline tests against real URLs and real LLM APIs."""

    def test_httpbin_html(self, output_dir):
        """Fetch httpbin.org/html (always available, stable content)
        and run through the full pipeline."""
        from webinfo2md.pipeline import PipelineConfig, run_pipeline

        output_path = str(output_dir / "httpbin_test.md")
        config = PipelineConfig(
            url="https://httpbin.org/html",
            api_key=LLM_API_KEY,
            provider=LLM_PROVIDER,
            model=LLM_MODEL,
            prompt="提取页面中的所有文本内容，整理为结构化笔记",
            output=output_path,
            max_concurrency=2,
            template="notes",
        )

        result_path = asyncio.get_event_loop().run_until_complete(
            run_pipeline(config)
        )

        # Assertions
        assert result_path != "", "Pipeline should return a file path"
        p = Path(result_path)
        assert p.exists(), f"Output file should exist: {result_path}"
        content = p.read_text(encoding="utf-8")
        assert len(content) > 100, "Output should have substantial content"
        # httpbin /html returns Moby Dick text
        assert "moby" in content.lower() or "whale" in content.lower() or "herman" in content.lower(), \
            "Should contain content related to the httpbin /html page"
        print(f"\n{'='*60}")
        print(f"Output ({len(content)} chars):")
        print(content[:500])
        print(f"{'='*60}")

    def test_dry_run_no_api_call(self, output_dir):
        """Dry-run should succeed even with an invalid API key."""
        from webinfo2md.pipeline import PipelineConfig, run_pipeline

        config = PipelineConfig(
            url="https://httpbin.org/html",
            api_key="sk-fake-key-for-dry-run",
            provider="openai",
            output=str(output_dir / "dryrun.md"),
            dry_run=True,
        )

        result_path = asyncio.get_event_loop().run_until_complete(
            run_pipeline(config)
        )

        # Dry-run returns empty string (no file written)
        assert result_path == ""

    def test_concurrent_extraction_real(self, output_dir):
        """Test that concurrent extraction works with real LLM."""
        from webinfo2md.llm.factory import create_client
        from webinfo2md.llm.concurrent import (
            ConcurrentExtractor,
            merge_extracted_questions,
        )
        from webinfo2md.prompts.templates import get_extract_prompt

        client = create_client(LLM_PROVIDER, LLM_API_KEY, LLM_MODEL)

        # Simulate 3 chunks of interview content
        chunks = [
            "面试问题1: 请解释什么是Transformer架构？面试官还追问了attention mechanism的细节。",
            "系统设计题：设计一个分布式缓存系统，讨论了一致性哈希和缓存淘汰策略。",
            "行为面试：请描述一个你解决过的复杂技术问题，以及你是如何与团队协作的。",
        ]

        progress_log = []

        def on_progress(done, total, preview):
            progress_log.append((done, total))
            print(f"  Progress: {done}/{total}")

        extractor = ConcurrentExtractor(
            client, max_concurrency=2, on_progress=on_progress
        )

        results, stats = asyncio.get_event_loop().run_until_complete(
            extractor.extract_all(chunks, get_extract_prompt())
        )

        print(f"\nExtraction stats: {stats}")
        assert stats.succeeded >= 2, f"At least 2/3 chunks should succeed, got {stats.succeeded}"
        assert len(progress_log) == 3

        # Merge
        merged = merge_extracted_questions(results)
        print(f"Merged: {len(merged['questions'])} questions in {merged['categories']}")
        assert len(merged["questions"]) >= 1, "Should extract at least 1 question"


# ── Test: Playwright (if installed) ────────────────────────────────


class TestPlaywrightReal:
    """Real Playwright tests — skipped if playwright is not installed."""

    @pytest.fixture(autouse=True)
    def check_playwright(self):
        try:
            import playwright.async_api  # noqa: F401
        except ImportError:
            pytest.skip("playwright not installed")

    def test_playwright_fetch_httpbin(self):
        """Fetch httpbin with Playwright."""
        from webinfo2md.crawler.playwright_crawler import (
            PlaywrightCrawler,
            PlaywrightConfig,
        )

        config = PlaywrightConfig(headless=True)
        crawler = PlaywrightCrawler(config)

        result = asyncio.get_event_loop().run_until_complete(
            crawler.fetch("https://httpbin.org/html")
        )

        assert result.status_code == 200
        assert "moby" in result.text_content.lower() or "herman" in result.text_content.lower()
        print(f"\nPlaywright fetch: {len(result.text_content)} chars, title='{result.title}'")

    def test_smart_fetch_fallback(self):
        """Test smart_fetch with a page that needs JS rendering."""
        from webinfo2md.crawler.factory import smart_fetch

        # httpbin /html is static, so httpx should handle it
        result = asyncio.get_event_loop().run_until_complete(
            smart_fetch("https://httpbin.org/html", min_content_length=50)
        )

        assert result.engine == "httpx"  # should succeed with httpx
        assert len(result.text_content) >= 50

    def test_force_playwright(self):
        """Test --force-playwright flag."""
        from webinfo2md.crawler.factory import smart_fetch

        result = asyncio.get_event_loop().run_until_complete(
            smart_fetch(
                "https://httpbin.org/html",
                force_playwright=True,
            )
        )

        assert result.engine == "playwright"
        assert result.status_code == 200
