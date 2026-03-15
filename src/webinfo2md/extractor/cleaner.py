from __future__ import annotations

import re

from bs4 import BeautifulSoup


class ContentCleaner:
    """Extract and clean main content from HTML pages."""

    # Minimum character threshold for readability output to be considered useful
    _MIN_READABILITY_LENGTH = 200

    def clean(self, html: str) -> str:
        cleaned_html = self._remove_noise(html)
        main_html = self._extract_main_content(cleaned_html)

        # If readability returned too little, try content-area selectors
        if len(self._strip_tags(main_html)) < self._MIN_READABILITY_LENGTH:
            selector_html = self._extract_by_selectors(cleaned_html)
            if selector_html:
                main_html = selector_html
            else:
                # Last resort: use the noise-removed HTML directly
                main_html = cleaned_html

        markdown = self._to_markdown(main_html)
        return self._normalize_whitespace(markdown)

    def _remove_noise(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag_name in (
            "script", "style", "nav", "footer", "aside", "noscript",
            "iframe", "header", "svg",
        ):
            for tag in soup.find_all(tag_name):
                tag.decompose()
        # Remove common noise by class/id patterns
        noise_patterns = [
            "sidebar", "breadcrumb", "pagination", "cookie", "banner",
            "advertisement", "ad-", "popup", "modal", "overlay",
        ]
        # Collect elements to remove first to avoid mutation during iteration
        to_remove = []
        for el in soup.find_all(True):
            if el.attrs is None:
                continue
            cls = el.get("class")
            if cls:
                classes = " ".join(cls) if isinstance(cls, list) else str(cls)
                if any(p in classes.lower() for p in noise_patterns):
                    to_remove.append(el)
                    continue
            el_id = el.get("id")
            if el_id and any(p in el_id.lower() for p in noise_patterns):
                to_remove.append(el)
        for el in to_remove:
            el.decompose()
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

    def _extract_by_selectors(self, html: str) -> str | None:
        """Try common content-area selectors when readability fails."""
        soup = BeautifulSoup(html, "html.parser")
        # Prioritized list of selectors for main content areas
        selectors = [
            "main",
            "article",
            "[role='main']",
            "#content",
            ".content",
            "#main-content",
            ".main-content",
            ".post-content",
            ".thread-content",
            ".forum-content",
            "#ct",           # Discuz forums
            "#postlist",     # Discuz forums
            ".bm_c",         # Discuz forums
        ]
        for selector in selectors:
            el = soup.select_one(selector)
            if el and len(el.get_text(strip=True)) >= self._MIN_READABILITY_LENGTH:
                return str(el)
        return None

    def _to_markdown(self, html: str) -> str:
        try:
            from markdownify import markdownify
        except ImportError:
            soup = BeautifulSoup(html, "html.parser")
            return soup.get_text("\n", strip=True)
        return markdownify(html, heading_style="ATX")

    @staticmethod
    def _strip_tags(html: str) -> str:
        """Quick text extraction for length checking."""
        return BeautifulSoup(html, "html.parser").get_text(strip=True)

    def _normalize_whitespace(self, text: str) -> str:
        text = text.replace("\r\n", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()
