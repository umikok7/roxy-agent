from __future__ import annotations

import pytest

from harness.models.types import ToolCall
from harness.sandbox.runtime import BasicSandbox
from harness.tools.executor import ToolExecutor
from harness.tools.registry import ToolRegistry
from harness.tools.web_search import WebSearchClient


class FakeWebSearchClient(WebSearchClient):
    def search(self, query: str, *, max_results: int = 5) -> str:
        return f"search:{query}:{max_results}"


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


@pytest.mark.asyncio
async def test_tool_registry_supports_thread_workspace_and_skills_dirs(tmp_path):
    thread_root = tmp_path / "threads" / "t1"
    sandbox = BasicSandbox(thread_root, command_cwd=thread_root / "workspace")
    registry = ToolRegistry.with_default_tools(sandbox)
    executor = ToolExecutor(registry)

    workspace_result = await executor.execute_tool_call(
        ToolCall(id="1", name="write_file", arguments={"path": "workspace/note.txt", "content": "workspace"})
    )
    skills_result = await executor.execute_tool_call(
        ToolCall(id="2", name="write_file", arguments={"path": "skills/example/SKILL.md", "content": "skill"})
    )
    read_result = await executor.execute_tool_call(
        ToolCall(id="3", name="read_file", arguments={"path": "skills/example/SKILL.md"})
    )

    assert workspace_result.is_error is False
    assert skills_result.is_error is False
    assert read_result.output == "skill"


@pytest.mark.asyncio
async def test_tool_registry_supports_web_search(tmp_path):
    sandbox = BasicSandbox(tmp_path)
    registry = ToolRegistry.with_default_tools(sandbox, web_search_client=FakeWebSearchClient())
    executor = ToolExecutor(registry)

    result = await executor.execute_tool_call(
        ToolCall(id="4", name="web_search", arguments={"query": "deer flow", "max_results": 3})
    )

    assert result.is_error is False
    assert result.output == "search:deer flow:3"
