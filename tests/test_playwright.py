from __future__ import annotations

import asyncio
import json
import types
from unittest.mock import AsyncMock, patch

from webinfo2md.crawler.playwright_crawler import PlaywrightCrawler
from webinfo2md.utils.config import PlaywrightConfig


def _install_fake_playwright(page):
    browser = AsyncMock()
    context = AsyncMock()
    context.new_page.return_value = page
    browser.new_context.return_value = context

    chromium = AsyncMock()
    chromium.launch.return_value = browser

    playwright_instance = types.SimpleNamespace(chromium=chromium)

    class AsyncPlaywrightContextManager:
        async def __aenter__(self):
            return playwright_instance

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async_api_module = types.ModuleType("playwright.async_api")
    async_api_module.async_playwright = lambda: AsyncPlaywrightContextManager()
    playwright_module = types.ModuleType("playwright")

    return patch.dict(
        "sys.modules",
        {
            "playwright": playwright_module,
            "playwright.async_api": async_api_module,
        },
    ), context


def _build_page(*, scroll_heights: list[int] | None = None):
    page = AsyncMock()
    page.title.return_value = "Interview Post"
    page.content.return_value = "<html><head><meta name='author' content='codex'></head><body>Body</body></html>"
    page.eval_on_selector_all.return_value = ["/a", "https://example.com/b"]
    heights = iter(scroll_heights or [100, 200, 200])

    async def evaluate(script: str):
        if "innerText" in script:
            return "Body"
        if "scrollHeight" in script:
            return next(heights, 200)
        return None

    page.evaluate.side_effect = evaluate
    page.wait_for_selector = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    response = AsyncMock()
    response.status = 200
    page.goto.return_value = response
    return page


def test_playwright_fetch_uses_cookie_file_and_scroll(tmp_path):
    cookie_file = tmp_path / "cookies.json"
    cookie_file.write_text(
        json.dumps([{"name": "session", "value": "abc", "domain": ".example.com"}]),
        encoding="utf-8",
    )
    page = _build_page()
    module_patch, context = _install_fake_playwright(page)

    with module_patch:
        crawler = PlaywrightCrawler(
            headers={"X-Test": "1"},
            cookies={"local": "cookie"},
            timeout=5.0,
            crawl_delay_min=0.0,
            crawl_delay_max=0.0,
            verbose=False,
            playwright_config=PlaywrightConfig(
                cookie_file=cookie_file,
                enable_scroll=True,
                scroll_pause_ms=10,
            ),
        )
        result = asyncio.run(crawler.fetch("https://example.com/post"))

    injected = context.add_cookies.await_args.args[0]
    assert {item["name"] for item in injected} == {"local", "session"}
    assert result.title == "Interview Post"
    assert result.links == ["https://example.com/a", "https://example.com/b"]
    assert page.wait_for_timeout.await_count >= 1


def test_playwright_fetch_waits_for_selector_and_saves_screenshot(tmp_path):
    page = _build_page(scroll_heights=[100, 100])
    module_patch, context = _install_fake_playwright(page)
    screenshot = tmp_path / "debug.png"

    with module_patch:
        crawler = PlaywrightCrawler(
            headers={},
            cookies={},
            timeout=5.0,
            crawl_delay_min=0.0,
            crawl_delay_max=0.0,
            verbose=False,
            playwright_config=PlaywrightConfig(
                wait_until="selector",
                wait_selector=".content",
                screenshot_path=screenshot,
            ),
        )
        asyncio.run(crawler.fetch("https://example.com/post"))

    page.wait_for_selector.assert_awaited_once_with(".content", timeout=20000)
    page.screenshot.assert_awaited_once_with(path=str(screenshot), full_page=True)
    context.add_cookies.assert_not_awaited()
