from __future__ import annotations

import pytest

from harness.models.types import RuntimeContext, ToolCall
from harness.sandbox.runtime import BasicSandbox
from harness.tools.executor import ToolExecutor
from harness.tools.local_browser import LocalBrowserClient
from harness.tools.registry import ToolRegistry, ToolRuntime
from harness.tools.web_search import WebSearchClient


class FakeWebSearchClient(WebSearchClient):
    def search(self, query: str, *, max_results: int = 5) -> str:
        return f"search:{query}:{max_results}"


class FakeKnowledgeBaseService:
    def render_search_results(self, query: str, *, top_k: int | None = None) -> str:
        return f"Knowledge base results for: {query}\n1. title=退款政策 source=refund.md hybrid_score=0.9000 rerank_score=0.9500 text=支持 7 天退款"


class FakeLocalBrowserClient(LocalBrowserClient):
    def open_url(self, url: str, *, action: str = "browser_open", meta: dict[str, str] | None = None) -> str:
        return f"{action}:{url}:{meta or {}}"

    def search(self, query: str, *, open_result: bool = False) -> str:
        return f"browser_search:{query}:{open_result}"


class FailingLocalBrowserClient(LocalBrowserClient):
    def open_url(self, url: str, *, action: str = "browser_open", meta: dict[str, str] | None = None) -> str:
        raise RuntimeError("gui unavailable")


@pytest.mark.asyncio
async def test_tool_registry_and_executor_roundtrip(tmp_path):
    sandbox = BasicSandbox(tmp_path)
    registry = ToolRegistry.with_default_tools(sandbox)
    executor = ToolExecutor(registry, ToolRuntime(sandbox=sandbox, context=RuntimeContext()))

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
    executor = ToolExecutor(registry, ToolRuntime(sandbox=sandbox, context=RuntimeContext()))

    result = await executor.execute_tool_call(ToolCall(id="x", name="not_exists", arguments={}))
    assert result.is_error is True
    assert "Unknown tool" in result.output


@pytest.mark.asyncio
async def test_tool_registry_supports_thread_workspace_and_skills_dirs(tmp_path):
    thread_root = tmp_path / "threads" / "t1"
    sandbox = BasicSandbox(thread_root, command_cwd=thread_root / "workspace")
    registry = ToolRegistry.with_default_tools(sandbox)
    executor = ToolExecutor(registry, ToolRuntime(sandbox=sandbox, context=RuntimeContext()))

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
    executor = ToolExecutor(registry, ToolRuntime(sandbox=sandbox, context=RuntimeContext()))

    result = await executor.execute_tool_call(
        ToolCall(id="4", name="web_search", arguments={"query": "roxy flow", "max_results": 3})
    )

    assert result.is_error is False
    assert result.output == "search:roxy flow:3"


@pytest.mark.asyncio
async def test_tool_registry_supports_knowledge_search(tmp_path):
    sandbox = BasicSandbox(tmp_path)
    registry = ToolRegistry.with_default_tools(sandbox, knowledge_base=FakeKnowledgeBaseService())
    executor = ToolExecutor(registry, ToolRuntime(sandbox=sandbox, context=RuntimeContext()))

    result = await executor.execute_tool_call(
        ToolCall(id="5", name="knowledge_search", arguments={"query": "退款政策", "top_k": 2})
    )

    assert result.is_error is False
    assert "hybrid_score=0.9000" in result.output
    assert "rerank_score=0.9500" in result.output


@pytest.mark.asyncio
async def test_tool_registry_supports_browser_tools(tmp_path):
    sandbox = BasicSandbox(tmp_path)
    registry = ToolRegistry.with_default_tools(sandbox, local_browser_client=FakeLocalBrowserClient())
    executor = ToolExecutor(registry, ToolRuntime(sandbox=sandbox, context=RuntimeContext()))

    search_result = await executor.execute_tool_call(
        ToolCall(id="6", name="browser_search", arguments={"query": "roxy flow", "open_result": False})
    )
    open_result = await executor.execute_tool_call(
        ToolCall(id="7", name="browser_open", arguments={"url": "https://example.com"})
    )

    assert search_result.is_error is False
    assert search_result.output == "browser_search:roxy flow:False"
    assert open_result.is_error is False
    assert open_result.output == "browser_open:https://example.com:{}"


@pytest.mark.asyncio
async def test_tool_registry_skips_browser_tools_when_disabled(tmp_path):
    sandbox = BasicSandbox(tmp_path)
    registry = ToolRegistry.with_default_tools(
        sandbox,
        local_browser_client=FakeLocalBrowserClient(enabled=False),
        local_browser_enabled=False,
    )
    executor = ToolExecutor(registry, ToolRuntime(sandbox=sandbox, context=RuntimeContext()))

    tool_names = {item["function"]["name"] for item in registry.list_tool_schemas()}
    result = await executor.execute_tool_call(ToolCall(id="8", name="browser_open", arguments={"url": "https://example.com"}))

    assert "browser_open" not in tool_names
    assert "browser_search" not in tool_names
    assert result.is_error is True
    assert "Unknown tool" in result.output


@pytest.mark.asyncio
async def test_browser_tool_failure_sets_error_result(tmp_path):
    sandbox = BasicSandbox(tmp_path)
    registry = ToolRegistry.with_default_tools(sandbox, local_browser_client=FailingLocalBrowserClient())
    executor = ToolExecutor(registry, ToolRuntime(sandbox=sandbox, context=RuntimeContext()))

    result = await executor.execute_tool_call(
        ToolCall(id="9", name="browser_open", arguments={"url": "https://example.com"})
    )

    assert result.is_error is True
    assert "Tool execution error (browser_open)" in result.output
    assert "gui unavailable" in result.output
