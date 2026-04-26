from __future__ import annotations

from types import SimpleNamespace

import pytest

from APP.service.chat_service import ChatService
from harness.context import normalize_thread_id
from harness.models.types import AgentRunResult


class FakeHarnessClient:
    def __init__(self, sandbox_root) -> None:
        self.config = SimpleNamespace(
            sandbox=SimpleNamespace(root_dir=sandbox_root),
            runtime=SimpleNamespace(
                max_recent_messages=8,
                compact_threshold_chars=5000,
                skill_memory_max=4,
            ),
        )
        self.calls: list[dict[str, object]] = []

    async def run_async(self, prompt: str, model_name: str | None = None, **kwargs) -> AgentRunResult:
        self.calls.append({"prompt": prompt, "model_name": model_name, **kwargs})
        return AgentRunResult(text=f"reply:{prompt}")

    def list_enabled_skill_names(self) -> list[str]:
        return ["example"]

    def list_models(self) -> list[dict[str, object]]:
        return []


@pytest.mark.asyncio
async def test_chat_service_routes_context_by_thread_id(tmp_path):
    client = FakeHarnessClient(tmp_path / ".sandbox")
    service = ChatService(client=client)

    result = await service.run_chat("hello", thread_id="thread-a")

    assert result.text == "reply:hello"
    assert client.calls[0]["thread_id"] == "thread-a"
    thread_context = tmp_path / ".sandbox" / "threads" / normalize_thread_id("thread-a") / "context.json"
    assert thread_context.exists()


@pytest.mark.asyncio
async def test_chat_service_isolates_context_between_threads(tmp_path):
    client = FakeHarnessClient(tmp_path / ".sandbox")
    service = ChatService(client=client)

    await service.run_chat("first", thread_id="thread-a")
    await service.run_chat("second", thread_id="thread-b")

    first_context = tmp_path / ".sandbox" / "threads" / normalize_thread_id("thread-a") / "context.json"
    second_context = tmp_path / ".sandbox" / "threads" / normalize_thread_id("thread-b") / "context.json"
    assert first_context.exists()
    assert second_context.exists()
    assert first_context.read_text(encoding="utf-8") != second_context.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_chat_service_does_not_create_legacy_runtime_context_dir(tmp_path):
    client = FakeHarnessClient(tmp_path / ".sandbox")
    service = ChatService(client=client)

    await service.run_chat("hello", thread_id="thread-a")

    assert not (tmp_path / ".runtime").exists()
