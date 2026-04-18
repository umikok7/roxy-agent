from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from harness.models.types import AgentRunResult, AgentTrace, ToolCall
from harness.tools.executor import ToolExecutor


ChatMessage = dict[str, Any]


class ChatCompletionsModelClient(Protocol):
    async def create_response(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, list[ToolCall]]: ...


ResponsesModelClient = ChatCompletionsModelClient


@dataclass(slots=True)
class LoopSettings:
    model: str
    max_steps: int = 8
    temperature: float | None = 1.0
    max_tokens: int | None = 4096


class OpenAIChatCompletionsClient:
    def __init__(self, *, api_key: str, base_url: str | None = None) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError("openai package is required. Install dependency 'openai'.") from exc

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def create_response(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, list[ToolCall]]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        response = await self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message

        tool_calls: list[ToolCall] = []
        for item in getattr(message, "tool_calls", []) or []:
            function = getattr(item, "function", None)
            if function is None:
                continue
            raw_arguments = getattr(function, "arguments", "{}") or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = {}

            tool_calls.append(
                ToolCall(
                    id=getattr(item, "id", ""),
                    name=getattr(function, "name", ""),
                    arguments=arguments,
                )
            )

        output_text = getattr(message, "content", "") or ""
        return output_text, tool_calls


class AsyncAgentLoop:
    def __init__(
        self,
        *,
        model_client: ChatCompletionsModelClient,
        tool_executor: ToolExecutor,
        tool_schemas: list[dict[str, Any]],
        settings: LoopSettings,
        instructions: str | None = None,
    ) -> None:
        self.model_client = model_client
        self.tool_executor = tool_executor
        self.tool_schemas = tool_schemas
        self.settings = settings
        self.instructions = instructions

    async def run(self, user_prompt: str) -> AgentRunResult:
        trace = AgentTrace()

        messages: list[ChatMessage] = []
        if self.instructions:
            messages.append({"role": "system", "content": self.instructions})
        messages.append({"role": "user", "content": user_prompt})
        final_text = ""

        for _ in range(self.settings.max_steps):
            trace.steps += 1
            text, tool_calls = await self.model_client.create_response(
                model=self.settings.model,
                messages=messages,
                tools=self.tool_schemas,
                temperature=self.settings.temperature,
                max_tokens=self.settings.max_tokens,
            )

            if text:
                final_text = text

            assistant_message: ChatMessage = {"role": "assistant", "content": text or None}
            if tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments, ensure_ascii=False),
                        },
                    }
                    for call in tool_calls
                ]
            messages.append(assistant_message)

            if not tool_calls:
                return AgentRunResult(text=final_text or "(empty response)", trace=trace)

            trace.tool_calls += len(tool_calls)
            tool_results = await self.tool_executor.execute_batch(tool_calls)
            trace.errors += sum(1 for result in tool_results if result.is_error)

            messages.extend(
                {
                    "role": "tool",
                    "tool_call_id": result.call_id,
                    "content": result.output,
                }
                for result in tool_results
            )

        timeout_text = "Stopped because max_steps was reached."
        if final_text:
            timeout_text = f"{final_text}\n\n{timeout_text}"
        return AgentRunResult(text=timeout_text, trace=trace)


OpenAIResponsesClient = OpenAIChatCompletionsClient
