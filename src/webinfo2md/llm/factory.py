from __future__ import annotations

from webinfo2md.llm.anthropic_client import AnthropicClient
from webinfo2md.llm.base import BaseLLMClient
from webinfo2md.llm.deepseek_client import DeepSeekClient
from webinfo2md.llm.openai_client import OpenAIClient
from webinfo2md.utils.config import default_model_for_provider


def create_client(provider: str, api_key: str, model: str | None = None) -> BaseLLMClient:
    resolved_model = model or default_model_for_provider(provider)
    clients: dict[str, type[BaseLLMClient]] = {
        "openai": OpenAIClient,
        "anthropic": AnthropicClient,
        "deepseek": DeepSeekClient,
    }
    if provider not in clients:
        raise ValueError(f"Unsupported provider: {provider}")
    return clients[provider](api_key=api_key, model=resolved_model)
