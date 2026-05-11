from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from harness.models.types import AgentRunResult, AgentTrace, ToolCall
from harness.tools.executor import ToolExecutor


ChatMessage = dict[str, Any]


def split_stream_delta(text: str, *, chunk_size: int = 12) -> list[str]:
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    current = ""
    punctuation = {"。", "！", "？", "，", ",", ".", "!", "?", ";", "；", "\n"}

    for char in text:
        current += char
        if len(current) >= chunk_size or char in punctuation:
            chunks.append(current)
            current = ""

    if current:
        chunks.append(current)
    return chunks


class ChatCompletionsModelClient(Protocol):
    async def create_response(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
        on_delta: Callable[[str], Awaitable[None] | None] | None = None,
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
        on_delta: Callable[[str], Awaitable[None] | None] | None = None,
    ) -> tuple[str, list[ToolCall]]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        if on_delta is not None:
            # 开启 OpenAI streaming
            kwargs["stream"] = True

            stream = await self._client.chat.completions.create(**kwargs)

            text_parts: list[str] = []
            tool_parts: dict[int, dict[str, str]] = {}

            async for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue

                delta = getattr(choices[0], "delta", None)
                if delta is None:
                    continue

                content = getattr(delta, "content", None)
                if content:
                    text_parts.append(content)
                    for piece in split_stream_delta(content):
                        maybe_awaitable = on_delta(piece)
                        if maybe_awaitable is not None:
                            await maybe_awaitable

                delta_tool_calls = getattr(delta, "tool_calls", None) or []
                for item in delta_tool_calls:
                    index = getattr(item, "index", 0) or 0
                    current = tool_parts.setdefault(index, {"id": "", "name": "", "arguments": ""})

                    call_id = getattr(item, "id", None)
                    if call_id:
                        current["id"] = call_id

                    function = getattr(item, "function", None)
                    if function is None:
                        continue

                    function_name = getattr(function, "name", None)
                    if function_name:
                        current["name"] += function_name

                    function_arguments = getattr(function, "arguments", None)
                    if function_arguments:
                        current["arguments"] += function_arguments

            tool_calls: list[ToolCall] = []
            for _, raw in sorted(tool_parts.items(), key=lambda entry: entry[0]):
                raw_arguments = raw.get("arguments", "{}") or "{}"
                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    arguments = {}

                tool_calls.append(
                    ToolCall(
                        id=raw.get("id", ""),
                        name=raw.get("name", ""),
                        arguments=arguments,
                    )
                )

            return "".join(text_parts), tool_calls

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
        max_concurrent_subagents: int = 3,
    ) -> None:
        self.model_client = model_client
        self.tool_executor = tool_executor
        self.tool_schemas = tool_schemas
        self.settings = settings
        self.instructions = instructions
        self.max_concurrent_subagents = max(1, max_concurrent_subagents)

    def _has_tool(self, name: str) -> bool:
        return any(item.get("function", {}).get("name") == name for item in self.tool_schemas)

    @staticmethod
    def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
        lowered = text.lower()
        return any(pattern in lowered for pattern in patterns)

    def _should_retry_browser_tool_use(self, user_prompt: str, assistant_text: str, *, already_retried: bool) -> bool:
        if already_retried:
            return False
        if not self._has_tool("browser_search") and not self._has_tool("browser_open"):
            return False

        prompt_text = user_prompt.strip()
        assistant_output = assistant_text.strip()
        if not prompt_text or not assistant_output:
            return False

        browser_request_patterns = (
            "打开浏览器",
            "浏览器",
            "open browser",
            "launch browser",
            "open the browser",
            "open webpage",
            "打开网页",
            "打开页面",
            "search in browser",
            "browser search",
        )
        if not self._contains_any(prompt_text, browser_request_patterns):
            return False

        false_action_patterns = (
            "browser_search",
            "browser_open",
            "浏览器已打开",
            "已打开搜索页面",
            "已打开浏览器",
            "搜索页面已打开",
            "opened browser",
            "opened the browser",
            "opened search",
        )
        return self._contains_any(assistant_output, false_action_patterns)

    def _truncate_subagent_calls(self, tool_calls: list[ToolCall]) -> tuple[list[ToolCall], int]:
        task_indices = [index for index, call in enumerate(tool_calls) if call.name == "task"]
        if len(task_indices) <= self.max_concurrent_subagents:
            return tool_calls, 0
        drop_indices = set(task_indices[self.max_concurrent_subagents :])
        return [call for index, call in enumerate(tool_calls) if index not in drop_indices], len(drop_indices)

    async def run(
        self,
        user_prompt: str,
        *,
        history_messages: list[ChatMessage] | None = None,
    ) -> AgentRunResult:
        return await self._run_impl(user_prompt, history_messages=history_messages)

    async def run_with_stream(
        self,
        user_prompt: str,
        *,
        on_text_delta: Callable[[str], Awaitable[None] | None] | None = None,
        history_messages: list[ChatMessage] | None = None,
    ) -> AgentRunResult:
        return await self._run_impl(
            user_prompt,
            on_text_delta=on_text_delta,
            history_messages=history_messages,
        )

    @staticmethod
    def _normalize_history(history_messages: list[ChatMessage]) -> list[ChatMessage]:
        normalized: list[ChatMessage] = []
        for item in history_messages:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role not in {"user", "assistant"}:
                continue
            if not isinstance(content, str):
                continue
            text = content.strip()
            if not text:
                continue
            normalized.append({"role": role, "content": text})
        return normalized

    async def _run_impl(
        self,
        user_prompt: str,
        on_text_delta: Callable[[str], Awaitable[None] | None] | None = None,
        history_messages: list[ChatMessage] | None = None,
    ) -> AgentRunResult:
        trace = AgentTrace()

        messages: list[ChatMessage] = []
        if self.instructions:
            messages.append({"role": "system", "content": self.instructions})
        if history_messages:
            messages.extend(self._normalize_history(history_messages))
        messages.append({"role": "user", "content": user_prompt})
        final_text = ""
        browser_retry_used = False

        for _ in range(self.settings.max_steps):
            trace.steps += 1
            text, tool_calls = await self.model_client.create_response(
                model=self.settings.model,
                messages=messages,
                tools=self.tool_schemas,
                temperature=self.settings.temperature,
                max_tokens=self.settings.max_tokens,
                on_delta=on_text_delta,
            )

            if text:
                final_text = text

            tool_calls, dropped_subagents = self._truncate_subagent_calls(tool_calls)
            if dropped_subagents:
                trace.subagent_errors += dropped_subagents

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
                if self._should_retry_browser_tool_use(user_prompt, final_text or text or "", already_retried=browser_retry_used):
                    browser_retry_used = True
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Tool-use correction: you have not executed the browser action yet. "
                                "If you intend to open or search in the host browser, call browser_search or browser_open now. "
                                "Do not claim success without a real tool call."
                            ),
                        }
                    )
                    continue
                return AgentRunResult(text=final_text or "(empty response)", trace=trace)

            trace.tool_calls += len(tool_calls)
            trace.subagent_calls += sum(1 for call in tool_calls if call.name == "task")
            tool_results = await self.tool_executor.execute_batch(tool_calls)
            trace.errors += sum(1 for result in tool_results if result.is_error)
            trace.subagent_errors += sum(
                1 for call, result in zip(tool_calls, tool_results, strict=False) if call.name == "task" and result.is_error
            )

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
