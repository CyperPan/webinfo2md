from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
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
    source_urls: list[str] = field(default_factory=list)


class MarkdownWriter:
    def write(
        self,
        content: str,
        output_path: str | Path,
        metadata: DocumentMetadata | None = None,
    ) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        final_content = self._post_process(content.strip())
        has_h1 = re.match(r"^#\s+\S", final_content) is not None
        if metadata and not has_h1:
            title = self._build_title(metadata)
            header = self._build_header(title, metadata)
            final_content = "\n".join(header) + "\n\n" + final_content

        path.write_text(final_content + "\n", encoding="utf-8")
        return path

    def _build_header(self, title: str, metadata: DocumentMetadata) -> list[str]:
        header = [
            f"# {title}",
            "",
        ]
        source_urls = metadata.source_urls or [metadata.source_url]
        info_lines = []
        if len(source_urls) == 1:
            info_lines.append(f"| 来源 | {source_urls[0]} |")
        else:
            info_lines.append(f"| 来源网页数 | {len(source_urls)} |")
        info_lines.append(
            f"| 整理时间 | {metadata.generated_at.strftime('%Y-%m-%d %H:%M')} |"
        )
        if metadata.company:
            info_lines.append(f"| 公司 | {metadata.company} |")
        if metadata.position:
            info_lines.append(f"| 岗位 | {metadata.position} |")
        if metadata.question_count is not None:
            info_lines.append(f"| 问题总数 | {metadata.question_count} |")

        header.append("| 属性 | 信息 |")
        header.append("|------|------|")
        header.extend(info_lines)

        if len(source_urls) > 1:
            header.append("")
            header.append("<details><summary>来源网页列表</summary>")
            header.append("")
            for i, url in enumerate(source_urls, 1):
                header.append(f"{i}. {url}")
            header.append("")
            header.append("</details>")

        header.append("")
        header.append("---")
        return header

    def _post_process(self, content: str) -> str:
        """Clean up LLM output for better readability."""
        # Remove markdown code fences wrapping the whole content
        fence_match = re.match(
            r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", content, re.DOTALL
        )
        if fence_match:
            content = fence_match.group(1).strip()

        # Ensure consistent heading spacing
        content = re.sub(r"\n{3,}", "\n\n", content)

        # Ensure there's a blank line before headings
        content = re.sub(r"([^\n])\n(#{1,6}\s)", r"\1\n\n\2", content)

        return content

    def _build_title(self, metadata: DocumentMetadata) -> str:
        if metadata.company and metadata.position:
            return f"{metadata.company} - {metadata.position} 面试整理"
        if metadata.company:
            return f"{metadata.company} 面试整理"
        if len(metadata.source_urls) > 1:
            return "多网页信息整理"
        return metadata.source_title or "网页信息整理"
