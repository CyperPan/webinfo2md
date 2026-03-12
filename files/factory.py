"""Crawler factory: auto-selects httpx or Playwright based on content quality.

Strategy:
1. Try httpx first (fast, lightweight)
2. If content is too short (< min_content_length), fall back to Playwright
3. If --force-playwright is set, skip httpx entirely
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Rotate User-Agent to reduce blocking
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


@dataclass
class CrawlResult:
    """Unified crawl result across both engines."""

    url: str
    title: str
    raw_html: str
    text_content: str
    links: list[str]
    metadata: dict[str, Any]
    status_code: int
    engine: str = "httpx"  # "httpx" or "playwright"


async def fetch_with_httpx(
    url: str,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 30.0,
) -> CrawlResult:
    """Lightweight fetch using httpx."""
    import httpx

    ua = random.choice(_USER_AGENTS)
    default_headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    }
    if headers:
        default_headers.update(headers)

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        headers=default_headers,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    raw_html = resp.text
    title = ""
    text_content = raw_html
    links: list[str] = []

    # Basic extraction without heavy deps
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw_html, "html.parser")
        title = soup.title.string if soup.title else ""
        # Remove script/style
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text_content = soup.get_text(separator="\n", strip=True)
        links = [
            a["href"]
            for a in soup.find_all("a", href=True)
            if a["href"].startswith("http")
        ]
    except ImportError:
        pass

    return CrawlResult(
        url=url,
        title=title or "",
        raw_html=raw_html,
        text_content=text_content,
        links=links,
        metadata={},
        status_code=resp.status_code,
        engine="httpx",
    )


async def smart_fetch(
    url: str,
    min_content_length: int = 500,
    force_playwright: bool = False,
    playwright_config: Optional[dict[str, Any]] = None,
    httpx_headers: Optional[dict[str, str]] = None,
) -> CrawlResult:
    """Fetch a URL with automatic engine selection.

    1. If force_playwright, go straight to Playwright.
    2. Otherwise, try httpx first.
    3. If httpx content is too short, fall back to Playwright.
    4. If Playwright is unavailable, return httpx result anyway.
    """
    httpx_result: Optional[CrawlResult] = None

    if not force_playwright:
        try:
            httpx_result = await fetch_with_httpx(url, headers=httpx_headers)
            content_len = len(httpx_result.text_content.strip())
            if content_len >= min_content_length:
                logger.info(
                    "httpx OK: %s (%d chars)", url, content_len
                )
                return httpx_result
            logger.info(
                "httpx content too short (%d < %d), trying Playwright",
                content_len,
                min_content_length,
            )
        except Exception as e:
            logger.warning("httpx failed for %s: %s, trying Playwright", url, e)

    # Playwright fallback
    try:
        from webinfo2md.crawler.playwright_crawler import (
            PlaywrightCrawler,
            PlaywrightCrawlerFactory,
        )

        if playwright_config:
            crawler = PlaywrightCrawlerFactory.from_dict(playwright_config)
        else:
            crawler = PlaywrightCrawler()

        pw_result = await crawler.fetch(url)
        return CrawlResult(
            url=pw_result.url,
            title=pw_result.title,
            raw_html=pw_result.raw_html,
            text_content=pw_result.text_content,
            links=pw_result.links,
            metadata=pw_result.metadata,
            status_code=pw_result.status_code,
            engine="playwright",
        )
    except ImportError:
        logger.warning(
            "Playwright not available. "
            "Install: pip install playwright && python -m playwright install chromium"
        )
        if httpx_result:
            return httpx_result
        raise RuntimeError(
            f"Cannot fetch {url}: httpx failed and Playwright is not installed"
        )
    except Exception as e:
        logger.error("Playwright also failed for %s: %s", url, e)
        if httpx_result:
            return httpx_result
        raise
