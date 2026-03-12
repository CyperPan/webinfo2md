from __future__ import annotations

from webinfo2md.llm.openai_client import OpenAIClient


class DeepSeekClient(OpenAIClient):
    def __init__(self, *, api_key: str, model: str) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url="https://api.deepseek.com/v1",
        )
