from __future__ import annotations

from pydantic import BaseModel


class HistoryMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    model: str | None = None
    thread_id: str | None = None
    messages: list[HistoryMessage] | None = None


class TraceInfo(BaseModel):
    steps: int
    tool_calls: int
    errors: int


class ChatResponse(BaseModel):
    text: str
    trace: TraceInfo


class ModelInfo(BaseModel):
    name: str
    display_name: str
    provider: str
    supports_vision: bool
    default: bool
