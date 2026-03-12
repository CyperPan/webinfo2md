from __future__ import annotations

import asyncio
import json

from webinfo2md.llm.concurrent import ConcurrentExtractor, ExtractionTask


class FakeLLMClient:
    def __init__(self, *, delay: float = 0.01) -> None:
        self.delay = delay
        self.active = 0
        self.max_active = 0

    async def complete(self, system: str, user: str) -> str:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(self.delay)
        self.active -= 1
        return json.dumps({"prompt": user})


def test_concurrent_extractor_preserves_order_and_limit():
    client = FakeLLMClient()
    extractor = ConcurrentExtractor(
        client,
        system_prompt="extract",
        max_concurrency=2,
    )
    tasks = [
        ExtractionTask(source="page-1", user_prompt="chunk-1"),
        ExtractionTask(source="page-2", user_prompt="chunk-2"),
        ExtractionTask(source="page-3", user_prompt="chunk-3"),
    ]

    results, stats = asyncio.run(extractor.extract_all(tasks))

    assert [item.index for item in results] == [0, 1, 2]
    assert [item.source for item in results] == ["page-1", "page-2", "page-3"]
    assert stats.succeeded == 3
    assert stats.failed == 0
    assert client.max_active <= 2


def test_concurrent_extractor_progress_callback():
    progress: list[tuple[int, int]] = []
    extractor = ConcurrentExtractor(
        FakeLLMClient(),
        system_prompt="extract",
        max_concurrency=1,
        on_progress=lambda done, total: progress.append((done, total)),
    )

    asyncio.run(
        extractor.extract_all(
            [
                ExtractionTask(source="page-1", user_prompt="a"),
                ExtractionTask(source="page-2", user_prompt="b"),
            ]
        )
    )

    assert progress == [(1, 2), (2, 2)]
