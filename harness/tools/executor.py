from __future__ import annotations

from harness.models.types import ToolCall, ToolResult
from harness.tools.registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    async def execute_tool_call(self, tool_call: ToolCall) -> ToolResult:
        handler = self.registry.get_handler(tool_call.name)
        if handler is None:
            return ToolResult(
                call_id=tool_call.id,
                output=f"Unknown tool: {tool_call.name}",
                is_error=True,
            )

        try:
            output = await handler(tool_call.arguments)
            return ToolResult(call_id=tool_call.id, output=output, is_error=False)
        except Exception as exc:  # pragma: no cover - defensive layer
            return ToolResult(
                call_id=tool_call.id,
                output=f"Tool execution error ({tool_call.name}): {type(exc).__name__}: {exc}",
                is_error=True,
            )

    async def execute_batch(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        results: list[ToolResult] = []
        for call in tool_calls:
            results.append(await self.execute_tool_call(call))
        return results
