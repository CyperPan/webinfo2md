from __future__ import annotations

from webinfo2md.llm.openai_client import OpenAIClient


class GeminiClient(OpenAIClient):
    def __init__(self, *, api_key: str, model: str) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
