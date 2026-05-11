from __future__ import annotations

import pytest

from harness.tools.local_browser import LocalBrowserClient, LocalBrowserError


class RecordingBrowserClient(LocalBrowserClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.opened_urls: list[str] = []

    def _launch_url(self, url: str) -> None:
        self.opened_urls.append(url)


def test_browser_open_rejects_dangerous_schemes():
    client = RecordingBrowserClient()

    with pytest.raises(LocalBrowserError):
        client.open_url("javascript:alert(1)")

    with pytest.raises(LocalBrowserError):
        client.open_url("file:///tmp/demo.txt")


def test_browser_open_rejects_empty_url():
    client = RecordingBrowserClient()

    with pytest.raises(LocalBrowserError):
        client.open_url("  ")


def test_browser_search_encodes_query_and_opens_results_page():
    client = RecordingBrowserClient(search_engine_template="https://example.com/search?q={query}")

    output = client.search("洛琪希 roxy & magic", open_result=False)

    assert "action=browser_search" in output
    assert "ok=true" in output
    assert "opened=true" in output
    assert "url=https://example.com/search?q=%E6%B4%9B%E7%90%AA%E5%B8%8C+roxy+%26+magic" in output
    assert client.opened_urls == ["https://example.com/search?q=%E6%B4%9B%E7%90%AA%E5%B8%8C+roxy+%26+magic"]


def test_browser_search_requires_template_placeholder():
    client = RecordingBrowserClient(search_engine_template="https://example.com/search")

    with pytest.raises(LocalBrowserError):
        client.search("roxy")
