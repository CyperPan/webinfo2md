from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    def __init__(self, *, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def complete(self, system: str, user: str) -> str:
        raise NotImplementedError
