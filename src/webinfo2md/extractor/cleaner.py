from __future__ import annotations

import re

from bs4 import BeautifulSoup


class ContentCleaner:
    def clean(self, html: str) -> str:
        cleaned_html = self._remove_noise(html)
        main_html = self._extract_main_content(cleaned_html)
        markdown = self._to_markdown(main_html)
        return self._normalize_whitespace(markdown)

    def _remove_noise(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag_name in ("script", "style", "nav", "footer", "aside", "noscript", "iframe"):
            for tag in soup.find_all(tag_name):
                tag.decompose()
        return str(soup)

    def _extract_main_content(self, html: str) -> str:
        try:
            from readability import Document
        except ImportError:
            return html
        try:
            document = Document(html)
            return document.summary()
        except Exception:
            return html

    def _to_markdown(self, html: str) -> str:
        try:
            from markdownify import markdownify
        except ImportError:
            soup = BeautifulSoup(html, "html.parser")
            return soup.get_text("\n", strip=True)
        return markdownify(html, heading_style="ATX")

    def _normalize_whitespace(self, text: str) -> str:
        text = text.replace("\r\n", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()
