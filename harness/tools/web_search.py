from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse
from urllib.request import Request, urlopen


@dataclass(slots=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str = ""


class WebSearchError(RuntimeError):
    """Raised when web search fails."""


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self, *, max_results: int) -> None:
        super().__init__()
        self.max_results = max_results
        self.results: list[WebSearchResult] = []
        self._current_href: str | None = None
        self._current_title_parts: list[str] = []
        self._collect_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if len(self.results) >= self.max_results:
            return

        attr_map = dict(attrs)
        if tag == "a":
            class_name = attr_map.get("class", "")
            href = attr_map.get("href")
            if href and "result__a" in class_name:
                self._current_href = href
                self._current_title_parts = []
                self._collect_title = True

    def handle_data(self, data: str) -> None:
        if self._collect_title:
            text = data.strip()
            if text:
                self._current_title_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._collect_title or self._current_href is None:
            return

        title = " ".join(self._current_title_parts).strip()
        url = _extract_target_url(self._current_href)
        if title and url:
            self.results.append(WebSearchResult(title=title, url=url))

        self._current_href = None
        self._current_title_parts = []
        self._collect_title = False


def _extract_target_url(raw_href: str) -> str:
    parsed = urlparse(raw_href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        encoded_url = parse_qs(parsed.query).get("uddg", [""])[0]
        return encoded_url or raw_href
    return raw_href


class WebSearchClient:
    def __init__(self, *, timeout_seconds: int = 10) -> None:
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, *, max_results: int = 5) -> str:
        normalized_query = query.strip()
        if not normalized_query:
            raise WebSearchError("query cannot be empty")

        max_results = max(1, min(max_results, 10))
        request = Request(
            f"https://duckduckgo.com/html/?q={quote_plus(normalized_query)}",
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; MyDeerFlow/0.1; +https://github.com/bytedance/deer-flow)"
                )
            },
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                html = response.read().decode("utf-8", errors="ignore")
        except Exception as exc:  # pragma: no cover - depends on runtime network
            raise WebSearchError(f"web search request failed: {exc}") from exc

        parser = _DuckDuckGoHTMLParser(max_results=max_results)
        parser.feed(html)
        if not parser.results:
            return "No web results found."

        return self._format_results(normalized_query, parser.results)

    @staticmethod
    def _format_results(query: str, results: list[WebSearchResult]) -> str:
        lines = [f'Web search results for "{query}":']
        for index, item in enumerate(results, start=1):
            lines.append(f"{index}. {item.title}")
            lines.append(f"   URL: {item.url}")
            if item.snippet:
                lines.append(f"   Snippet: {item.snippet}")
        return "\n".join(lines)


__all__ = ["WebSearchClient", "WebSearchError", "WebSearchResult"]
