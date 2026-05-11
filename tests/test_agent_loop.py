from __future__ import annotations

import pytest

from harness.agents.loop import AsyncAgentLoop, ChatCompletionsModelClient, LoopSettings, split_stream_delta
from harness.models.types import RuntimeContext, ToolCall
from harness.sandbox.runtime import BasicSandbox
from harness.tools.executor import ToolExecutor
from harness.tools.local_browser import LocalBrowserClient
from harness.tools.registry import ToolRegistry, ToolRuntime


class FakeResponsesClient(ChatCompletionsModelClient):
    def __init__(self):
        self.calls = 0

    async def create_response(
        self,
        *,
        model,
        messages,
        tools,
        temperature=None,
        max_tokens=None,
        on_delta=None,
    ):
        self.calls += 1
        if self.calls == 1:
            assert messages[0]["role"] == "system"
            assert messages[1]["role"] == "user"
            assert tools[0]["type"] == "function"
            assert tools[0]["function"]["name"] == "bash"
            return (
                "",
                [
                    ToolCall(
                        id="call_1",
                        name="write_file",
                        arguments={"path": "memo.txt", "content": "ok"},
                    )
                ],
            )
        assert messages[-2]["role"] == "assistant"
        assert messages[-2]["tool_calls"][0]["id"] == "call_1"
        assert messages[-1]["role"] == "tool"
        assert messages[-1]["tool_call_id"] == "call_1"
        return ("done", [])


class FakeResponsesClientWithHistory(ChatCompletionsModelClient):
    async def create_response(
        self,
        *,
        model,
        messages,
        tools,
        temperature=None,
        max_tokens=None,
        on_delta=None,
    ):
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "turn1"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "turn1 answer"
        assert messages[3]["role"] == "user"
        assert messages[3]["content"] == "turn2"
        return ("ok", [])


class FakeKnowledgeBaseService:
    def render_search_results(self, query: str, *, top_k: int | None = None) -> str:
        return (
            f"Knowledge base results for: {query}\n"
            "1. title=退款政策 source=refund.md hybrid_score=0.9900 rerank_score=0.9950 text=支持 7 天退款"
        )


class FakeResponsesClientWithKnowledgeSearch(ChatCompletionsModelClient):
    def __init__(self):
        self.calls = 0

    async def create_response(
        self,
        *,
        model,
        messages,
        tools,
        temperature=None,
        max_tokens=None,
        on_delta=None,
    ):
        self.calls += 1
        if self.calls == 1:
            assert any(item["function"]["name"] == "knowledge_search" for item in tools)
            return ("", [ToolCall(id="call_kb", name="knowledge_search", arguments={"query": "退款政策"})])
        assert messages[-1]["role"] == "tool"
        assert messages[-1]["tool_call_id"] == "call_kb"
        assert "退款政策" in messages[-1]["content"]
        return ("根据知识库，支持 7 天退款。", [])


class FakeLocalBrowserClient(LocalBrowserClient):
    def search(self, query: str, *, open_result: bool = False) -> str:
        return f"action=browser_search\nok=true\nopened=true\nurl=https://example.com/search?q={query}\nmessage=Opened"


class FakeResponsesClientWithBrowserSearch(ChatCompletionsModelClient):
    def __init__(self):
        self.calls = 0

    async def create_response(
        self,
        *,
        model,
        messages,
        tools,
        temperature=None,
        max_tokens=None,
        on_delta=None,
    ):
        self.calls += 1
        if self.calls == 1:
            assert any(item["function"]["name"] == "browser_search" for item in tools)
            return ("", [ToolCall(id="call_browser", name="browser_search", arguments={"query": "roxy"})])
        assert messages[-1]["role"] == "tool"
        assert messages[-1]["tool_call_id"] == "call_browser"
        assert "action=browser_search" in messages[-1]["content"]
        return ("已经在本地浏览器里打开搜索结果。", [])


class FakeResponsesClientWithHallucinatedBrowserAction(ChatCompletionsModelClient):
    def __init__(self):
        self.calls = 0

    async def create_response(
        self,
        *,
        model,
        messages,
        tools,
        temperature=None,
        max_tokens=None,
        on_delta=None,
    ):
        self.calls += 1
        if self.calls == 1:
            return ("browser_search - 已经帮你打开浏览器搜索洛琪希。", [])
        if self.calls == 2:
            assert messages[-1]["role"] == "user"
            assert "Tool-use correction" in messages[-1]["content"]
            return ("", [ToolCall(id="call_browser_retry", name="browser_search", arguments={"query": "洛琪希"})])
        assert messages[-1]["role"] == "tool"
        assert messages[-1]["tool_call_id"] == "call_browser_retry"
        return ("这次已经真正打开浏览器搜索洛琪希了。", [])


@pytest.mark.asyncio
async def test_agent_loop_handles_tool_use_roundtrip(tmp_path):
    sandbox = BasicSandbox(tmp_path)
    registry = ToolRegistry.with_default_tools(sandbox)
    executor = ToolExecutor(registry, ToolRuntime(sandbox=sandbox, context=RuntimeContext()))

    loop = AsyncAgentLoop(
        model_client=FakeResponsesClient(),
        tool_executor=executor,
        tool_schemas=registry.list_tool_schemas(),
        settings=LoopSettings(model="fake", max_steps=4),
        instructions="test",
    )

    result = await loop.run("write a memo")

    assert result.text == "done"
    assert result.trace.steps == 2
    assert result.trace.tool_calls == 1
    assert result.trace.errors == 0


@pytest.mark.asyncio
async def test_agent_loop_uses_history_messages(tmp_path):
    sandbox = BasicSandbox(tmp_path)
    registry = ToolRegistry.with_default_tools(sandbox)
    executor = ToolExecutor(registry, ToolRuntime(sandbox=sandbox, context=RuntimeContext()))

    loop = AsyncAgentLoop(
        model_client=FakeResponsesClientWithHistory(),
        tool_executor=executor,
        tool_schemas=registry.list_tool_schemas(),
        settings=LoopSettings(model="fake", max_steps=2),
        instructions="test",
    )

    result = await loop.run(
        "turn2",
        history_messages=[
            {"role": "user", "content": "turn1"},
            {"role": "assistant", "content": "turn1 answer"},
        ],
    )

    assert result.text == "ok"


@pytest.mark.asyncio
async def test_agent_loop_handles_knowledge_search_roundtrip(tmp_path):
    sandbox = BasicSandbox(tmp_path)
    registry = ToolRegistry.with_default_tools(sandbox, knowledge_base=FakeKnowledgeBaseService())
    executor = ToolExecutor(registry, ToolRuntime(sandbox=sandbox, context=RuntimeContext()))

    loop = AsyncAgentLoop(
        model_client=FakeResponsesClientWithKnowledgeSearch(),
        tool_executor=executor,
        tool_schemas=registry.list_tool_schemas(),
        settings=LoopSettings(model="fake", max_steps=4),
        instructions="test",
    )

    result = await loop.run("退款政策是什么")

    assert result.text == "根据知识库，支持 7 天退款。"
    assert result.trace.steps == 2
    assert result.trace.tool_calls == 1


@pytest.mark.asyncio
async def test_agent_loop_handles_browser_search_roundtrip(tmp_path):
    sandbox = BasicSandbox(tmp_path)
    registry = ToolRegistry.with_default_tools(sandbox, local_browser_client=FakeLocalBrowserClient())
    executor = ToolExecutor(registry, ToolRuntime(sandbox=sandbox, context=RuntimeContext()))

    loop = AsyncAgentLoop(
        model_client=FakeResponsesClientWithBrowserSearch(),
        tool_executor=executor,
        tool_schemas=registry.list_tool_schemas(),
        settings=LoopSettings(model="fake", max_steps=4),
        instructions="test",
    )

    result = await loop.run("帮我打开浏览器搜索 roxy")

    assert result.text == "已经在本地浏览器里打开搜索结果。"
    assert result.trace.steps == 2
    assert result.trace.tool_calls == 1


@pytest.mark.asyncio
async def test_agent_loop_retries_when_browser_action_was_only_claimed_in_text(tmp_path):
    sandbox = BasicSandbox(tmp_path)
    registry = ToolRegistry.with_default_tools(sandbox, local_browser_client=FakeLocalBrowserClient())
    executor = ToolExecutor(registry, ToolRuntime(sandbox=sandbox, context=RuntimeContext()))

    loop = AsyncAgentLoop(
        model_client=FakeResponsesClientWithHallucinatedBrowserAction(),
        tool_executor=executor,
        tool_schemas=registry.list_tool_schemas(),
        settings=LoopSettings(model="fake", max_steps=4),
        instructions="test",
    )

    result = await loop.run("打开浏览器搜索一下洛琪希")

    assert result.text == "这次已经真正打开浏览器搜索洛琪希了。"
    assert result.trace.steps == 3
    assert result.trace.tool_calls == 1


def test_split_stream_delta_breaks_large_chunks():
    text = "这是一个较长的流式片段，需要被拆成更小的段落。这样看起来才像真正流式输出。"
    chunks = split_stream_delta(text, chunk_size=10)

    assert len(chunks) > 2
    assert "".join(chunks) == text
    assert all(chunk for chunk in chunks)
