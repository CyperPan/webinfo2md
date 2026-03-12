"""Main pipeline: crawl → clean → concurrent extract → organize → write MD.

This is the updated pipeline that uses ConcurrentExtractor for parallel
LLM calls across text chunks, with progress reporting.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """All parameters needed to run the pipeline."""

    url: str
    api_key: str
    provider: str = "openai"
    model: str = ""
    prompt: str = ""
    output: str = "output.md"
    depth: int = 0
    max_pages: int = 5
    chunk_size: int = 6000
    template: str = "interview-general"
    verbose: bool = False

    # --- P2 additions ---
    max_concurrency: int = 3
    force_playwright: bool = False
    playwright_config: Optional[dict[str, Any]] = None

    # --- dry-run ---
    dry_run: bool = False


def _progress_printer(completed: int, total: int, preview: Optional[str]) -> None:
    """CLI progress callback."""
    bar_len = 30
    filled = int(bar_len * completed / total)
    bar = "█" * filled + "░" * (bar_len - filled)
    pct = 100 * completed / total
    sys.stdout.write(f"\r  [{bar}] {completed}/{total} ({pct:.0f}%)")
    if completed == total:
        sys.stdout.write("\n")
    sys.stdout.flush()


async def run_pipeline(config: PipelineConfig) -> str:
    """Execute the full webinfo2md pipeline.

    Returns the output file path.
    """
    from webinfo2md.crawler.factory import smart_fetch
    from webinfo2md.extractor.cleaner import ContentCleaner
    from webinfo2md.extractor.chunker import TextChunker
    from webinfo2md.llm.factory import create_client
    from webinfo2md.llm.concurrent import (
        ConcurrentExtractor,
        merge_extracted_questions,
    )
    from webinfo2md.prompts.templates import get_extract_prompt, get_organize_prompt
    from webinfo2md.writer.md_writer import MarkdownWriter

    t_start = time.monotonic()

    # ── Step 1: Crawl ──────────────────────────────────────────────
    print(f"🕷️  Crawling: {config.url}")
    pages = []
    urls_to_crawl = [config.url]

    for i, url in enumerate(urls_to_crawl):
        if i >= config.max_pages:
            break
        try:
            result = await smart_fetch(
                url,
                force_playwright=config.force_playwright,
                playwright_config=config.playwright_config,
            )
            pages.append(result)
            print(
                f"  ✓ [{result.engine}] {result.title or url} "
                f"({len(result.text_content)} chars)"
            )

            # Collect child links for depth > 0
            if config.depth > 0 and i == 0:
                for link in result.links[: config.max_pages * 3]:
                    if link not in urls_to_crawl and link.startswith("http"):
                        urls_to_crawl.append(link)
        except Exception as e:
            print(f"  ✗ Failed: {url} — {e}")

    if not pages:
        raise RuntimeError("No pages successfully crawled")

    # ── Step 2: Clean & Chunk ──────────────────────────────────────
    print("🧹 Cleaning and chunking content...")
    cleaner = ContentCleaner()
    chunker = TextChunker(max_tokens=config.chunk_size)

    all_chunks: list[str] = []
    for page in pages:
        clean_text = cleaner.clean(page.raw_html)
        chunks = chunker.chunk(clean_text)
        all_chunks.extend(chunks)

    print(f"  → {len(pages)} page(s), {len(all_chunks)} chunk(s)")

    # Token estimate
    total_chars = sum(len(c) for c in all_chunks)
    est_tokens = total_chars // 4  # rough estimate
    print(f"  → ~{est_tokens:,} input tokens estimated")

    # ── Dry-run exit ───────────────────────────────────────────────
    if config.dry_run:
        print("\n🏁 Dry-run complete. No LLM calls made.")
        print(f"   Pages: {len(pages)}")
        print(f"   Chunks: {len(all_chunks)}")
        print(f"   Est. tokens: ~{est_tokens:,}")
        return ""

    # ── Step 3: Concurrent LLM Extraction ──────────────────────────
    print(f"🤖 Extracting questions ({config.max_concurrency} concurrent)...")
    llm = create_client(config.provider, config.api_key, config.model)
    extract_prompt = get_extract_prompt()

    extractor = ConcurrentExtractor(
        client=llm,
        max_concurrency=config.max_concurrency,
        on_progress=_progress_printer,
    )
    results, stats = await extractor.extract_all(all_chunks, extract_prompt)

    print(
        f"  → {stats.succeeded} succeeded, {stats.failed} failed, "
        f"avg {stats.avg_latency_ms:.0f}ms, {stats.retries} retries"
    )

    # ── Step 4: Merge & Dedup ──────────────────────────────────────
    print("🔗 Merging and deduplicating...")
    merged = merge_extracted_questions(results)
    q_count = len(merged["questions"])
    cat_count = len(merged["categories"])
    print(f"  → {q_count} unique questions in {cat_count} categories")

    if q_count == 0:
        print("⚠️  No questions extracted. Check the URL and content.")
        return ""

    # ── Step 5: LLM Organization ───────────────────────────────────
    print("📝 Organizing into structured format...")
    organize_prompt = get_organize_prompt(config.prompt)
    organized_md = await llm.complete(
        organize_prompt,
        json.dumps(merged, ensure_ascii=False),
    )

    # ── Step 6: Write Markdown ─────────────────────────────────────
    writer = MarkdownWriter()
    output_path = writer.write(
        content=organized_md,
        output_path=config.output,
        metadata={
            "url": config.url,
            "pages": len(pages),
            "questions": q_count,
            "categories": merged["categories"],
            "engine": pages[0].engine if pages else "unknown",
        },
    )

    elapsed = time.monotonic() - t_start
    print(f"\n✅ Done in {elapsed:.1f}s → {output_path}")
    return output_path
