from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ToolResult:
    call_id: str
    output: str
    is_error: bool = False


@dataclass(slots=True)
class AgentTrace:
    steps: int = 0
    tool_calls: int = 0
    errors: int = 0


@dataclass(slots=True)
class AgentRunResult:
    text: str
    trace: AgentTrace = field(default_factory=AgentTrace)


ConversationInput = list[dict[str, Any]]
