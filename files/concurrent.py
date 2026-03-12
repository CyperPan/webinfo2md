"""Concurrent LLM extraction with semaphore-based rate limiting.

Usage:
    extractor = ConcurrentExtractor(llm_client, max_concurrency=3)
    results = await extractor.extract_all(chunks, system_prompt)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Protocol matching BaseLLMClient.complete()."""

    async def complete(self, system: str, user: str) -> str: ...


@dataclass
class ExtractionResult:
    """Result of a single chunk extraction."""

    chunk_index: int
    raw_response: str
    parsed: Optional[dict | list] = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    retries: int = 0


@dataclass
class ExtractionStats:
    """Aggregate statistics for a batch extraction run."""

    total_chunks: int = 0
    succeeded: int = 0
    failed: int = 0
    total_latency_ms: float = 0.0
    retries: int = 0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(self.succeeded, 1)


ProgressCallback = Callable[[int, int, Optional[str]], None]
"""(completed, total, chunk_preview_or_none)"""


def _safe_parse_json(text: str) -> Optional[dict | list]:
    """Try to parse JSON from LLM response, handling markdown fences."""
    cleaned = text.strip()
    # Strip ```json ... ``` wrapping
    if cleaned.startswith("```"):
        first_nl = cleaned.index("\n") if "\n" in cleaned else 3
        cleaned = cleaned[first_nl + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


class ConcurrentExtractor:
    """Run LLM extraction across multiple text chunks concurrently.

    Features:
    - asyncio.Semaphore caps in-flight requests (protects rate limits)
    - Exponential backoff retry on transient failures
    - Progress callback for CLI feedback
    - Graceful partial-failure: collects all results, surfaces errors
    """

    def __init__(
        self,
        client: LLMClient,
        max_concurrency: int = 3,
        max_retries: int = 3,
        base_backoff: float = 2.0,
        on_progress: Optional[ProgressCallback] = None,
    ):
        self.client = client
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.on_progress = on_progress

    async def _extract_one(
        self, index: int, chunk: str, system_prompt: str
    ) -> ExtractionResult:
        """Extract from a single chunk with retry logic."""
        retries = 0
        last_error = ""

        for attempt in range(self.max_retries + 1):
            try:
                async with self.semaphore:
                    t0 = time.monotonic()
                    raw = await self.client.complete(system_prompt, chunk)
                    latency = (time.monotonic() - t0) * 1000

                parsed = _safe_parse_json(raw)
                return ExtractionResult(
                    chunk_index=index,
                    raw_response=raw,
                    parsed=parsed,
                    latency_ms=latency,
                    retries=retries,
                )
            except Exception as e:
                retries += 1
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    "Chunk %d attempt %d/%d failed: %s",
                    index,
                    attempt + 1,
                    self.max_retries + 1,
                    last_error,
                )
                if attempt < self.max_retries:
                    wait = self.base_backoff * (2**attempt)
                    await asyncio.sleep(wait)

        return ExtractionResult(
            chunk_index=index,
            raw_response="",
            error=last_error,
            retries=retries,
        )

    async def extract_all(
        self,
        chunks: list[str],
        system_prompt: str,
    ) -> tuple[list[ExtractionResult], ExtractionStats]:
        """Run extraction on all chunks concurrently.

        Returns:
            (results_sorted_by_index, aggregate_stats)
        """
        total = len(chunks)
        completed = 0
        stats = ExtractionStats(total_chunks=total)

        async def _task(i: int, chunk: str) -> ExtractionResult:
            nonlocal completed
            result = await self._extract_one(i, chunk, system_prompt)
            completed += 1
            if self.on_progress:
                preview = chunk[:60] + "..." if len(chunk) > 60 else chunk
                self.on_progress(completed, total, preview)
            return result

        tasks = [_task(i, c) for i, c in enumerate(chunks)]
        results = await asyncio.gather(*tasks)

        # Sort by original chunk order
        results = sorted(results, key=lambda r: r.chunk_index)

        for r in results:
            if r.error:
                stats.failed += 1
            else:
                stats.succeeded += 1
                stats.total_latency_ms += r.latency_ms
            stats.retries += r.retries

        return results, stats


def merge_extracted_questions(
    results: list[ExtractionResult],
) -> dict[str, Any]:
    """Merge and deduplicate questions from multiple extraction results.

    Expects each result.parsed to have a "questions" key with a list of dicts,
    each containing at least "question" and "category".

    Returns:
        {
            "questions": [...],        # deduplicated
            "source_chunks": int,
            "failed_chunks": int,
            "categories": [str, ...],
        }
    """
    seen_questions: set[str] = set()
    all_questions: list[dict] = []
    categories: set[str] = set()
    failed = 0

    for r in results:
        if r.error or r.parsed is None:
            failed += 1
            continue

        parsed = r.parsed
        # Handle both {"questions": [...]} and bare [...]
        questions = []
        if isinstance(parsed, dict):
            questions = parsed.get("questions", [])
        elif isinstance(parsed, list):
            questions = parsed

        for q in questions:
            if not isinstance(q, dict):
                continue
            text = q.get("question", "").strip()
            if not text:
                continue

            # Simple dedup by normalized text
            norm = text.lower().strip("?？。. ")
            if norm in seen_questions:
                continue
            seen_questions.add(norm)

            cat = q.get("category", "未分类")
            categories.add(cat)
            all_questions.append(q)

    return {
        "questions": all_questions,
        "source_chunks": len(results),
        "failed_chunks": failed,
        "categories": sorted(categories),
    }
