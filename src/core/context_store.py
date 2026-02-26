from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import sqlite3
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ConversationTurn:
    role: str
    content: str
    images: list[str] | None = None


class ContextStore(Protocol):
    def get_turns(self, user_id: int) -> list[ConversationTurn]: ...

    def append(self, user_id: int, role: str, content: str) -> None: ...

    def clear(self, user_id: int) -> None: ...


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


class SQLiteContextStore:
    def __init__(self, db_path: str, max_turns: int) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._max_turns = max_turns
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=5)

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversation_turns_user_id ON conversation_turns(user_id, id)"
            )
            connection.commit()

    def get_turns(self, user_id: int) -> list[ConversationTurn]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content
                FROM conversation_turns
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, self._max_turns),
            ).fetchall()

        ordered_rows = list(reversed(rows))
        return [ConversationTurn(role=str(role), content=str(content)) for role, content in ordered_rows]

    def append(self, user_id: int, role: str, content: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO conversation_turns (user_id, role, content) VALUES (?, ?, ?)",
                (user_id, role, content),
            )
            connection.execute(
                """
                DELETE FROM conversation_turns
                WHERE user_id = ?
                  AND id NOT IN (
                    SELECT id
                    FROM conversation_turns
                    WHERE user_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                  )
                """,
                (user_id, user_id, self._max_turns),
            )
            connection.commit()

    def clear(self, user_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM conversation_turns WHERE user_id = ?", (user_id,))
            connection.commit()
