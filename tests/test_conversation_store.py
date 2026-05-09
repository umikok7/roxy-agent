from __future__ import annotations

import json

from harness.context import ConversationStore


def test_conversation_store_creates_and_appends_turns(tmp_path):
    store = ConversationStore()
    conversation_path = tmp_path / "threads" / "t1" / "conversation.json"
    messages_path = tmp_path / "threads" / "t1" / "messages.json"

    detail = store.ensure_conversation(
        "t1",
        conversation_path=conversation_path,
        messages_path=messages_path,
    )
    assert detail.summary.thread_id == "t1"
    assert conversation_path.exists()
    assert messages_path.exists()

    updated = store.append_turn(
        "t1",
        user_message="hello world",
        assistant_message="reply text",
        conversation_path=conversation_path,
        messages_path=messages_path,
    )

    assert updated.summary.title == "hello world"
    assert updated.summary.message_count == 2
    assert updated.summary.last_message_preview == "reply text"
    assert [item.role for item in updated.messages] == ["user", "assistant"]


def test_conversation_store_lists_conversations_in_desc_order(tmp_path):
    store = ConversationStore()
    threads_root = tmp_path / "threads"

    store.append_turn(
        "thread-a",
        user_message="first",
        assistant_message="reply a",
        conversation_path=threads_root / "thread-a" / "conversation.json",
        messages_path=threads_root / "thread-a" / "messages.json",
    )
    store.append_turn(
        "thread-b",
        user_message="second",
        assistant_message="reply b",
        conversation_path=threads_root / "thread-b" / "conversation.json",
        messages_path=threads_root / "thread-b" / "messages.json",
    )

    summaries = store.list_conversations(threads_root)

    assert [item.thread_id for item in summaries] == ["thread-b", "thread-a"]


def test_conversation_store_skips_corrupt_summary_files(tmp_path):
    store = ConversationStore()
    threads_root = tmp_path / "threads"
    valid_dir = threads_root / "valid"
    invalid_dir = threads_root / "invalid"
    valid_dir.mkdir(parents=True, exist_ok=True)
    invalid_dir.mkdir(parents=True, exist_ok=True)

    (invalid_dir / "conversation.json").write_text("{bad json", encoding="utf-8")
    (valid_dir / "conversation.json").write_text(
        json.dumps(
            {
                "thread_id": "valid",
                "title": "ok",
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "last_message_preview": "preview",
                "message_count": 0,
            }
        ),
        encoding="utf-8",
    )

    summaries = store.list_conversations(threads_root)

    assert len(summaries) == 1
    assert summaries[0].thread_id == "valid"
