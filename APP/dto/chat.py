from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    model: str | None = None


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
