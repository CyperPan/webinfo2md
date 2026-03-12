"""Tests for PlaywrightCrawler with fully mocked browser.

These tests never launch a real browser — they mock playwright.async_api
to verify our crawler logic: cookie injection, scroll behavior, config handling.
"""

from __future__ import annotations

import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from tempfile import NamedTemporaryFile

from webinfo2md.crawler.playwright_crawler import (
    PlaywrightConfig,
    PlaywrightCrawler,
    PlaywrightCrawlerFactory,
)


# ── Helpers ────────────────────────────────────────────────────────


def _make_mock_page(
    title: str = "Test Page",
    html: str = "<html><body><p>Hello</p></body></html>",
    inner_text: str = "Hello",
    links: list[str] | None = None,
    scroll_heights: list[int] | None = None,
):
    """Create a mock Playwright page object."""
    page = AsyncMock()
    page.title.return_value = title
    page.content.return_value = html

    # Track scroll height calls for infinite scroll testing
    _scroll_call = 0
    heights = scroll_heights or [800]

    async def _evaluate(script):
        nonlocal _scroll_call
        if "innerText" in script:
            return inner_text
        if "scrollHeight" in script:
            idx = min(_scroll_call, len(heights) - 1)
            _scroll_call += 1
            return heights[idx]
        if "querySelectorAll" in script:
            return links or []
        if "meta[" in script or "og:" in script:
            return {}
        if "scrollTo" in script or "scrollTop" in script:
            return None
        return None

    page.evaluate = _evaluate
    page.wait_for_timeout = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.screenshot = AsyncMock()

    response = AsyncMock()
    response.status = 200
    page.goto.return_value = response

    return page


def _make_mock_playwright(page):
    """Create the full mock chain: playwright → browser → context → page."""
    context = AsyncMock()
    context.new_page.return_value = page
    context.add_cookies = AsyncMock()

    browser = AsyncMock()
    browser.new_context.return_value = context

    pw_instance = AsyncMock()
    pw_instance.chromium.launch.return_value = browser

    # async context manager
    pw_cm = AsyncMock()
    pw_cm.__aenter__ = AsyncMock(return_value=pw_instance)
    pw_cm.__aexit__ = AsyncMock(return_value=False)

    return pw_cm, context, browser


# ── Tests: PlaywrightConfig ────────────────────────────────────────


class TestPlaywrightConfig:
    def test_default_config(self):
        config = PlaywrightConfig()
        assert config.headless is True
        assert config.wait_strategy == "networkidle"
        assert config.enable_scroll is False
        assert config.get_all_cookies() == []

    def test_inline_cookies(self):
        config = PlaywrightConfig(
            cookies=[{"name": "session", "value": "abc123", "domain": ".example.com"}]
        )
        cookies = config.get_all_cookies()
        assert len(cookies) == 1
        assert cookies[0]["name"] == "session"

    def test_cookie_file_loading(self, tmp_path):
        cookie_data = [
            {"name": "token", "value": "xyz", "domain": ".test.com"}
        ]
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(cookie_data))

        config = PlaywrightConfig(cookie_file=str(cookie_file))
        cookies = config.get_all_cookies()
        assert len(cookies) == 1
        assert cookies[0]["value"] == "xyz"

    def test_cookie_file_with_wrapper(self, tmp_path):
        """Handle {"cookies": [...]} format from browser extensions."""
        cookie_data = {"cookies": [
            {"name": "a", "value": "1", "domain": ".x.com"},
            {"name": "b", "value": "2", "domain": ".x.com"},
        ]}
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps(cookie_data))

        config = PlaywrightConfig(cookie_file=str(cookie_file))
        assert len(config.get_all_cookies()) == 2

    def test_missing_cookie_file(self):
        config = PlaywrightConfig(cookie_file="/nonexistent/cookies.json")
        assert config.get_all_cookies() == []

    def test_merge_inline_and_file_cookies(self, tmp_path):
        cookie_file = tmp_path / "cookies.json"
        cookie_file.write_text(json.dumps([
            {"name": "file_cookie", "value": "f1", "domain": ".x.com"}
        ]))
        config = PlaywrightConfig(
            cookies=[{"name": "inline", "value": "i1", "domain": ".x.com"}],
            cookie_file=str(cookie_file),
        )
        all_cookies = config.get_all_cookies()
        assert len(all_cookies) == 2
        names = {c["name"] for c in all_cookies}
        assert names == {"inline", "file_cookie"}


# ── Tests: PlaywrightCrawler ──────────────────────────────────────


class TestPlaywrightCrawler:
    @patch("webinfo2md.crawler.playwright_crawler._PLAYWRIGHT_AVAILABLE", True)
    def test_basic_fetch(self):
        page = _make_mock_page(title="Interview Blog", inner_text="Q: What is ML?")
        pw_cm, context, browser = _make_mock_playwright(page)

        with patch(
            "webinfo2md.crawler.playwright_crawler.async_playwright",
            return_value=pw_cm,
        ):
            crawler = PlaywrightCrawler(PlaywrightConfig())
            result = asyncio.get_event_loop().run_until_complete(
                crawler.fetch("https://example.com/post")
            )

        assert result.title == "Interview Blog"
        assert result.text_content == "Q: What is ML?"
        assert result.status_code == 200

    @patch("webinfo2md.crawler.playwright_crawler._PLAYWRIGHT_AVAILABLE", True)
    def test_cookie_injection(self):
        page = _make_mock_page()
        pw_cm, context, browser = _make_mock_playwright(page)

        config = PlaywrightConfig(
            cookies=[
                {"name": "session", "value": "s123", "domain": ".example.com"},
                {"name": "token", "value": "t456", "domain": ".example.com"},
            ]
        )

        with patch(
            "webinfo2md.crawler.playwright_crawler.async_playwright",
            return_value=pw_cm,
        ):
            crawler = PlaywrightCrawler(config)
            asyncio.get_event_loop().run_until_complete(
                crawler.fetch("https://example.com")
            )

        context.add_cookies.assert_called_once()
        injected = context.add_cookies.call_args[0][0]
        assert len(injected) == 2
        assert injected[0]["name"] == "session"

    @patch("webinfo2md.crawler.playwright_crawler._PLAYWRIGHT_AVAILABLE", True)
    def test_infinite_scroll(self):
        """Scroll stops when page height stabilizes."""
        page = _make_mock_page(
            scroll_heights=[800, 1600, 2400, 2400]  # stabilizes on 3rd scroll
        )
        pw_cm, context, browser = _make_mock_playwright(page)

        config = PlaywrightConfig(
            enable_scroll=True,
            scroll_max_iterations=10,
            scroll_pause_ms=100,
        )

        with patch(
            "webinfo2md.crawler.playwright_crawler.async_playwright",
            return_value=pw_cm,
        ):
            crawler = PlaywrightCrawler(config)
            asyncio.get_event_loop().run_until_complete(
                crawler.fetch("https://example.com/feed")
            )

        # Should have called wait_for_timeout for scroll pauses
        # (exact count depends on when stabilization is detected)
        assert page.wait_for_timeout.call_count >= 2

    @patch("webinfo2md.crawler.playwright_crawler._PLAYWRIGHT_AVAILABLE", True)
    def test_selector_wait(self):
        page = _make_mock_page()
        pw_cm, context, browser = _make_mock_playwright(page)

        config = PlaywrightConfig(
            wait_strategy="selector",
            wait_selector=".post-content",
        )

        with patch(
            "webinfo2md.crawler.playwright_crawler.async_playwright",
            return_value=pw_cm,
        ):
            crawler = PlaywrightCrawler(config)
            asyncio.get_event_loop().run_until_complete(
                crawler.fetch("https://example.com")
            )

        page.wait_for_selector.assert_called_once_with(
            ".post-content", timeout=15000
        )


# ── Tests: Factory ─────────────────────────────────────────────────


class TestPlaywrightCrawlerFactory:
    @patch("webinfo2md.crawler.playwright_crawler._PLAYWRIGHT_AVAILABLE", True)
    def test_from_dict(self):
        config_dict = {
            "enable_scroll": True,
            "scroll_max_iterations": 5,
            "cookie_file": "/tmp/cookies.json",
            "headers": {"X-Custom": "value"},
            "wait_strategy": "selector",
            "wait_selector": "#content",
        }
        crawler = PlaywrightCrawlerFactory.from_dict(config_dict)
        assert crawler.config.enable_scroll is True
        assert crawler.config.scroll_max_iterations == 5
        assert crawler.config.headers == {"X-Custom": "value"}
        assert crawler.config.wait_strategy == "selector"

    @patch("webinfo2md.crawler.playwright_crawler._PLAYWRIGHT_AVAILABLE", True)
    def test_from_empty_dict(self):
        crawler = PlaywrightCrawlerFactory.from_dict({})
        assert crawler.config.headless is True
        assert crawler.config.enable_scroll is False
