from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from webinfo2md.crawler.base import BaseCrawler, CrawlResult
from webinfo2md.utils.config import PlaywrightConfig

logger = logging.getLogger(__name__)

# Patterns that indicate a login wall is blocking content
_LOGIN_WALL_PATTERNS = [
    "登录后查看",
    "请登录",
    "登录后继续",
    "请先登录",
    "sign in to continue",
    "log in to view",
    "login required",
]


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
            from playwright.async_api import async_playwright, TimeoutError as PwTimeout
        except ImportError as exc:  # pragma: no cover - dependency error
            raise RuntimeError(
                "playwright is required for PlaywrightCrawler. "
                "Install the playwright extra and browser binaries."
            ) from exc

        cfg = self.playwright_config
        use_persistent = cfg.user_data_dir is not None

        async with async_playwright() as playwright:
            if use_persistent:
                result = await self._fetch_with_persistent_context(
                    playwright, url, PwTimeout
                )
            else:
                result = await self._fetch_with_temp_context(
                    playwright, url, PwTimeout
                )

        # Detect login wall
        if self._detect_login_wall(result.text_content):
            if use_persistent:
                logger.warning(
                    "Login wall detected on %s — please run with --no-headless "
                    "to open a browser window and log in manually.",
                    url,
                )
            else:
                logger.warning(
                    "Login wall detected on %s — use --user-data-dir to enable "
                    "persistent login, or --cookie-file for cookie auth.",
                    url,
                )

        return result

    async def _fetch_with_temp_context(self, playwright, url: str, PwTimeout):
        """Standard fetch using a temporary browser context."""
        cfg = self.playwright_config
        browser = await playwright.chromium.launch(
            headless=cfg.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = None
        try:
            default_ua = (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
            context = await browser.new_context(
                extra_http_headers=self.headers or None,
                user_agent=cfg.user_agent or default_ua,
                viewport={
                    "width": cfg.viewport_width,
                    "height": cfg.viewport_height,
                },
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            cookies = self._build_cookies(url)
            if cookies:
                await context.add_cookies(cookies)

            page = await context.new_page()
            await self._apply_stealth(page)
            return await self._do_fetch(page, url, PwTimeout)
        finally:
            if context is not None:
                await context.close()
            await browser.close()

    async def _fetch_with_persistent_context(self, playwright, url: str, PwTimeout):
        """Fetch using a persistent browser context that preserves login state."""
        cfg = self.playwright_config
        user_data_path = Path(cfg.user_data_dir).expanduser()
        user_data_path.mkdir(parents=True, exist_ok=True)

        default_ua = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
        context = await playwright.chromium.launch_persistent_context(
            str(user_data_path),
            headless=cfg.headless,
            args=["--disable-blink-features=AutomationControlled"],
            user_agent=cfg.user_agent or default_ua,
            viewport={
                "width": cfg.viewport_width,
                "height": cfg.viewport_height,
            },
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        try:
            cookies = self._build_cookies(url)
            if cookies:
                await context.add_cookies(cookies)

            page = context.pages[0] if context.pages else await context.new_page()
            await self._apply_stealth(page)

            # Set up API response interception if enabled
            api_responses: list[dict] = []
            if cfg.intercept_api:
                page.on("response", lambda resp: self._on_api_response(resp, api_responses))

            result = await self._do_fetch(page, url, PwTimeout)

            # If login wall detected and browser is visible, wait for manual login
            if (
                not cfg.headless
                and self._detect_login_wall(result.text_content)
            ):
                logger.info(
                    "Login wall detected. Please log in manually in the browser window. "
                    "The page will auto-refresh after you log in."
                )
                print(
                    "\n🔐 检测到登录墙，请在弹出的浏览器窗口中登录。\n"
                    "   登录完成后页面会自动刷新并继续爬取...\n"
                )
                # Wait for login by polling for login wall disappearance
                for _ in range(120):  # Wait up to 4 minutes
                    await page.wait_for_timeout(2000)
                    text = await page.evaluate("() => document.body?.innerText ?? ''")
                    if not self._detect_login_wall(text):
                        logger.info("Login successful, continuing...")
                        print("✓ 登录成功，继续爬取...")
                        # Re-navigate to target URL after login
                        result = await self._do_fetch(page, url, PwTimeout)
                        break
                else:
                    logger.warning("Login timeout after 4 minutes")

            # If we intercepted API data, append it to text_content
            if api_responses:
                api_text = "\n\n--- API Data ---\n"
                for data in api_responses:
                    api_text += json.dumps(data, ensure_ascii=False, indent=2) + "\n"
                result = CrawlResult(
                    url=result.url,
                    title=result.title,
                    raw_html=result.raw_html,
                    text_content=result.text_content + api_text,
                    links=result.links,
                    metadata=result.metadata,
                    status_code=result.status_code,
                )

            return result
        finally:
            await context.close()

    def _on_api_response(self, response, results: list[dict]) -> None:
        """Intercept API responses for structured data extraction."""
        url = response.url
        # Common API endpoints for content platforms
        api_patterns = [
            "/api/sns/web/v1/search",
            "/api/sns/web/v1/feed",
            "/api/sns/web/v2/note",
            "/api/sns/web/v1/note",
        ]
        if response.status == 200 and any(p in url for p in api_patterns):
            try:
                # Schedule the async json() call
                import asyncio
                asyncio.ensure_future(self._collect_api_data(response, results))
            except Exception:
                pass

    async def _collect_api_data(self, response, results: list[dict]) -> None:
        """Collect JSON data from intercepted API response."""
        try:
            data = await response.json()
            if isinstance(data, dict):
                results.append(data)
        except Exception:
            pass

    async def _do_fetch(self, page, url: str, PwTimeout) -> CrawlResult:
        """Core fetch logic shared by both context modes."""
        cfg = self.playwright_config

        response = await self._goto_with_fallback(page, url, PwTimeout)

        if cfg.wait_until == "selector" and cfg.wait_selector:
            try:
                await page.wait_for_selector(
                    cfg.wait_selector,
                    timeout=cfg.wait_timeout_ms,
                )
            except PwTimeout:
                logger.warning("Selector wait timed out, continuing anyway")

        # Give SPAs a moment to render after initial load
        await page.wait_for_timeout(2000)

        if cfg.enable_scroll:
            await self._scroll_until_stable(page)

        if cfg.screenshot_path is not None:
            screenshot_path = Path(cfg.screenshot_path).expanduser()
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot_path), full_page=True)

        html = await page.content()
        title = await page.title()
        text_content = await page.evaluate("() => document.body?.innerText ?? ''")
        raw_links = await self._safe_extract_links(page)

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

    async def _apply_stealth(self, page) -> None:
        """Apply anti-detection measures to avoid bot fingerprinting."""
        try:
            from playwright_stealth import stealth_async
            await stealth_async(page)
        except ImportError:
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
                window.chrome = {runtime: {}};
            """)

    async def _goto_with_fallback(self, page, url: str, PwTimeout):
        """Navigate to URL, using domcontentloaded first then optionally waiting for networkidle."""
        if self.playwright_config.wait_until == "networkidle":
            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.playwright_config.wait_timeout_ms,
            )
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except PwTimeout:
                logger.debug("networkidle not reached for %s, continuing", url)
            return response
        else:
            return await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.playwright_config.wait_timeout_ms,
            )

    async def _safe_extract_links(self, page) -> list[str]:
        """Extract links, handling context destruction from client-side navigation."""
        try:
            return await page.eval_on_selector_all(
                "a[href]",
                "(nodes) => nodes.map((node) => node.getAttribute('href')).filter(Boolean)",
            )
        except Exception:
            logger.warning("Link extraction failed (page may have navigated), returning empty list")
            return []

    def _detect_login_wall(self, text_content: str) -> bool:
        """Check if the page content suggests a login wall is blocking real content."""
        lower = text_content.lower()
        for pattern in _LOGIN_WALL_PATTERNS:
            if pattern in lower:
                return True
        return False

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
