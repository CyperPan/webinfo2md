from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable

from webinfo2md.llm.base import BaseLLMClient


@dataclass(slots=True)
class ExtractionTask:
    source: str
    user_prompt: str


@dataclass(slots=True)
class ExtractionResult:
    index: int
    source: str
    raw_response: str = ""
    error: str | None = None
    latency_ms: float = 0.0
    retries: int = 0


@dataclass(slots=True)
class ExtractionStats:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    retries: int = 0
    total_latency_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        if self.succeeded == 0:
            return 0.0
        return self.total_latency_ms / self.succeeded


ProgressCallback = Callable[[int, int], None]


class ConcurrentExtractor:
    def __init__(
        self,
        client: BaseLLMClient,
        *,
        system_prompt: str,
        max_concurrency: int = 3,
        max_attempts: int = 3,
        base_delay: float = 2.0,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        self.client = client
        self.system_prompt = system_prompt
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.on_progress = on_progress
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def extract_all(
        self,
        tasks: list[ExtractionTask],
    ) -> tuple[list[ExtractionResult], ExtractionStats]:
        stats = ExtractionStats(total=len(tasks))
        completed = 0

        async def run_one(index: int, task: ExtractionTask) -> ExtractionResult:
            nonlocal completed
            result = await self._extract_one(index, task)
            completed += 1
            if self.on_progress is not None:
                self.on_progress(completed, len(tasks))
            return result

        results = await asyncio.gather(
            *(run_one(index, task) for index, task in enumerate(tasks))
        )
        results.sort(key=lambda item: item.index)

        for result in results:
            stats.retries += result.retries
            if result.error is None:
                stats.succeeded += 1
                stats.total_latency_ms += result.latency_ms
            else:
                stats.failed += 1

        return results, stats

    async def _extract_one(self, index: int, task: ExtractionTask) -> ExtractionResult:
        delay = self.base_delay
        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                async with self._semaphore:
                    started = time.monotonic()
                    response = await self.client.complete(
                        system=self.system_prompt,
                        user=task.user_prompt,
                    )
                    latency_ms = (time.monotonic() - started) * 1000
                return ExtractionResult(
                    index=index,
                    source=task.source,
                    raw_response=response,
                    latency_ms=latency_ms,
                    retries=attempt - 1,
                )
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_attempts:
                    break
                await asyncio.sleep(delay)
                delay *= 2

        return ExtractionResult(
            index=index,
            source=task.source,
            error=str(last_error) if last_error is not None else "unknown error",
            retries=self.max_attempts - 1,
        )
