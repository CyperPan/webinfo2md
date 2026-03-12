from __future__ import annotations

from webinfo2md.llm.base import BaseLLMClient


class OpenAIClient(BaseLLMClient):
    def __init__(self, *, api_key: str, model: str, base_url: str | None = None) -> None:
        super().__init__(api_key=api_key, model=model)
        self.base_url = base_url
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - dependency error
            raise RuntimeError("openai package is required for OpenAIClient") from exc

        kwargs = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = AsyncOpenAI(**kwargs)
        return self._client

    async def complete(self, system: str, user: str) -> str:
        client = self._get_client()
        response = await client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                item.text for item in content if getattr(item, "type", None) == "text"
            )
        raise RuntimeError("OpenAI returned an unsupported content format")
