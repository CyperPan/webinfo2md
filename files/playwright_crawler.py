"""Enhanced Playwright crawler for JS-rendered and authenticated pages.

Features:
- Cookie injection (from file, dict, or browser string)
- Custom header support
- Infinite scroll detection and execution
- Configurable wait strategies (networkidle, selector, timeout)
- Screenshot capture for debugging
- Graceful degradation when playwright is not installed
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Lazy import — playwright is an optional heavyweight dependency
_PLAYWRIGHT_AVAILABLE: Optional[bool] = None


def _check_playwright() -> bool:
    global _PLAYWRIGHT_AVAILABLE
    if _PLAYWRIGHT_AVAILABLE is None:
        try:
            import playwright.async_api  # noqa: F401

            _PLAYWRIGHT_AVAILABLE = True
        except ImportError:
            _PLAYWRIGHT_AVAILABLE = False
    return _PLAYWRIGHT_AVAILABLE


@dataclass
class PlaywrightConfig:
    """Configuration for the Playwright crawler."""

    # --- Authentication ---
    cookies: Optional[list[dict[str, Any]]] = None
    cookie_file: Optional[str] = None  # Path to JSON cookie file
    headers: dict[str, str] = field(default_factory=dict)

    # --- Page loading ---
    wait_strategy: str = "networkidle"  # "networkidle" | "selector" | "timeout"
    wait_selector: Optional[str] = None  # CSS selector to wait for
    wait_timeout_ms: int = 15000

    # --- Scrolling ---
    enable_scroll: bool = False
    scroll_max_iterations: int = 10
    scroll_pause_ms: int = 1500
    scroll_selector: Optional[str] = None  # Element to scroll (default: window)

    # --- Browser ---
    headless: bool = True
    viewport_width: int = 1280
    viewport_height: int = 800
    user_agent: Optional[str] = None

    # --- Debug ---
    screenshot_path: Optional[str] = None  # Save screenshot after load

    def load_cookies_from_file(self) -> list[dict[str, Any]]:
        """Load cookies from a JSON file (Chromium export format)."""
        if not self.cookie_file:
            return []
        path = Path(self.cookie_file).expanduser()
        if not path.exists():
            logger.warning("Cookie file not found: %s", path)
            return []
        with open(path) as f:
            data = json.load(f)
        # Handle both [{...}] and {"cookies": [{...}]} formats
        if isinstance(data, dict) and "cookies" in data:
            data = data["cookies"]
        return data

    def get_all_cookies(self) -> list[dict[str, Any]]:
        """Merge inline cookies with file-loaded cookies."""
        cookies = list(self.cookies or [])
        cookies.extend(self.load_cookies_from_file())
        return cookies


@dataclass
class CrawlResult:
    """Result from crawling a single URL."""

    url: str
    title: str
    raw_html: str
    text_content: str
    links: list[str]
    metadata: dict[str, Any]
    status_code: int


class PlaywrightCrawler:
    """Async Playwright-based crawler for JS-heavy / authenticated pages.

    Usage:
        config = PlaywrightConfig(
            cookies=[{"name": "session", "value": "abc", "domain": ".example.com"}],
            enable_scroll=True,
            scroll_max_iterations=5,
        )
        crawler = PlaywrightCrawler(config)
        result = await crawler.fetch("https://example.com/post/123")
    """

    def __init__(self, config: Optional[PlaywrightConfig] = None):
        if not _check_playwright():
            raise ImportError(
                "playwright is not installed. "
                "Install with: pip install playwright && python -m playwright install chromium"
            )
        self.config = config or PlaywrightConfig()

    async def fetch(self, url: str) -> CrawlResult:
        """Fetch a URL using a headless browser."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.config.headless)
            context = await browser.new_context(
                viewport={
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height,
                },
                user_agent=self.config.user_agent,
                extra_http_headers=self.config.headers or None,
            )

            # Inject cookies
            cookies = self.config.get_all_cookies()
            if cookies:
                # Playwright expects cookies with url or domain+path
                prepared = []
                for c in cookies:
                    entry = {
                        "name": c.get("name", ""),
                        "value": c.get("value", ""),
                    }
                    if "domain" in c:
                        entry["domain"] = c["domain"]
                        entry["path"] = c.get("path", "/")
                    else:
                        entry["url"] = url
                    if "sameSite" in c:
                        entry["sameSite"] = c["sameSite"]
                    prepared.append(entry)
                await context.add_cookies(prepared)
                logger.info("Injected %d cookies", len(prepared))

            page = await context.new_page()

            # Navigate
            try:
                response = await page.goto(
                    url,
                    wait_until=(
                        "networkidle"
                        if self.config.wait_strategy == "networkidle"
                        else "domcontentloaded"
                    ),
                    timeout=self.config.wait_timeout_ms,
                )
                status_code = response.status if response else 0
            except Exception as e:
                logger.error("Navigation failed for %s: %s", url, e)
                await browser.close()
                return CrawlResult(
                    url=url,
                    title="",
                    raw_html="",
                    text_content="",
                    links=[],
                    metadata={"error": str(e)},
                    status_code=0,
                )

            # Wait for specific selector if configured
            if (
                self.config.wait_strategy == "selector"
                and self.config.wait_selector
            ):
                try:
                    await page.wait_for_selector(
                        self.config.wait_selector,
                        timeout=self.config.wait_timeout_ms,
                    )
                except Exception as e:
                    logger.warning(
                        "Selector wait timed out for '%s': %s",
                        self.config.wait_selector,
                        e,
                    )

            # Infinite scroll
            if self.config.enable_scroll:
                await self._infinite_scroll(page)

            # Extract content
            title = await page.title()
            raw_html = await page.content()
            text_content = await page.evaluate(
                "() => document.body ? document.body.innerText : ''"
            )
            links = await page.evaluate(
                """() => {
                    return Array.from(document.querySelectorAll('a[href]'))
                        .map(a => a.href)
                        .filter(h => h.startsWith('http'))
                }"""
            )

            # Extract metadata
            metadata = await page.evaluate(
                """() => {
                    const meta = {};
                    const og = document.querySelectorAll('meta[property^="og:"]');
                    og.forEach(m => { meta[m.getAttribute('property')] = m.getAttribute('content'); });
                    const desc = document.querySelector('meta[name="description"]');
                    if (desc) meta['description'] = desc.getAttribute('content');
                    const author = document.querySelector('meta[name="author"]');
                    if (author) meta['author'] = author.getAttribute('content');
                    const time = document.querySelector('time[datetime]');
                    if (time) meta['published_at'] = time.getAttribute('datetime');
                    return meta;
                }"""
            )

            # Screenshot for debugging
            if self.config.screenshot_path:
                try:
                    await page.screenshot(
                        path=self.config.screenshot_path, full_page=True
                    )
                    logger.info("Screenshot saved: %s", self.config.screenshot_path)
                except Exception as e:
                    logger.warning("Screenshot failed: %s", e)

            await browser.close()

            return CrawlResult(
                url=url,
                title=title,
                raw_html=raw_html,
                text_content=text_content,
                links=links,
                metadata=metadata,
                status_code=status_code,
            )

    async def _infinite_scroll(self, page) -> None:
        """Scroll down incrementally, stopping when no new content loads."""
        prev_height = 0
        for i in range(self.config.scroll_max_iterations):
            current_height = await page.evaluate(
                "() => document.body.scrollHeight"
            )
            if current_height == prev_height:
                logger.info("Scroll stabilized after %d iterations", i)
                break
            prev_height = current_height

            if self.config.scroll_selector:
                # Scroll a specific container
                await page.evaluate(
                    f"""() => {{
                        const el = document.querySelector('{self.config.scroll_selector}');
                        if (el) el.scrollTop = el.scrollHeight;
                    }}"""
                )
            else:
                await page.evaluate(
                    "() => window.scrollTo(0, document.body.scrollHeight)"
                )

            await page.wait_for_timeout(self.config.scroll_pause_ms)
        else:
            logger.info(
                "Reached max scroll iterations (%d)",
                self.config.scroll_max_iterations,
            )


class PlaywrightCrawlerFactory:
    """Create PlaywrightCrawler from config dict or PlaywrightConfig."""

    @staticmethod
    def from_dict(config: dict[str, Any]) -> PlaywrightCrawler:
        """Create from a flat config dictionary (e.g. from YAML)."""
        pw_config = PlaywrightConfig(
            cookies=config.get("cookies"),
            cookie_file=config.get("cookie_file"),
            headers=config.get("headers", {}),
            wait_strategy=config.get("wait_strategy", "networkidle"),
            wait_selector=config.get("wait_selector"),
            wait_timeout_ms=config.get("wait_timeout_ms", 15000),
            enable_scroll=config.get("enable_scroll", False),
            scroll_max_iterations=config.get("scroll_max_iterations", 10),
            scroll_pause_ms=config.get("scroll_pause_ms", 1500),
            scroll_selector=config.get("scroll_selector"),
            headless=config.get("headless", True),
            user_agent=config.get("user_agent"),
            screenshot_path=config.get("screenshot_path"),
        )
        return PlaywrightCrawler(pw_config)
