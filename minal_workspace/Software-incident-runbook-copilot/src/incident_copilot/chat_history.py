from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


CHAT_ID_PATTERN = re.compile(r"[0-9a-f]{32}\Z")


class ChatHistoryStore:
    """Persist this local prototype's chat transcripts as JSON files."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def list_chats(self) -> list[dict[str, str]]:
        if not self.directory.exists():
            return []
        chats = []
        for path in self.directory.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("id") != path.stem or not CHAT_ID_PATTERN.fullmatch(path.stem):
                    continue
                chats.append({
                    "id": data["id"],
                    "title": data["title"],
                    "updated_at": data["updated_at"],
                })
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                continue
        return sorted(chats, key=lambda chat: chat["updated_at"], reverse=True)

    def load_chat(self, chat_id: str) -> dict[str, object] | None:
        path = self._path(chat_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("id") != chat_id or not isinstance(data.get("messages"), list):
            raise ValueError("Invalid saved chat")
        return data

    def save_chat(self, messages: list[dict[str, object]], chat_id: str | None = None) -> str:
        chat_id = chat_id or uuid4().hex
        path = self._path(chat_id)
        previous = self.load_chat(chat_id) if path.exists() else None
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "id": chat_id,
            "title": _chat_title(messages),
            "created_at": previous["created_at"] if previous else now,
            "updated_at": now,
            "messages": messages,
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.directory,
                                             prefix=f".{chat_id}-", suffix=".tmp", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                json.dump(data, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n")
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return chat_id

    def delete_chat(self, chat_id: str) -> bool:
        path = self._path(chat_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def delete_all_chats(self) -> int:
        chat_ids = [chat["id"] for chat in self.list_chats()]
        return sum(self.delete_chat(chat_id) for chat_id in chat_ids)

    def _path(self, chat_id: str) -> Path:
        if not CHAT_ID_PATTERN.fullmatch(chat_id):
            raise ValueError("Invalid chat ID")
        return self.directory / f"{chat_id}.json"


def _chat_title(messages: list[dict[str, object]]) -> str:
    first_prompt = next((str(message.get("content", "")) for message in messages
                         if message.get("role") == "user" and str(message.get("content", "")).strip()), "New chat")
    title = " ".join(first_prompt.split())
    return title[:61] + "…" if len(title) > 64 else title
