"""Tests for crawler factory smart_fetch logic."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from webinfo2md.crawler.factory import smart_fetch, fetch_with_httpx, CrawlResult


class TestSmartFetch:
    def test_httpx_sufficient_content(self):
        """When httpx returns enough content, no Playwright fallback."""
        mock_result = CrawlResult(
            url="https://example.com",
            title="Test",
            raw_html="<html><body>" + "x" * 600 + "</body></html>",
            text_content="x" * 600,
            links=[],
            metadata={},
            status_code=200,
            engine="httpx",
        )

        with patch(
            "webinfo2md.crawler.factory.fetch_with_httpx",
            new_callable=lambda: AsyncMock(return_value=mock_result),
        ):
            result = asyncio.get_event_loop().run_until_complete(
                smart_fetch("https://example.com", min_content_length=500)
            )

        assert result.engine == "httpx"
        assert len(result.text_content) >= 500

    def test_httpx_too_short_falls_back(self):
        """When httpx content is too short, tries Playwright."""
        short_result = CrawlResult(
            url="https://spa.example.com",
            title="",
            raw_html="<html></html>",
            text_content="Loading...",
            links=[],
            metadata={},
            status_code=200,
            engine="httpx",
        )

        pw_result = MagicMock()
        pw_result.url = "https://spa.example.com"
        pw_result.title = "SPA Page"
        pw_result.raw_html = "<html><body>" + "content " * 200 + "</body></html>"
        pw_result.text_content = "content " * 200
        pw_result.links = []
        pw_result.metadata = {}
        pw_result.status_code = 200

        mock_crawler = AsyncMock()
        mock_crawler.fetch.return_value = pw_result

        with patch(
            "webinfo2md.crawler.factory.fetch_with_httpx",
            new_callable=lambda: AsyncMock(return_value=short_result),
        ), patch(
            "webinfo2md.crawler.factory.PlaywrightCrawler",
            return_value=mock_crawler,
        ), patch(
            "webinfo2md.crawler.factory.PlaywrightCrawlerFactory",
        ):
            # Need to also patch the import
            with patch.dict("sys.modules", {
                "webinfo2md.crawler.playwright_crawler": MagicMock(
                    PlaywrightCrawler=lambda: mock_crawler,
                    PlaywrightCrawlerFactory=MagicMock(
                        from_dict=MagicMock(return_value=mock_crawler)
                    ),
                )
            }):
                result = asyncio.get_event_loop().run_until_complete(
                    smart_fetch(
                        "https://spa.example.com",
                        min_content_length=500,
                        playwright_config={"headless": True},
                    )
                )

        assert result.engine == "playwright"

    def test_force_playwright_skips_httpx(self):
        """--force-playwright goes straight to browser."""
        pw_result = MagicMock()
        pw_result.url = "https://example.com"
        pw_result.title = "Browser Page"
        pw_result.raw_html = "<html>...</html>"
        pw_result.text_content = "Full rendered content " * 50
        pw_result.links = []
        pw_result.metadata = {}
        pw_result.status_code = 200

        mock_crawler = AsyncMock()
        mock_crawler.fetch.return_value = pw_result

        with patch.dict("sys.modules", {
            "webinfo2md.crawler.playwright_crawler": MagicMock(
                PlaywrightCrawler=lambda: mock_crawler,
                PlaywrightCrawlerFactory=MagicMock(
                    from_dict=MagicMock(return_value=mock_crawler)
                ),
            )
        }):
            result = asyncio.get_event_loop().run_until_complete(
                smart_fetch(
                    "https://example.com",
                    force_playwright=True,
                    playwright_config={"headless": True},
                )
            )

        assert result.engine == "playwright"
