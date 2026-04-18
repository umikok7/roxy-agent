from __future__ import annotations

from harness.client import HarnessClient
from harness.models.types import AgentRunResult


class ChatService:
    def __init__(self, client: HarnessClient | None = None) -> None:
        self._client = client or HarnessClient()

    async def run_chat(self, message: str, model: str | None = None) -> AgentRunResult:
        return await self._client.run_async(message, model)

    def list_models(self) -> list[dict[str, object]]:
        return self._client.list_models()


_service: ChatService | None = None


def get_chat_service() -> ChatService:
    global _service
    if _service is None:
        _service = ChatService()
    return _service
