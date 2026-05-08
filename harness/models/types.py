from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from harness.rag.service import KnowledgeBaseService


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
class SubagentMessage:
    role: str
    content: str


@dataclass(slots=True)
class SubagentEvent:
    task_id: str
    type: Literal["task_started", "task_running", "task_completed", "task_failed", "task_timed_out"]
    description: str | None = None
    subagent_type: str | None = None
    message: str | None = None
    result: str | None = None
    error: str | None = None


@dataclass(slots=True)
class AgentEvent:
    type: Literal[
        "start",
        "delta",
        "task_started",
        "task_running",
        "task_completed",
        "task_failed",
        "task_timed_out",
        "done",
        "error",
    ]
    delta: str | None = None
    text: str | None = None
    error: str | None = None
    trace: dict[str, int] | None = None
    thread_id: str | None = None
    task_id: str | None = None
    description: str | None = None
    subagent_type: str | None = None
    message: str | None = None
    result: str | None = None


@dataclass(slots=True)
class AgentTrace:
    steps: int = 0
    tool_calls: int = 0
    errors: int = 0
    subagent_calls: int = 0
    subagent_errors: int = 0


@dataclass(slots=True)
class AgentRunResult:
    text: str
    trace: AgentTrace = field(default_factory=AgentTrace)


@dataclass(slots=True)
class RuntimeContext:
    thread_id: str | None = None
    thread_root: Path | None = None
    workspace_dir: Path | None = None
    model_name: str | None = None
    subagent_depth: int = 0
    max_subagents: int = 3
    subagent_timeout_seconds: int = 900
    knowledge_base: KnowledgeBaseService | None = None


ConversationInput = list[dict[str, Any]]
