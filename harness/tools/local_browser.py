from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urlparse


class LocalBrowserError(RuntimeError):
    """Raised when the local browser action cannot be completed safely."""


@dataclass(slots=True)
class LocalBrowserResult:
    action: str
    ok: bool
    url: str
    opened: bool
    message: str
    meta: dict[str, str] = field(default_factory=dict)

    def render(self) -> str:
        rows = [
            f"action={self.action}",
            f"ok={'true' if self.ok else 'false'}",
            f"opened={'true' if self.opened else 'false'}",
            f"url={self.url}",
            f"message={self.message}",
        ]
        for key in sorted(self.meta):
            rows.append(f"{key}={self.meta[key]}")
        return "\n".join(rows)


@dataclass(slots=True)
class LocalBrowserClient:
    enabled: bool = True
    search_engine_template: str = "https://www.bing.com/search?q={query}"
    allowed_domains: tuple[str, ...] = ()

    def search(self, query: str, *, open_result: bool = False) -> str:
        normalized_query = str(query).strip()
        if not normalized_query:
            raise LocalBrowserError("Search query cannot be empty.")

        template = self.search_engine_template.strip()
        if "{query}" not in template:
            raise LocalBrowserError("Browser search engine template must contain '{query}'.")

        encoded_query = quote_plus(normalized_query)
        url = template.format(query=encoded_query)
        self._validate_http_url(url)
        result = self.open_url(
            url,
            action="browser_search",
            meta={
                "query": normalized_query,
                "open_result": "true" if open_result else "false",
                "note": "open_result is reserved for future direct-result behavior; search results page was opened.",
            },
        )
        return result

    def open_url(self, url: str, *, action: str = "browser_open", meta: dict[str, str] | None = None) -> str:
        if not self.enabled:
            raise LocalBrowserError("Local browser actions are disabled by configuration.")

        normalized_url = str(url).strip()
        self._validate_http_url(normalized_url)
        self._launch_url(normalized_url)
        return LocalBrowserResult(
            action=action,
            ok=True,
            url=normalized_url,
            opened=True,
            message="Opened URL in the default local browser.",
            meta=meta or {},
        ).render()

    def _validate_http_url(self, url: str) -> None:
        if not url:
            raise LocalBrowserError("URL cannot be empty.")

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise LocalBrowserError("Only http and https URLs are allowed.")
        if not parsed.netloc:
            raise LocalBrowserError("URL must include a hostname.")

    def _launch_url(self, url: str) -> None:
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", url], check=True, capture_output=True, text=True)
                return
            if os.name == "nt":
                os.startfile(url)  # type: ignore[attr-defined]
                return
            subprocess.run(["xdg-open", url], check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise LocalBrowserError("Local browser launcher is unavailable on this system.") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip() or f"exit code {exc.returncode}"
            raise LocalBrowserError(f"Local browser launcher failed: {detail}") from exc
        except OSError as exc:
            raise LocalBrowserError(f"Failed to open the local browser: {exc}") from exc
