from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import patch

from webinfo2md.pipeline import PipelineRunResult, WebInfo2MDPipeline
from webinfo2md.utils.config import PipelineConfig

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "interview_post.html"
TEST_URL = "https://example.com/interview-post"


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url: str) -> FakeResponse:
        assert url == TEST_URL
        return FakeResponse(FIXTURE_PATH.read_text(encoding="utf-8"))


class FakeLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, system: str, user: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return """
            {
              "source": "Example Interview Post",
              "company": "字节跳动",
              "position": "LLM 训练推理工程师",
              "questions": [
                {
                  "category": "ML理论",
                  "question": "请详细解释 Multi-Head Attention 的计算过程",
                  "context": "一面",
                  "difficulty": "medium"
                }
              ]
            }
            """
        return """
        ## Transformer 架构

        ### Q1: 请详细解释 Multi-Head Attention 的计算过程

        **简短回答：**
        MHA 将输入映射到多个头并并行计算注意力，再拼接得到输出。
        """


def test_pipeline_end_to_end_with_mocked_http_and_llm(tmp_path):
    output = tmp_path / "interview.md"
    config = PipelineConfig(
        url=TEST_URL,
        api_key="test-key",
        provider="openai",
        model="gpt-4o-mini",
        output=output,
        min_content_length=10,
        crawl_delay_min=0.0,
        crawl_delay_max=0.0,
    )

    with patch("httpx.AsyncClient", FakeAsyncClient):
        with patch(
            "webinfo2md.crawler.httpx_crawler.HttpxCrawler._can_fetch",
            new=AsyncMock(return_value=True),
        ):
            with patch("webinfo2md.pipeline.create_client", return_value=FakeLLMClient()):
                result = asyncio.run(WebInfo2MDPipeline().run(config))

    assert isinstance(result, PipelineRunResult)
    assert result.dry_run is False
    assert result.output_path == str(output)
    assert output.exists()

    content = output.read_text(encoding="utf-8")
    assert content.startswith("# 字节跳动 - LLM 训练推理工程师 面试整理")
    assert "## Transformer 架构" in content
    assert "### Q1: 请详细解释 Multi-Head Attention 的计算过程" in content
