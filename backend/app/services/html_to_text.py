"""HTML → readable text extraction using only the standard library.

Removes scripts, styles, navigation chrome, and unrelated elements, then
keeps block-level content (paragraphs, headings, list items, quotes).
No JavaScript is ever executed.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# Elements whose entire subtree is dropped.
_SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "iframe",
    "object",
    "embed",
    "canvas",
    "form",
    "nav",
    "footer",
    "aside",
    "header",
    "button",
    "select",
    "option",
}

# Block elements that produce paragraph breaks.
_BLOCK_TAGS = {
    "p",
    "div",
    "section",
    "article",
    "main",
    "blockquote",
    "pre",
    "li",
    "ul",
    "ol",
    "table",
    "tr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "br",
    "hr",
    "figure",
    "figcaption",
    "dt",
    "dd",
}

# Tags whose text content is boilerplate even inside <body>.
_META_TEXT_TAGS = {"title"}

_TITLE_ATTR_TAGS = {"img", "figure", "a"}

_WS_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._blocks: list[str] = []
        self._current: list[str] = []
        self.title: str = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag in _META_TEXT_TAGS:
            self._in_title = True
            return
        if tag in _BLOCK_TAGS:
            self._flush()
        if tag == "img":
            alt = dict(attrs).get("alt")
            if alt and alt.strip():
                self._current.append(f"[image: {alt.strip()}]")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if tag in _META_TEXT_TAGS:
            self._in_title = False
            return
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_title:
            self.title += data
            return
        self._current.append(data)

    def _flush(self) -> None:
        if self._current:
            self._blocks.append("".join(self._current))
            self._current = []

    def close(self) -> None:  # type: ignore[override]
        super().close()
        self._flush()

    @property
    def blocks(self) -> list[str]:
        return self._blocks


def html_to_text(html: str, *, max_chars: int = 12_000) -> tuple[str, str]:
    """Extract readable text and the page title from HTML.

    Returns (text, title). Truncates to `max_chars` on a paragraph boundary
    with an explicit truncation marker.
    """
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # Malformed HTML: keep whatever was parsed before the error.
        pass

    title = " ".join(parser.title.split())[:300]

    parts: list[str] = []
    for block in parser.blocks:
        text = _WS_RE.sub(" ", block).strip()
        if text:
            parts.append(text)

    joined = "\n\n".join(parts)
    joined = _MULTI_NL_RE.sub("\n\n", joined).strip()

    if len(joined) > max_chars:
        truncated = joined[:max_chars]
        # Back off to the last paragraph boundary for a clean cut.
        last_break = truncated.rfind("\n\n")
        if last_break > max_chars // 2:
            truncated = truncated[:last_break]
        joined = truncated + "\n\n[Extracted text truncated at the configured limit.]"

    return joined, title
