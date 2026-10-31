from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from incident_copilot.chat_history import ChatHistoryStore


def test_sidebar_can_reopen_a_saved_chat_after_new_chat(tmp_path, monkeypatch) -> None:
    directory = tmp_path / "chats"
    store = ChatHistoryStore(directory)
    chat_id = store.save_chat([
        {"role": "user", "content": "What is the CHECKOUT-5XX threshold?"},
        {"role": "assistant", "error": "Temporary test response"},
    ])
    monkeypatch.setenv("INCIDENT_CHAT_HISTORY_DIR", str(directory))
    app_path = Path(__file__).parents[1] / "app.py"

    app = AppTest.from_file(str(app_path)).run()

    assert not app.exception
    assert [button.label for button in app.sidebar.button] == [
        "New chat", "What is the CHECKOUT-5XX threshold?", "🗑", "Delete all chats",
    ]
    assert app.session_state["active_chat_id"] == chat_id

    app.sidebar.button[0].click().run()
    assert app.session_state["messages"] == []

    app.sidebar.button[1].click().run()
    assert app.session_state["active_chat_id"] == chat_id
    assert app.session_state["messages"][0]["content"] == "What is the CHECKOUT-5XX threshold?"


def test_delete_active_chat_requires_confirmation_and_clears_it(tmp_path, monkeypatch) -> None:
    directory = tmp_path / "chats"
    store = ChatHistoryStore(directory)
    chat_id = store.save_chat([{"role": "user", "content": "Old incident"}])
    monkeypatch.setenv("INCIDENT_CHAT_HISTORY_DIR", str(directory))
    app_path = Path(__file__).parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run()

    next(button for button in app.sidebar.button if button.key == f"delete_{chat_id}").click().run()
    assert store.load_chat(chat_id) is not None
    assert app.session_state["pending_chat_delete"] == chat_id

    next(button for button in app.sidebar.button if button.label == "Confirm delete").click().run()
    assert store.load_chat(chat_id) is None
    assert app.session_state["active_chat_id"] is None
    assert app.session_state["messages"] == []


def test_delete_all_chats_can_be_cancelled_or_confirmed(tmp_path, monkeypatch) -> None:
    directory = tmp_path / "chats"
    store = ChatHistoryStore(directory)
    store.save_chat([{"role": "user", "content": "First incident"}])
    store.save_chat([{"role": "user", "content": "Second incident"}])
    monkeypatch.setenv("INCIDENT_CHAT_HISTORY_DIR", str(directory))
    app_path = Path(__file__).parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run()

    next(button for button in app.sidebar.button if button.label == "Delete all chats").click().run()
    assert len(store.list_chats()) == 2
    next(button for button in app.sidebar.button if button.label == "Cancel").click().run()
    assert len(store.list_chats()) == 2

    next(button for button in app.sidebar.button if button.label == "Delete all chats").click().run()
    next(button for button in app.sidebar.button if button.label == "Confirm delete").click().run()
    assert store.list_chats() == []
    assert app.session_state["active_chat_id"] is None
    assert app.session_state["messages"] == []
