from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from webinfo2md.crawler.base import CrawlResult
from webinfo2md.crawler.factory import AutoCrawler, CrawlerFactory
from webinfo2md.utils.config import PlaywrightConfig


def test_factory_returns_playwright_when_forced():
    crawler = asyncio.run(
        CrawlerFactory.create(
            "https://example.com",
            force_playwright=True,
            playwright_config=PlaywrightConfig(enable_scroll=True),
        )
    )

    assert crawler.__class__.__name__ == "PlaywrightCrawler"


def test_auto_crawler_falls_back_to_playwright():
    auto = AutoCrawler(
        headers={},
        cookies={},
        timeout=5.0,
        crawl_delay_min=0.0,
        crawl_delay_max=0.0,
        verbose=False,
        min_content_length=50,
        playwright_config=PlaywrightConfig(),
    )
    httpx_result = CrawlResult(
        url="https://example.com",
        title="short",
        raw_html="<html></html>",
        text_content="too short",
        links=[],
        status_code=200,
    )
    pw_result = CrawlResult(
        url="https://example.com",
        title="rendered",
        raw_html="<html><body>rendered</body></html>",
        text_content="rendered content " * 10,
        links=[],
        status_code=200,
    )

    auto._httpx.fetch = AsyncMock(return_value=httpx_result)
    auto._playwright.fetch = AsyncMock(return_value=pw_result)

    result = asyncio.run(auto.fetch("https://example.com"))

    assert result.title == "rendered"
    auto._playwright.fetch.assert_awaited_once()
