from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from webinfo2md.crawler.base import BaseCrawler, CrawlResult
from webinfo2md.utils.config import PlaywrightConfig


class PlaywrightCrawler(BaseCrawler):
    """Browser-based crawler for dynamic or authenticated pages."""

    def __init__(
        self,
        *,
        playwright_config: PlaywrightConfig | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.playwright_config = playwright_config or PlaywrightConfig()

    async def fetch(self, url: str) -> CrawlResult:
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - dependency error
            raise RuntimeError(
                "playwright is required for PlaywrightCrawler. "
                "Install the playwright extra and browser binaries."
            ) from exc

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=self.playwright_config.headless
            )
            context = None
            try:
                context = await browser.new_context(
                    extra_http_headers=self.headers or None,
                    user_agent=self.playwright_config.user_agent,
                    viewport={
                        "width": self.playwright_config.viewport_width,
                        "height": self.playwright_config.viewport_height,
                    },
                )
                cookies = self._build_cookies(url)
                if cookies:
                    await context.add_cookies(cookies)

                page = await context.new_page()
                wait_until = (
                    "networkidle"
                    if self.playwright_config.wait_until == "networkidle"
                    else "domcontentloaded"
                )
                response = await page.goto(
                    url,
                    wait_until=wait_until,
                    timeout=self.playwright_config.wait_timeout_ms,
                )

                if (
                    self.playwright_config.wait_until == "selector"
                    and self.playwright_config.wait_selector
                ):
                    await page.wait_for_selector(
                        self.playwright_config.wait_selector,
                        timeout=self.playwright_config.wait_timeout_ms,
                    )

                if self.playwright_config.enable_scroll:
                    await self._scroll_until_stable(page)

                if self.playwright_config.screenshot_path is not None:
                    screenshot_path = Path(self.playwright_config.screenshot_path).expanduser()
                    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path=str(screenshot_path), full_page=True)

                html = await page.content()
                title = await page.title()
                text_content = await page.evaluate("() => document.body?.innerText ?? ''")
                raw_links = await page.eval_on_selector_all(
                    "a[href]",
                    "(nodes) => nodes.map((node) => node.getAttribute('href')).filter(Boolean)",
                )
            finally:
                if context is not None:
                    await context.close()
                await browser.close()

        soup = BeautifulSoup(html, "html.parser")
        metadata = self._extract_metadata(soup)
        links = self._normalize_links(url, raw_links)

        return CrawlResult(
            url=url,
            title=title or url,
            raw_html=html,
            text_content=text_content,
            links=links,
            metadata=metadata,
            status_code=response.status if response is not None else 200,
        )

    def _build_cookies(self, url: str) -> list[dict[str, str]]:
        cookies: list[dict[str, str]] = []
        for name, value in self.cookies.items():
            cookies.append(
                {
                    "name": name,
                    "value": value,
                    "url": url,
                    "path": "/",
                }
            )

        cookie_file = self.playwright_config.cookie_file
        if cookie_file is None:
            return cookies

        path = Path(cookie_file).expanduser()
        if not path.exists():
            return cookies

        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "cookies" in payload:
            payload = payload["cookies"]
        if not isinstance(payload, list):
            return cookies

        for item in payload:
            if not isinstance(item, dict):
                continue
            normalized = {
                "name": item.get("name", ""),
                "value": item.get("value", ""),
                "path": item.get("path", "/"),
            }
            if item.get("domain"):
                normalized["domain"] = item["domain"]
            else:
                normalized["url"] = item.get("url") or url
            if item.get("sameSite"):
                normalized["sameSite"] = item["sameSite"]
            if normalized["name"]:
                cookies.append(normalized)
        return cookies

    async def _scroll_until_stable(self, page) -> None:
        last_height = -1
        stable_rounds = 0

        for _ in range(self.playwright_config.scroll_max_iterations):
            current_height = await page.evaluate("() => document.body?.scrollHeight ?? 0")
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(self.playwright_config.scroll_pause_ms)
            new_height = await page.evaluate("() => document.body?.scrollHeight ?? 0")

            if new_height <= current_height or new_height == last_height:
                stable_rounds += 1
            else:
                stable_rounds = 0

            last_height = new_height
            if stable_rounds >= 1:
                break

    def _normalize_links(self, base_url: str, raw_links: list[str]) -> list[str]:
        seen: set[str] = set()
        links: list[str] = []
        for href in raw_links:
            absolute = urljoin(base_url, href)
            if absolute not in seen:
                seen.add(absolute)
                links.append(absolute)
        return links

    def _extract_metadata(self, soup: BeautifulSoup) -> dict[str, str]:
        metadata: dict[str, str] = {}
        selectors = {
            "author": ('meta[name="author"]', "content"),
            "published_at": ('meta[property="article:published_time"]', "content"),
            "description": ('meta[name="description"]', "content"),
        }
        for key, (selector, attribute) in selectors.items():
            tag = soup.select_one(selector)
            if tag and tag.get(attribute):
                metadata[key] = tag[attribute]
        return metadata
