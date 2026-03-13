from __future__ import annotations

from webinfo2md.llm.base import BaseLLMClient


class AnthropicClient(BaseLLMClient):
    def __init__(self, *, api_key: str, model: str) -> None:
        super().__init__(api_key=api_key, model=model)
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - dependency error
            raise RuntimeError("anthropic package is required for AnthropicClient") from exc
        self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def complete(self, system: str, user: str) -> str:
        client = self._get_client()
        response = await client.messages.create(
            model=self.model,
            system=system,
            max_tokens=16384,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
