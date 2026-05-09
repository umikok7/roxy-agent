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
    subagent_calls: int = 0
    subagent_errors: int = 0


class ChatResponse(BaseModel):
    text: str
    trace: TraceInfo
    thread_id: str | None = None


class ConversationMessage(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class ConversationSummary(BaseModel):
    thread_id: str
    title: str
    created_at: str
    updated_at: str
    last_message_preview: str
    message_count: int


class ConversationDetail(ConversationSummary):
    messages: list[ConversationMessage]


class ConversationCreateResponse(ConversationSummary):
    pass


class ConversationRenameRequest(BaseModel):
    title: str


class ModelInfo(BaseModel):
    name: str
    display_name: str
    provider: str
    supports_vision: bool
    default: bool
