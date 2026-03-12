from __future__ import annotations

from webinfo2md.crawler.base import BaseCrawler, CrawlResult
from webinfo2md.crawler.httpx_crawler import HttpxCrawler
from webinfo2md.crawler.playwright_crawler import PlaywrightCrawler
from webinfo2md.utils.config import PlaywrightConfig


class AutoCrawler(BaseCrawler):
    def __init__(
        self,
        *,
        min_content_length: int = 500,
        playwright_config: PlaywrightConfig | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.min_content_length = min_content_length
        self._httpx = HttpxCrawler(
            headers=self.headers,
            cookies=self.cookies,
            timeout=self.timeout,
            crawl_delay_min=self.crawl_delay_min,
            crawl_delay_max=self.crawl_delay_max,
            verbose=self.verbose,
        )
        self._playwright = PlaywrightCrawler(
            headers=self.headers,
            cookies=self.cookies,
            timeout=self.timeout,
            crawl_delay_min=self.crawl_delay_min,
            crawl_delay_max=self.crawl_delay_max,
            verbose=self.verbose,
            playwright_config=playwright_config,
        )

    async def fetch(self, url: str) -> CrawlResult:
        try:
            result = await self._httpx.fetch(url)
            if len(result.text_content.strip()) >= self.min_content_length:
                return result
        except Exception:
            result = None

        try:
            return await self._playwright.fetch(url)
        except Exception:
            if result is not None:
                return result
            raise


class CrawlerFactory:
    @staticmethod
    async def create(
        url: str,
        *,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        timeout: float = 20.0,
        crawl_delay_min: float = 1.0,
        crawl_delay_max: float = 3.0,
        verbose: bool = False,
        min_content_length: int = 500,
        force_playwright: bool = False,
        playwright_config: PlaywrightConfig | None = None,
    ) -> BaseCrawler:
        if force_playwright:
            return PlaywrightCrawler(
                headers=headers,
                cookies=cookies,
                timeout=timeout,
                crawl_delay_min=crawl_delay_min,
                crawl_delay_max=crawl_delay_max,
                verbose=verbose,
                playwright_config=playwright_config,
            )
        return AutoCrawler(
            headers=headers,
            cookies=cookies,
            timeout=timeout,
            crawl_delay_min=crawl_delay_min,
            crawl_delay_max=crawl_delay_max,
            verbose=verbose,
            min_content_length=min_content_length,
            playwright_config=playwright_config,
        )
