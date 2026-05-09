from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import APP.api.app as app_module
from APP.api.app import create_app
from APP.service.chat_service import ChatService
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

    async def run_async(self, prompt: str, model_name: str | None = None, **kwargs) -> AgentRunResult:
        return AgentRunResult(text=f"reply:{prompt}")

    def list_enabled_skill_names(self) -> list[str]:
        return ["example"]

    def list_models(self) -> list[dict[str, object]]:
        return []


def test_conversation_endpoints_work(tmp_path):
    service = ChatService(client=FakeHarnessClient(tmp_path / ".sandbox"))
    app_module._service = service
    client = TestClient(create_app())

    create_response = client.post("/conversations/create")
    assert create_response.status_code == 200
    created = create_response.json()
    thread_id = created["thread_id"]

    chat_response = client.post("/chat", json={"message": "hello", "thread_id": thread_id})
    assert chat_response.status_code == 200
    assert chat_response.json()["thread_id"] == thread_id

    list_response = client.get("/conversations")
    assert list_response.status_code == 200
    summaries = list_response.json()
    assert summaries[0]["thread_id"] == thread_id

    detail_response = client.get(f"/conversations/{thread_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["messages"][0]["content"] == "hello"

    rename_response = client.post(
        f"/conversations/{thread_id}/rename",
        json={"title": "Renamed"},
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["title"] == "Renamed"
