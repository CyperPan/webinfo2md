from __future__ import annotations

import asyncio
import json
import re
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urldefrag, urlparse

from webinfo2md.crawler.base import BaseCrawler, CrawlResult
from webinfo2md.crawler.factory import CrawlerFactory
from webinfo2md.extractor.chunker import TextChunker
from webinfo2md.extractor.cleaner import ContentCleaner
from webinfo2md.llm.concurrent import ConcurrentExtractor, ExtractionTask
from webinfo2md.llm.factory import create_client
from webinfo2md.prompts.templates import (
    EXTRACT_SYSTEM_TEMPLATE,
    EXTRACT_USER_TEMPLATE,
    get_template,
)
from webinfo2md.utils.config import PipelineConfig
from webinfo2md.utils.logger import get_console, get_logger
from webinfo2md.utils.token_counter import estimate_tokens
from webinfo2md.writer.md_writer import DocumentMetadata, MarkdownWriter


@dataclass(slots=True)
class PageChunk:
    url: str
    title: str
    content: str


@dataclass(slots=True)
class PipelineRunResult:
    url: str
    output_path: str | None
    dry_run: bool
    page_count: int
    chunk_count: int
    estimated_tokens: int
    question_count: int | None = None


class WebInfo2MDPipeline:
    def __init__(self) -> None:
        self.console = get_console()
        self.logger = get_logger(False)

    async def run(self, config: PipelineConfig) -> PipelineRunResult:
        self.logger = get_logger(config.verbose)
        self._emit("正在初始化爬虫...")
        crawler = await CrawlerFactory.create(
            config.url,
            headers=config.headers,
            cookies=config.cookies,
            timeout=config.timeout,
            crawl_delay_min=config.crawl_delay_min,
            crawl_delay_max=config.crawl_delay_max,
            verbose=config.verbose,
            min_content_length=config.min_content_length,
            force_playwright=config.force_playwright,
            playwright_config=config.playwright,
        )

        self._emit("正在爬取网页...")
        pages = await self._crawl_with_depth(crawler, config.url, config.depth, config.pages)
        if not pages:
            raise RuntimeError("No pages were crawled")

        self._emit("正在清洗与分块...")
        chunks = self._prepare_chunks(pages, config.chunk_size)
        if not chunks:
            raise RuntimeError("No usable content was extracted from the crawled pages")
        estimated_tokens = sum(estimate_tokens(chunk.content) for chunk in chunks)

        if config.dry_run:
            self._emit(
                "Dry run 完成: "
                f"pages={len(pages)} chunks={len(chunks)} estimated_tokens={estimated_tokens} "
                f"output={config.output}"
            )
            return PipelineRunResult(
                url=config.url,
                output_path=str(config.output),
                dry_run=True,
                page_count=len(pages),
                chunk_count=len(chunks),
                estimated_tokens=estimated_tokens,
            )

        self._emit("正在调用 LLM 进行结构化提取...")
        llm = create_client(config.provider, config.api_key or "", config.model)
        extractor = ConcurrentExtractor(
            llm,
            system_prompt=EXTRACT_SYSTEM_TEMPLATE,
            max_concurrency=config.max_concurrency,
            on_progress=self._emit_progress if config.verbose else None,
        )
        tasks = [
            ExtractionTask(
                source=chunk.title,
                user_prompt=EXTRACT_USER_TEMPLATE.format(
                    title=chunk.title,
                    url=chunk.url,
                    content=chunk.content,
                ),
            )
            for chunk in chunks
        ]
        results, stats = await extractor.extract_all(tasks)
        extracted = []
        for result in results:
            if result.error:
                self.logger.warning(
                    "Chunk extraction failed for %s: %s",
                    result.source,
                    result.error,
                )
                extracted.append(self._empty_extracted_payload(result.source))
                continue
            extracted.append(
                self._parse_json_response(result.raw_response, default_source=result.source)
            )
        self.logger.info(
            "Chunk extraction completed: total=%s succeeded=%s failed=%s retries=%s avg_latency_ms=%.1f",
            stats.total,
            stats.succeeded,
            stats.failed,
            stats.retries,
            stats.avg_latency_ms,
        )

        merged = self._merge_and_dedup(extracted)

        self._emit("正在生成 Markdown 文档...")
        final_system = get_template(config.template).format(
            custom_instructions=config.prompt or "请尽量保持精炼且适合复习。"
        )
        final_user = json.dumps(merged, ensure_ascii=False, indent=2)
        final_content = await self._safe_llm_call(llm, final_system, final_user)

        self._emit("正在写入输出文件...")
        writer = MarkdownWriter()
        metadata = DocumentMetadata(
            source_url=config.url,
            source_title=pages[0].title,
            generated_at=datetime.now(),
            question_count=len(merged.get("questions", [])),
            company=merged.get("company") or None,
            position=merged.get("position") or None,
        )
        output_path = writer.write(final_content, config.output, metadata=metadata)
        self._emit(f"完成，输出文件: {output_path}")
        return PipelineRunResult(
            url=config.url,
            output_path=str(output_path),
            dry_run=False,
            page_count=len(pages),
            chunk_count=len(chunks),
            estimated_tokens=estimated_tokens,
            question_count=len(merged.get("questions", [])),
        )

    async def _crawl_with_depth(
        self,
        crawler: BaseCrawler,
        start_url: str,
        depth: int,
        max_pages: int,
    ) -> list[CrawlResult]:
        results: list[CrawlResult] = []
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(self._normalize_url(start_url), 0)])
        start_host = urlparse(start_url).netloc

        while queue and len(results) < max_pages:
            url, current_depth = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            try:
                page = await crawler.fetch(url)
            except Exception as exc:
                self.logger.warning("Failed to crawl %s: %s", url, exc)
                continue
            results.append(page)
            if current_depth >= depth:
                continue

            for link in page.links:
                normalized = self._normalize_url(link)
                parsed = urlparse(normalized)
                if parsed.scheme not in {"http", "https"}:
                    continue
                if parsed.netloc != start_host:
                    continue
                if normalized not in visited:
                    queue.append((normalized, current_depth + 1))
        return results

    def _prepare_chunks(self, pages: list[CrawlResult], chunk_size: int) -> list[PageChunk]:
        cleaner = ContentCleaner()
        chunker = TextChunker(max_tokens=chunk_size)
        chunks: list[PageChunk] = []
        for page in pages:
            cleaned = cleaner.clean(page.raw_html)
            if not cleaned.strip():
                cleaned = page.text_content
            for part in chunker.chunk(cleaned):
                chunks.append(PageChunk(url=page.url, title=page.title, content=part))
        return chunks

    async def _safe_llm_call(self, client, system: str, user: str, max_attempts: int = 3) -> str:
        delay = 2.0
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await client.complete(system=system, user=user)
            except Exception as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break
                self.logger.warning("LLM call failed on attempt %s/%s: %s", attempt, max_attempts, exc)
                await asyncio.sleep(delay)
                delay *= 2
        raise RuntimeError(f"LLM call failed after {max_attempts} attempts") from last_error

    def _parse_json_response(self, raw: str, default_source: str) -> dict[str, Any]:
        candidates = [raw.strip()]
        fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
        if fence_match:
            candidates.insert(0, fence_match.group(1))
        brace_match = re.search(r"(\{.*\})", raw, re.DOTALL)
        if brace_match:
            candidates.append(brace_match.group(1))

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    parsed.setdefault("source", default_source)
                    parsed.setdefault("company", "")
                    parsed.setdefault("position", "")
                    parsed.setdefault("questions", [])
                    return parsed
            except json.JSONDecodeError:
                continue

        return self._empty_extracted_payload(default_source)

    def _empty_extracted_payload(self, default_source: str) -> dict[str, Any]:
        return {
            "source": default_source,
            "company": "",
            "position": "",
            "questions": [],
        }

    def _merge_and_dedup(self, extracted_payloads: list[dict[str, Any]]) -> dict[str, Any]:
        merged_questions: list[dict[str, Any]] = []
        seen: set[str] = set()
        company = ""
        position = ""
        source = ""

        for payload in extracted_payloads:
            source = source or payload.get("source", "")
            company = company or payload.get("company", "")
            position = position or payload.get("position", "")
            for question in payload.get("questions", []):
                normalized = self._normalize_question(question.get("question", ""))
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                merged_questions.append(
                    {
                        "category": question.get("category", "其他"),
                        "question": question.get("question", "").strip(),
                        "context": question.get("context", "").strip(),
                        "difficulty": question.get("difficulty", "medium"),
                    }
                )

        return {
            "source": source,
            "company": company,
            "position": position,
            "questions": merged_questions,
        }

    def _normalize_question(self, question: str) -> str:
        return re.sub(r"\s+", "", question.strip().lower())

    def _normalize_url(self, url: str) -> str:
        cleaned, _ = urldefrag(url)
        return cleaned.rstrip("/")

    def _emit(self, message: str) -> None:
        if self.console is not None:
            self.console.print(message)
        else:  # pragma: no cover - fallback path
            print(message)

    def _emit_progress(self, completed: int, total: int) -> None:
        self._emit(f"结构化提取进度: {completed}/{total}")
