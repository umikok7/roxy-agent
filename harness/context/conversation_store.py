from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def generate_thread_id() -> str:
    return f"thread-{uuid.uuid4()}"


@dataclass(slots=True)
class ConversationMessage:
    id: str
    role: str
    content: str
    created_at: str


@dataclass(slots=True)
class ConversationSummary:
    thread_id: str
    title: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    last_message_preview: str = ""
    message_count: int = 0


@dataclass(slots=True)
class ConversationDetail:
    summary: ConversationSummary
    messages: list[ConversationMessage] = field(default_factory=list)


def _safe_read_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _clip_text(text: str, *, limit: int) -> str:
    value = " ".join(text.strip().split())
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _default_title(text: str) -> str:
    clipped = _clip_text(text, limit=48)
    return clipped or "New Conversation"


def _default_preview(assistant_message: str, user_message: str) -> str:
    candidate = assistant_message.strip() or user_message.strip()
    return _clip_text(candidate, limit=120)


class ConversationStore:
    def ensure_conversation(
        self,
        thread_id: str,
        *,
        conversation_path: Path,
        messages_path: Path,
    ) -> ConversationDetail:
        existing = self.load_conversation(
            thread_id,
            conversation_path=conversation_path,
            messages_path=messages_path,
        )
        if existing is not None:
            return existing

        summary = ConversationSummary(thread_id=thread_id)
        detail = ConversationDetail(summary=summary, messages=[])
        self.save_conversation(detail, conversation_path=conversation_path, messages_path=messages_path)
        return detail

    def load_conversation(
        self,
        thread_id: str,
        *,
        conversation_path: Path,
        messages_path: Path,
    ) -> ConversationDetail | None:
        summary_data = _safe_read_json(conversation_path)
        messages_data = _safe_read_json(messages_path)

        if summary_data is None and messages_data is None:
            return None

        summary = self._parse_summary(summary_data, fallback_thread_id=thread_id)
        messages = self._parse_messages(messages_data)
        if summary.message_count != len(messages):
            summary.message_count = len(messages)
        return ConversationDetail(summary=summary, messages=messages)

    def save_conversation(
        self,
        detail: ConversationDetail,
        *,
        conversation_path: Path,
        messages_path: Path,
    ) -> None:
        conversation_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(detail.summary)
        conversation_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        message_payload = [asdict(item) for item in detail.messages]
        messages_path.write_text(json.dumps(message_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def append_turn(
        self,
        thread_id: str,
        *,
        user_message: str,
        assistant_message: str,
        conversation_path: Path,
        messages_path: Path,
    ) -> ConversationDetail:
        detail = self.ensure_conversation(
            thread_id,
            conversation_path=conversation_path,
            messages_path=messages_path,
        )

        now = utc_now_iso()
        detail.messages.extend(
            [
                ConversationMessage(
                    id=f"msg-{uuid.uuid4()}",
                    role="user",
                    content=user_message.strip(),
                    created_at=now,
                ),
                ConversationMessage(
                    id=f"msg-{uuid.uuid4()}",
                    role="assistant",
                    content=assistant_message.strip(),
                    created_at=now,
                ),
            ]
        )

        summary = detail.summary
        if not summary.title:
            summary.title = _default_title(user_message)
            if not summary.created_at:
                summary.created_at = now
        summary.updated_at = now
        summary.last_message_preview = _default_preview(assistant_message, user_message)
        summary.message_count = len(detail.messages)

        self.save_conversation(detail, conversation_path=conversation_path, messages_path=messages_path)
        return detail

    def rename_conversation(
        self,
        thread_id: str,
        title: str,
        *,
        conversation_path: Path,
        messages_path: Path,
    ) -> ConversationSummary:
        detail = self.ensure_conversation(
            thread_id,
            conversation_path=conversation_path,
            messages_path=messages_path,
        )
        detail.summary.title = title.strip() or detail.summary.title or "New Conversation"
        detail.summary.updated_at = utc_now_iso()
        self.save_conversation(detail, conversation_path=conversation_path, messages_path=messages_path)
        return detail.summary

    def list_conversations(self, threads_root: Path) -> list[ConversationSummary]:
        if not threads_root.exists():
            return []

        summaries: list[ConversationSummary] = []
        for thread_dir in threads_root.iterdir():
            if not thread_dir.is_dir():
                continue
            summary_data = _safe_read_json(thread_dir / "conversation.json")
            if summary_data is None:
                continue
            try:
                summary = self._parse_summary(summary_data)
            except ValueError:
                continue
            summaries.append(summary)

        summaries.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
        return summaries

    @staticmethod
    def build_history_messages(
        detail: ConversationDetail | None,
        *,
        max_messages: int,
    ) -> list[dict[str, str]]:
        if detail is None:
            return []
        history = [
            {"role": item.role, "content": item.content}
            for item in detail.messages
            if item.role in {"user", "assistant"} and item.content.strip()
        ]
        if max_messages > 0:
            return history[-max_messages:]
        return history

    @staticmethod
    def _parse_summary(data: object | None, fallback_thread_id: str | None = None) -> ConversationSummary:
        if not isinstance(data, dict):
            if fallback_thread_id is None:
                raise ValueError("Missing conversation summary")
            return ConversationSummary(thread_id=fallback_thread_id)

        thread_id = data.get("thread_id")
        if not isinstance(thread_id, str) or not thread_id.strip():
            if fallback_thread_id is None:
                raise ValueError("Invalid thread_id")
            thread_id = fallback_thread_id

        created_at = data.get("created_at")
        updated_at = data.get("updated_at")
        return ConversationSummary(
            thread_id=thread_id,
            title=data.get("title") if isinstance(data.get("title"), str) else "",
            created_at=created_at if isinstance(created_at, str) and created_at else utc_now_iso(),
            updated_at=updated_at if isinstance(updated_at, str) and updated_at else utc_now_iso(),
            last_message_preview=(
                data.get("last_message_preview")
                if isinstance(data.get("last_message_preview"), str)
                else ""
            ),
            message_count=data.get("message_count") if isinstance(data.get("message_count"), int) else 0,
        )

    @staticmethod
    def _parse_messages(data: object | None) -> list[ConversationMessage]:
        if not isinstance(data, list):
            return []
        messages: list[ConversationMessage] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            created_at = item.get("created_at")
            message_id = item.get("id")
            if role not in {"user", "assistant"}:
                continue
            if not isinstance(content, str) or not content.strip():
                continue
            messages.append(
                ConversationMessage(
                    id=message_id if isinstance(message_id, str) and message_id else f"msg-{uuid.uuid4()}",
                    role=role,
                    content=content.strip(),
                    created_at=created_at if isinstance(created_at, str) and created_at else utc_now_iso(),
                )
            )
        return messages
