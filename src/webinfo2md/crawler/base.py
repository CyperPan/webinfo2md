from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class CrawlResult:
    url: str
    title: str
    raw_html: str
    text_content: str
    links: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    status_code: int = 0
    crawled_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class BaseCrawler(ABC):
    def __init__(
        self,
        *,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        timeout: float = 20.0,
        crawl_delay_min: float = 1.0,
        crawl_delay_max: float = 3.0,
        verbose: bool = False,
    ) -> None:
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.timeout = timeout
        self.crawl_delay_min = crawl_delay_min
        self.crawl_delay_max = crawl_delay_max
        self.verbose = verbose

    @abstractmethod
    async def fetch(self, url: str) -> CrawlResult:
        raise NotImplementedError
