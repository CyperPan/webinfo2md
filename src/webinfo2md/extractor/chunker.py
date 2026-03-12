from __future__ import annotations

import re

from webinfo2md.utils.token_counter import estimate_tokens


class TextChunker:
    def __init__(self, max_tokens: int = 6000) -> None:
        self.max_tokens = max_tokens

    def chunk(self, text: str, max_tokens: int | None = None) -> list[str]:
        limit = max_tokens or self.max_tokens
        if estimate_tokens(text) <= limit:
            return [text.strip()] if text.strip() else []

        sections = self._split_by_heading(text)
        chunks: list[str] = []
        for section in sections:
            chunks.extend(self._chunk_section(section, limit))
        return [chunk for chunk in chunks if chunk.strip()]

    def _split_by_heading(self, text: str) -> list[str]:
        stripped = text.strip()
        if not stripped:
            return []
        parts = re.split(r"(?m)(?=^#{1,6}\s+)", stripped)
        return [part.strip() for part in parts if part.strip()]

    def _chunk_section(self, section: str, limit: int) -> list[str]:
        if estimate_tokens(section) <= limit:
            return [section.strip()]

        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", section) if part.strip()]
        return self._pack_units(paragraphs, limit)

    def _pack_units(self, units: list[str], limit: int) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0

        for unit in units:
            unit_tokens = estimate_tokens(unit)
            if unit_tokens > limit:
                for sentence in self._split_long_unit(unit, limit):
                    sentence_tokens = estimate_tokens(sentence)
                    if current and current_tokens + sentence_tokens > limit:
                        chunks.append("\n\n".join(current))
                        current = []
                        current_tokens = 0
                    current.append(sentence)
                    current_tokens += sentence_tokens
                continue

            if current and current_tokens + unit_tokens > limit:
                chunks.append("\n\n".join(current))
                current = []
                current_tokens = 0
            current.append(unit)
            current_tokens += unit_tokens

        if current:
            chunks.append("\n\n".join(current))
        return chunks

    def _split_long_unit(self, unit: str, limit: int) -> list[str]:
        parts = re.split(r"(?<=[。！？.!?])\s+", unit)
        if len(parts) == 1:
            return self._split_by_length(unit, limit)
        return self._pack_units([part.strip() for part in parts if part.strip()], limit)

    def _split_by_length(self, text: str, limit: int) -> list[str]:
        approx_chars = max(1, limit * 4)
        return [
            text[index : index + approx_chars].strip()
            for index in range(0, len(text), approx_chars)
            if text[index : index + approx_chars].strip()
        ]
