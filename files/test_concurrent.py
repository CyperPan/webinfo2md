"""Tests for ConcurrentExtractor and merge logic."""

from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock

from webinfo2md.llm.concurrent import (
    ConcurrentExtractor,
    ExtractionResult,
    ExtractionStats,
    merge_extracted_questions,
    _safe_parse_json,
)


# ── Helpers ────────────────────────────────────────────────────────


def _make_mock_client(responses: list[str], fail_indices: set[int] | None = None):
    """Create a mock LLM client that returns canned responses.

    Args:
        responses: List of response strings, one per chunk.
        fail_indices: Set of chunk indices that should raise on first attempt.
    """
    call_count: dict[int, int] = {}

    async def _complete(system: str, user: str) -> str:
        # Figure out chunk index from call order
        idx = len(call_count)
        for i in range(len(responses)):
            if i not in call_count:
                idx = i
                break
        call_count.setdefault(idx, 0)
        call_count[idx] += 1

        if fail_indices and idx in fail_indices and call_count[idx] == 1:
            raise RuntimeError(f"Transient error on chunk {idx}")

        return responses[idx]

    client = AsyncMock()
    client.complete = _complete
    return client


# ── Tests: _safe_parse_json ────────────────────────────────────────


class TestSafeParseJson:
    def test_plain_json(self):
        result = _safe_parse_json('{"questions": []}')
        assert result == {"questions": []}

    def test_json_in_markdown_fence(self):
        text = '```json\n{"questions": [{"q": "test"}]}\n```'
        result = _safe_parse_json(text)
        assert result == {"questions": [{"q": "test"}]}

    def test_invalid_json(self):
        assert _safe_parse_json("not json at all") is None

    def test_list_json(self):
        result = _safe_parse_json('[1, 2, 3]')
        assert result == [1, 2, 3]


# ── Tests: ConcurrentExtractor ────────────────────────────────────


class TestConcurrentExtractor:
    def test_basic_extraction(self):
        """All chunks succeed."""
        responses = [
            json.dumps({"questions": [{"question": "What is X?", "category": "ML"}]}),
            json.dumps({"questions": [{"question": "What is Y?", "category": "Sys"}]}),
        ]
        client = _make_mock_client(responses)
        extractor = ConcurrentExtractor(client, max_concurrency=2)

        results, stats = asyncio.get_event_loop().run_until_complete(
            extractor.extract_all(["chunk 0", "chunk 1"], "system prompt")
        )

        assert len(results) == 2
        assert stats.succeeded == 2
        assert stats.failed == 0
        assert results[0].chunk_index == 0
        assert results[1].chunk_index == 1
        assert results[0].parsed is not None
        assert results[1].parsed is not None

    def test_progress_callback(self):
        """Progress callback is called for each chunk."""
        responses = [json.dumps({"questions": []}) for _ in range(3)]
        client = _make_mock_client(responses)

        progress_calls = []
        def on_progress(completed, total, preview):
            progress_calls.append((completed, total))

        extractor = ConcurrentExtractor(
            client, max_concurrency=1, on_progress=on_progress
        )
        asyncio.get_event_loop().run_until_complete(
            extractor.extract_all(["a", "b", "c"], "sys")
        )

        assert len(progress_calls) == 3
        assert progress_calls[-1] == (3, 3)

    def test_semaphore_limits_concurrency(self):
        """Verify semaphore prevents all tasks from running at once."""
        max_concurrent = 0
        current_concurrent = 0

        original_responses = [
            json.dumps({"questions": []}) for _ in range(5)
        ]

        async def _tracked_complete(system, user):
            nonlocal max_concurrent, current_concurrent
            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.05)
            current_concurrent -= 1
            return json.dumps({"questions": []})

        client = AsyncMock()
        client.complete = _tracked_complete

        extractor = ConcurrentExtractor(client, max_concurrency=2)
        asyncio.get_event_loop().run_until_complete(
            extractor.extract_all(
                ["c0", "c1", "c2", "c3", "c4"], "sys"
            )
        )

        assert max_concurrent <= 2

    def test_empty_chunks(self):
        """Empty chunk list returns empty results."""
        client = _make_mock_client([])
        extractor = ConcurrentExtractor(client)
        results, stats = asyncio.get_event_loop().run_until_complete(
            extractor.extract_all([], "sys")
        )
        assert results == []
        assert stats.total_chunks == 0


# ── Tests: merge_extracted_questions ───────────────────────────────


class TestMergeExtractedQuestions:
    def test_basic_merge(self):
        results = [
            ExtractionResult(
                chunk_index=0,
                raw_response="",
                parsed={"questions": [
                    {"question": "What is attention?", "category": "ML"},
                    {"question": "Explain backprop", "category": "ML"},
                ]},
            ),
            ExtractionResult(
                chunk_index=1,
                raw_response="",
                parsed={"questions": [
                    {"question": "What is TCP?", "category": "Network"},
                ]},
            ),
        ]

        merged = merge_extracted_questions(results)
        assert len(merged["questions"]) == 3
        assert set(merged["categories"]) == {"ML", "Network"}
        assert merged["source_chunks"] == 2
        assert merged["failed_chunks"] == 0

    def test_deduplication(self):
        results = [
            ExtractionResult(
                chunk_index=0,
                raw_response="",
                parsed={"questions": [
                    {"question": "What is attention?", "category": "ML"},
                ]},
            ),
            ExtractionResult(
                chunk_index=1,
                raw_response="",
                parsed={"questions": [
                    {"question": "what is attention", "category": "ML"},  # duplicate
                    {"question": "What is attention?", "category": "DL"},  # also dup
                ]},
            ),
        ]

        merged = merge_extracted_questions(results)
        assert len(merged["questions"]) == 1  # deduped

    def test_handles_failures(self):
        results = [
            ExtractionResult(
                chunk_index=0,
                raw_response="",
                parsed={"questions": [
                    {"question": "Q1", "category": "A"},
                ]},
            ),
            ExtractionResult(
                chunk_index=1,
                raw_response="",
                error="API timeout",
            ),
        ]

        merged = merge_extracted_questions(results)
        assert len(merged["questions"]) == 1
        assert merged["failed_chunks"] == 1

    def test_handles_bare_list(self):
        """Some LLMs return a bare list instead of {"questions": [...]}."""
        results = [
            ExtractionResult(
                chunk_index=0,
                raw_response="",
                parsed=[
                    {"question": "Q1", "category": "A"},
                    {"question": "Q2", "category": "B"},
                ],
            ),
        ]

        merged = merge_extracted_questions(results)
        assert len(merged["questions"]) == 2
