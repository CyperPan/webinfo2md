from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from webinfo2md.crawler.factory import CrawlerFactory
from webinfo2md.crawler.playwright_crawler import PlaywrightCrawler
from webinfo2md.llm.concurrent import ConcurrentExtractor, ExtractionTask
from webinfo2md.llm.factory import create_client
from webinfo2md.pipeline import PipelineRunResult, WebInfo2MDPipeline
from webinfo2md.utils.config import PipelineConfig, PlaywrightConfig

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai")
LLM_MODEL = os.environ.get("LLM_MODEL") or None

pytestmark = pytest.mark.skipif(
    not LLM_API_KEY,
    reason="LLM_API_KEY not set; skipping real end-to-end tests.",
)


@pytest.fixture
def output_dir():
    with tempfile.TemporaryDirectory(prefix="webinfo2md-e2e-") as directory:
        yield Path(directory)


class TestRealE2E:
    def test_real_pipeline_httpbin(self, output_dir):
        config = PipelineConfig(
            url="https://httpbin.org/html",
            api_key=LLM_API_KEY,
            provider=LLM_PROVIDER,
            model=LLM_MODEL,
            prompt="提取页面中的关键信息，整理为结构化中文笔记。",
            template="notes",
            output=output_dir / "httpbin.md",
            max_concurrency=2,
            crawl_delay_min=0.0,
            crawl_delay_max=0.0,
            min_content_length=10,
        )

        result = asyncio.run(WebInfo2MDPipeline().run(config))

        assert isinstance(result, PipelineRunResult)
        assert result.dry_run is False
        assert result.output_path is not None
        output_path = Path(result.output_path)
        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert len(content) > 100
        assert any(keyword in content.lower() for keyword in ["moby", "whale", "herman"])

    def test_real_dry_run_does_not_require_valid_key(self, output_dir):
        config = PipelineConfig(
            url="https://httpbin.org/html",
            api_key="sk-invalid-dry-run-placeholder",
            provider="openai",
            output=output_dir / "dry-run.md",
            dry_run=True,
            crawl_delay_min=0.0,
            crawl_delay_max=0.0,
            min_content_length=10,
        )

        result = asyncio.run(WebInfo2MDPipeline().run(config))

        assert result.dry_run is True
        assert result.question_count is None
        assert result.output_path == str(output_dir / "dry-run.md")
        assert not (output_dir / "dry-run.md").exists()

    def test_real_concurrent_extraction(self):
        llm = create_client(LLM_PROVIDER, LLM_API_KEY, LLM_MODEL)
        progress: list[tuple[int, int]] = []
        extractor = ConcurrentExtractor(
            llm,
            system_prompt="你是一个信息提取助手。请从给定文本中提取面试问题，并输出 JSON。",
            max_concurrency=2,
            on_progress=lambda done, total: progress.append((done, total)),
        )
        tasks = [
            ExtractionTask(
                source="chunk-1",
                user_prompt="请输出 JSON：包含一个 questions 数组，问题是 什么是 Transformer？",
            ),
            ExtractionTask(
                source="chunk-2",
                user_prompt="请输出 JSON：包含一个 questions 数组，问题是 如何设计分布式缓存？",
            ),
            ExtractionTask(
                source="chunk-3",
                user_prompt="请输出 JSON：包含一个 questions 数组，问题是 介绍一个复杂项目经历。",
            ),
        ]

        results, stats = asyncio.run(extractor.extract_all(tasks))

        assert len(results) == 3
        assert stats.succeeded >= 2
        assert stats.failed <= 1
        assert progress[-1] == (3, 3)


class TestPlaywrightReal:
    @pytest.fixture(autouse=True)
    def ensure_playwright(self):
        try:
            import playwright.async_api  # noqa: F401
        except ImportError:
            pytest.skip("playwright not installed")

    def test_force_playwright_factory(self):
        crawler = asyncio.run(
            CrawlerFactory.create(
                "https://httpbin.org/html",
                force_playwright=True,
                crawl_delay_min=0.0,
                crawl_delay_max=0.0,
                playwright_config=PlaywrightConfig(headless=True),
            )
        )

        result = asyncio.run(crawler.fetch("https://httpbin.org/html"))

        assert result.status_code == 200
        assert len(result.text_content) > 50

    def test_playwright_direct_fetch(self):
        crawler = PlaywrightCrawler(
            headers={},
            cookies={},
            timeout=20.0,
            crawl_delay_min=0.0,
            crawl_delay_max=0.0,
            verbose=False,
            playwright_config=PlaywrightConfig(headless=True),
        )

        result = asyncio.run(crawler.fetch("https://httpbin.org/html"))

        assert result.status_code == 200
        assert any(keyword in result.text_content.lower() for keyword in ["moby", "whale", "herman"])
