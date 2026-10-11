"""Phase 3 session: vault + masked history, RAM only.

History holds MASKED text only. clear() wipes vault and history.
"""
from __future__ import annotations

from typing import Any

from memory.manager import MemoryManager
from privacy.vault import Vault


class Session:
    def __init__(self, config: Any, db_path: str) -> None:
        self.vault = Vault()
        self.manager = MemoryManager(db_path=db_path)
        self.max_history = max(0, int(config["session"].get("history_messages", 6)))
        self._history: list[dict] = []

    def add_exchange(self, user_clean: str, reply_masked: str) -> None:
        """Store one masked user message and the masked reply, then trim."""
        self._history.append({"role": "user", "content": user_clean})
        self._history.append({"role": "assistant", "content": reply_masked})
        self._trim()

    def history_messages(self) -> list[dict]:
        """Copy of the last N masked messages (never raw text)."""
        return [dict(m) for m in self._history]

    def _trim(self) -> None:
        if self.max_history == 0:
            self._history.clear()
            return
        self._history = self._history[-self.max_history:]
        if self._history and self._history[0]["role"] == "assistant":
            self._history.pop(0)  # keep the window starting with a user turn

    def clear(self) -> None:
        self.vault.clear()
        self._history.clear()

    def close(self) -> None:
        self.clear()
        self.manager.close()