from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        raise NotImplementedError

    async def validate(self) -> bool:
        """Send a minimal request to verify the API key and model are valid."""
        try:
            response = await self.complete(
                system="Reply with exactly: ok",
                user="ping",
            )
            return bool(response and response.strip())
        except Exception:
            return False
