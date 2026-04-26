from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class ThreadContext:
    thread_id: str
    recent_messages: list[dict[str, str]] = field(default_factory=list)
    pinned_skills: list[str] = field(default_factory=list)
    compact_summary: str = ""
    updated_at: str = field(default_factory=_utc_now_iso)


def _resolve_context_path(context_path: Path | None) -> Path:
    if context_path is None:
        raise ValueError(
            "context_path is required for ThreadContextStore; thread context must live in the thread sandbox"
        )
    return context_path


class ThreadContextStore:
    def __init__(
        self,
        *,
        max_recent_messages: int,
        compact_threshold_chars: int,
        skill_memory_max: int,
    ) -> None:
        self.max_recent_messages = max_recent_messages
        self.compact_threshold_chars = compact_threshold_chars
        self.skill_memory_max = skill_memory_max

    def load(self, thread_id: str, *, context_path: Path | None = None) -> ThreadContext:
        path = _resolve_context_path(context_path)
        if not path.exists():
            return ThreadContext(thread_id=thread_id)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return ThreadContext(thread_id=thread_id)

        recent_messages = self._sanitize_messages(data.get("recent_messages", []))
        pinned_skills = [item for item in data.get("pinned_skills", []) if isinstance(item, str)]
        compact_summary = data.get("compact_summary")
        if not isinstance(compact_summary, str):
            compact_summary = ""

        updated_at = data.get("updated_at")
        if not isinstance(updated_at, str) or not updated_at:
            updated_at = _utc_now_iso()

        return ThreadContext(
            thread_id=thread_id,
            recent_messages=recent_messages,
            pinned_skills=pinned_skills[: self.skill_memory_max],
            compact_summary=compact_summary,
            updated_at=updated_at,
        )

    def save(self, context: ThreadContext, *, context_path: Path | None = None) -> None:
        path = _resolve_context_path(context_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "thread_id": context.thread_id,
            "recent_messages": self._sanitize_messages(context.recent_messages),
            "pinned_skills": context.pinned_skills[: self.skill_memory_max],
            "compact_summary": context.compact_summary,
            "updated_at": context.updated_at,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def build_history(
        self,
        context: ThreadContext,
        incoming_messages: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        if context.recent_messages:
            return list(context.recent_messages)
        return self._sanitize_messages(incoming_messages or [])

    def update_after_turn(
        self,
        context: ThreadContext,
        *,
        user_message: str,
        assistant_message: str,
        incoming_messages: list[dict[str, str]] | None,
        available_skill_names: list[str],
        context_path: Path | None = None,
    ) -> ThreadContext:
        source_messages = context.recent_messages or self._sanitize_messages(incoming_messages or [])
        source_messages.append({"role": "user", "content": user_message.strip()})
        source_messages.append({"role": "assistant", "content": assistant_message.strip()})

        context.recent_messages = self._sanitize_messages(source_messages)
        context.pinned_skills = self._merge_pinned_skills(
            existing=context.pinned_skills,
            additions=self._extract_referenced_skills(user_message, available_skill_names),
        )
        context.compact_summary, context.recent_messages = self._compact_messages(
            context.compact_summary,
            context.recent_messages,
        )
        context.updated_at = _utc_now_iso()
        self.save(context, context_path=context_path)
        return context

    @staticmethod
    def _sanitize_messages(raw_messages: list[dict[str, str]]) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        for item in raw_messages:
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
            items.append({"role": role, "content": text})
        return items

    def _merge_pinned_skills(self, *, existing: list[str], additions: list[str]) -> list[str]:
        merged: list[str] = []
        for name in [*existing, *additions]:
            if name not in merged:
                merged.append(name)
        return merged[-self.skill_memory_max :]

    @staticmethod
    def _extract_referenced_skills(user_message: str, available_skill_names: list[str]) -> list[str]:
        text = user_message.lower()
        if not text:
            return []

        skill_intent_words = ("skill", "skills", "加载", "启用", "使用", "apply", "use", "load")
        if not any(word in text for word in skill_intent_words):
            return []

        matched: list[str] = []
        for item in available_skill_names:
            if item.lower() in text:
                matched.append(item)
        return matched

    def _compact_messages(
        self,
        current_summary: str,
        recent_messages: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]]]:
        trimmed = recent_messages[-self.max_recent_messages :]
        total_chars = sum(len(item["content"]) for item in trimmed)
        if total_chars <= self.compact_threshold_chars:
            return current_summary, trimmed

        split_index = max(2, len(trimmed) // 2)
        older = trimmed[:split_index]
        newer = trimmed[split_index:]

        summary_lines = []
        for item in older:
            clipped = item["content"].replace("\n", " ")[:180]
            summary_lines.append(f"- {item['role']}: {clipped}")

        older_summary = "\n".join(summary_lines)
        if current_summary:
            merged_summary = f"{current_summary}\n\n{older_summary}".strip()
        else:
            merged_summary = older_summary

        return merged_summary, newer
