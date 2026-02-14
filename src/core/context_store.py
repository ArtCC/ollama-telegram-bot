from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationTurn:
    role: str
    content: str


class InMemoryContextStore:
    def __init__(self, max_turns: int) -> None:
        self._max_turns = max_turns
        self._store: dict[int, list[ConversationTurn]] = defaultdict(list)

    def get_turns(self, user_id: int) -> list[ConversationTurn]:
        return list(self._store.get(user_id, []))

    def append(self, user_id: int, role: str, content: str) -> None:
        turns = self._store[user_id]
        turns.append(ConversationTurn(role=role, content=content))
        if len(turns) > self._max_turns:
            self._store[user_id] = turns[-self._max_turns :]

    def clear(self, user_id: int) -> None:
        self._store.pop(user_id, None)
