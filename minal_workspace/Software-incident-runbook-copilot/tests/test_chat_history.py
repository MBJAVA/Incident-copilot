from __future__ import annotations

import pytest

from incident_copilot.chat_history import ChatHistoryStore


def test_saved_chat_can_be_reopened_after_store_is_recreated(tmp_path) -> None:
    directory = tmp_path / "chats"
    store = ChatHistoryStore(directory)
    messages = [
        {"role": "user", "content": "What is the CHECKOUT-5XX threshold and duration?"},
        {"role": "assistant", "response": {"summary": {"text": "3% for 5 minutes"}}},
    ]

    chat_id = store.save_chat(messages)
    reopened = ChatHistoryStore(directory)

    assert reopened.list_chats()[0]["id"] == chat_id
    assert reopened.list_chats()[0]["title"] == messages[0]["content"]
    assert reopened.load_chat(chat_id)["messages"] == messages

    messages.append({"role": "user", "content": "Who owns the service?"})
    reopened.save_chat(messages, chat_id)
    assert store.load_chat(chat_id)["messages"][-1]["content"] == "Who owns the service?"
    assert len(store.list_chats()) == 1


def test_chat_history_rejects_path_traversal(tmp_path) -> None:
    store = ChatHistoryStore(tmp_path / "chats")

    with pytest.raises(ValueError, match="Invalid chat ID"):
        store.load_chat("../../outside")

    with pytest.raises(ValueError, match="Invalid chat ID"):
        store.delete_chat("../../outside")


def test_delete_one_or_all_saved_chats(tmp_path) -> None:
    store = ChatHistoryStore(tmp_path / "chats")
    first = store.save_chat([{"role": "user", "content": "First incident"}])
    second = store.save_chat([{"role": "user", "content": "Second incident"}])

    assert store.delete_chat(first) is True
    assert store.delete_chat(first) is False
    assert store.load_chat(first) is None
    assert [chat["id"] for chat in store.list_chats()] == [second]

    assert store.delete_all_chats() == 1
    assert store.list_chats() == []
