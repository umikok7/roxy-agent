from __future__ import annotations

import pytest

from harness.models.types import ToolCall
from harness.sandbox.runtime import BasicSandbox
from harness.tools.executor import ToolExecutor
from harness.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_tool_registry_and_executor_roundtrip(tmp_path):
    sandbox = BasicSandbox(tmp_path)
    registry = ToolRegistry.with_default_tools(sandbox)
    executor = ToolExecutor(registry)

    write_result = await executor.execute_tool_call(
        ToolCall(id="1", name="write_file", arguments={"path": "a.txt", "content": "hello"})
    )
    read_result = await executor.execute_tool_call(
        ToolCall(id="2", name="read_file", arguments={"path": "a.txt"})
    )

    assert write_result.is_error is False
    assert read_result.is_error is False
    assert read_result.output == "hello"


@pytest.mark.asyncio
async def test_unknown_tool_returns_error(tmp_path):
    sandbox = BasicSandbox(tmp_path)
    registry = ToolRegistry.with_default_tools(sandbox)
    executor = ToolExecutor(registry)

    result = await executor.execute_tool_call(ToolCall(id="x", name="not_exists", arguments={}))
    assert result.is_error is True
    assert "Unknown tool" in result.output
