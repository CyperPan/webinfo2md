from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re


@dataclass(slots=True)
class DocumentMetadata:
    source_url: str
    source_title: str
    generated_at: datetime
    question_count: int | None = None
    company: str | None = None
    position: str | None = None


class MarkdownWriter:
    def write(
        self,
        content: str,
        output_path: str | Path,
        metadata: DocumentMetadata | None = None,
    ) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        final_content = content.strip()
        has_h1 = re.match(r"^#\s+\S", final_content) is not None
        if metadata and not has_h1:
            title = self._build_title(metadata)
            header = [
                f"# {title}",
                "",
                f"> 来源: {metadata.source_url}",
                f"> 整理时间: {metadata.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            ]
            if metadata.question_count is not None:
                header.append(f"> 问题总数: {metadata.question_count}")
            final_content = "\n".join(header) + "\n\n" + final_content

        path.write_text(final_content + "\n", encoding="utf-8")
        return path

    def _build_title(self, metadata: DocumentMetadata) -> str:
        if metadata.company and metadata.position:
            return f"{metadata.company} - {metadata.position} 面试整理"
        if metadata.company:
            return f"{metadata.company} 面试整理"
        return metadata.source_title or "网页信息整理"
