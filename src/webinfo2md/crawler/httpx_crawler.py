from __future__ import annotations

import asyncio
import random
import urllib.robotparser
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from webinfo2md.crawler.base import BaseCrawler, CrawlResult

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]


class HttpxCrawler(BaseCrawler):
    """Lightweight crawler for static pages."""

    async def fetch(self, url: str) -> CrawlResult:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - dependency error
            raise RuntimeError("httpx is required for HttpxCrawler") from exc

        allowed = await self._can_fetch(url)
        if not allowed:
            raise PermissionError(f"robots.txt disallows crawling {url}")

        await asyncio.sleep(random.uniform(self.crawl_delay_min, self.crawl_delay_max))
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "en-US,en;q=0.9",
            **self.headers,
        }
        async with httpx.AsyncClient(
            headers=headers,
            cookies=self.cookies,
            follow_redirects=True,
            timeout=self.timeout,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        return self._build_result(url, response.status_code, response.text)

    async def _can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        def check() -> bool:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            try:
                parser.read()
            except Exception:
                return True
            return parser.can_fetch("*", url)

        return await asyncio.to_thread(check)

    def _build_result(self, url: str, status_code: int, html: str) -> CrawlResult:
        soup = BeautifulSoup(html, "html.parser")
        title = (
            soup.title.get_text(" ", strip=True)
            if soup.title is not None
            else url
        )
        text_content = soup.get_text("\n", strip=True)
        links = self._extract_links(url, soup)
        metadata = self._extract_metadata(soup)
        return CrawlResult(
            url=url,
            title=title,
            raw_html=html,
            text_content=text_content,
            links=links,
            metadata=metadata,
            status_code=status_code,
        )

    def _extract_links(self, base_url: str, soup: BeautifulSoup) -> list[str]:
        seen: set[str] = set()
        links: list[str] = []
        for tag in soup.find_all("a", href=True):
            absolute = urljoin(base_url, tag["href"])
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
