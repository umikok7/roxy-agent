from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, AsyncIterator

from harness.client import HarnessClient
from harness.context import ConversationStore, ThreadContextStore, ThreadRuntimeResolver, generate_thread_id
from harness.models.types import AgentRunResult


class ChatService:
    def __init__(self, client: HarnessClient | None = None) -> None:
        project_root = Path(__file__).resolve().parents[2]
        self._client = client or HarnessClient(project_root=project_root)
        runtime = self._client.config.runtime
        self._context_store = ThreadContextStore(
            max_recent_messages=runtime.max_recent_messages,
            compact_threshold_chars=runtime.compact_threshold_chars,
            skill_memory_max=runtime.skill_memory_max,
        )
        self._conversation_store = ConversationStore()
        self._thread_runtime = ThreadRuntimeResolver(self._client.config.sandbox.root_dir)
        self._thread_locks: dict[str, asyncio.Lock] = {}

    def _normalize_thread_id(self, thread_id: str | None = None) -> str | None:
        if thread_id and thread_id.strip():
            return thread_id.strip()
        return None

    def _resolve_or_create_thread_id(self, thread_id: str | None = None) -> str:
        return self._normalize_thread_id(thread_id) or generate_thread_id()

    def _get_thread_lock(self, thread_id: str) -> asyncio.Lock:
        lock = self._thread_locks.get(thread_id)
        if lock is None:
            lock = asyncio.Lock()
            self._thread_locks[thread_id] = lock
        return lock

    def _build_history(
        self,
        resolved_thread_id: str,
        *,
        messages: list[dict[str, str]] | None,
    ) -> list[dict[str, str]]:
        thread_paths = self._thread_runtime.ensure_dirs(self._thread_runtime.resolve(resolved_thread_id))
        detail = self._conversation_store.load_conversation(
            resolved_thread_id,
            conversation_path=thread_paths.conversation_file,
            messages_path=thread_paths.messages_file,
        )
        conversation_history = self._conversation_store.build_history_messages(
            detail,
            max_messages=self._client.config.runtime.max_recent_messages,
        )
        if conversation_history:
            return conversation_history

        context = self._context_store.load(resolved_thread_id, context_path=thread_paths.context_file)
        return self._context_store.build_history(context, messages)

    def create_conversation(self, thread_id: str | None = None) -> Any:
        resolved_thread_id = self._resolve_or_create_thread_id(thread_id)
        thread_paths = self._thread_runtime.ensure_dirs(self._thread_runtime.resolve(resolved_thread_id))
        detail = self._conversation_store.ensure_conversation(
            resolved_thread_id,
            conversation_path=thread_paths.conversation_file,
            messages_path=thread_paths.messages_file,
        )
        return detail.summary

    def list_conversations(self) -> list[Any]:
        return self._conversation_store.list_conversations(self._thread_runtime.sandbox_root / "threads")

    def get_conversation(self, thread_id: str) -> Any | None:
        resolved_thread_id = self._normalize_thread_id(thread_id)
        if not resolved_thread_id:
            return None
        thread_paths = self._thread_runtime.resolve(resolved_thread_id)
        return self._conversation_store.load_conversation(
            resolved_thread_id,
            conversation_path=thread_paths.conversation_file,
            messages_path=thread_paths.messages_file,
        )

    def rename_conversation(self, thread_id: str, title: str) -> Any:
        resolved_thread_id = self._normalize_thread_id(thread_id)
        if not resolved_thread_id:
            raise ValueError("thread_id is required")
        thread_paths = self._thread_runtime.ensure_dirs(self._thread_runtime.resolve(resolved_thread_id))
        return self._conversation_store.rename_conversation(
            resolved_thread_id,
            title,
            conversation_path=thread_paths.conversation_file,
            messages_path=thread_paths.messages_file,
        )

    async def run_chat(
        self,
        message: str,
        model: str | None = None,
        *,
        thread_id: str | None = None,
        messages: list[dict[str, str]] | None = None,
    ) -> AgentRunResult:
        resolved_thread_id = self._resolve_or_create_thread_id(thread_id)
        lock = self._get_thread_lock(resolved_thread_id)
        async with lock:
            thread_paths = self._thread_runtime.ensure_dirs(self._thread_runtime.resolve(resolved_thread_id))
            self._conversation_store.ensure_conversation(
                resolved_thread_id,
                conversation_path=thread_paths.conversation_file,
                messages_path=thread_paths.messages_file,
            )
            context = self._context_store.load(resolved_thread_id, context_path=thread_paths.context_file)
            history = self._build_history(resolved_thread_id, messages=messages)

            result = await self._client.run_async(
                message,
                model,
                conversation_history=history,
                thread_id=resolved_thread_id,
                thread_paths=thread_paths,
                pinned_skills=context.pinned_skills,
                compact_summary=context.compact_summary,
            )

            self._context_store.update_after_turn(
                context,
                user_message=message,
                assistant_message=result.text,
                incoming_messages=messages,
                available_skill_names=self._client.list_enabled_skill_names(),
                context_path=thread_paths.context_file,
            )
            self._conversation_store.append_turn(
                resolved_thread_id,
                user_message=message,
                assistant_message=result.text,
                conversation_path=thread_paths.conversation_file,
                messages_path=thread_paths.messages_file,
            )
            result.thread_id = resolved_thread_id
            return result

    async def run_chat_stream(
        self,
        message: str,
        model: str | None = None,
        *,
        thread_id: str | None = None,
        messages: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        yield {"type": "start"}

        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

        async def on_text_delta(delta: str) -> None:
            await queue.put({"type": "delta", "delta": delta})

        async def on_event(event: dict[str, object]) -> None:
            await queue.put(event)

        resolved_thread_id = self._resolve_or_create_thread_id(thread_id)
        lock = self._get_thread_lock(resolved_thread_id)
        async with lock:
            thread_paths = self._thread_runtime.ensure_dirs(self._thread_runtime.resolve(resolved_thread_id))
            self._conversation_store.ensure_conversation(
                resolved_thread_id,
                conversation_path=thread_paths.conversation_file,
                messages_path=thread_paths.messages_file,
            )
            context = self._context_store.load(resolved_thread_id, context_path=thread_paths.context_file)
            history = self._build_history(resolved_thread_id, messages=messages)
            task = asyncio.create_task(
                self._client.run_async(
                    message,
                    model,
                    on_text_delta=on_text_delta,
                    conversation_history=history,
                    thread_id=resolved_thread_id,
                    thread_paths=thread_paths,
                    pinned_skills=context.pinned_skills,
                    compact_summary=context.compact_summary,
                    event_callback=on_event,
                )
            )

            while True:
                if task.done() and queue.empty():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.05)
                    yield event
                except TimeoutError:
                    continue

            result = await task
            self._context_store.update_after_turn(
                context,
                user_message=message,
                assistant_message=result.text,
                incoming_messages=messages,
                available_skill_names=self._client.list_enabled_skill_names(),
                context_path=thread_paths.context_file,
            )
            self._conversation_store.append_turn(
                resolved_thread_id,
                user_message=message,
                assistant_message=result.text,
                conversation_path=thread_paths.conversation_file,
                messages_path=thread_paths.messages_file,
            )
            result.thread_id = resolved_thread_id

        yield {
            "type": "done",
            "text": result.text,
            "trace": {
                "steps": result.trace.steps,
                "tool_calls": result.trace.tool_calls,
                "errors": result.trace.errors,
                "subagent_calls": result.trace.subagent_calls,
                "subagent_errors": result.trace.subagent_errors,
            },
            "thread_id": resolved_thread_id,
        }

    def list_models(self) -> list[dict[str, Any]]:
        return self._client.list_models()


_service: ChatService | None = None


def get_chat_service() -> ChatService:
    global _service
    if _service is None:
        _service = ChatService()
    return _service
