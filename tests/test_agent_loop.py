from __future__ import annotations

import pytest

from harness.agents.loop import AsyncAgentLoop, ChatCompletionsModelClient, LoopSettings
from harness.models.types import ToolCall
from harness.sandbox.runtime import BasicSandbox
from harness.tools.executor import ToolExecutor
from harness.tools.registry import ToolRegistry


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


@pytest.mark.asyncio
async def test_agent_loop_handles_tool_use_roundtrip(tmp_path):
    sandbox = BasicSandbox(tmp_path)
    registry = ToolRegistry.with_default_tools(sandbox)
    executor = ToolExecutor(registry)

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
    executor = ToolExecutor(registry)

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
