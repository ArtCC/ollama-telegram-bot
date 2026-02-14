from __future__ import annotations

import sqlite3
from pathlib import Path


class ModelPreferencesStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=5)

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_model_preferences (
                    user_id INTEGER PRIMARY KEY,
                    model_name TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()

    def get_user_model(self, user_id: int) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT model_name FROM user_model_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            return str(row[0])

    def set_user_model(self, user_id: int, model_name: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO user_model_preferences (user_id, model_name)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    model_name = excluded.model_name,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (user_id, model_name),
            )
            connection.commit()
