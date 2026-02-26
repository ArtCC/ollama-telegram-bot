from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3


@dataclass(frozen=True)
class UserAsset:
    id: int
    user_id: int
    asset_kind: str
    asset_name: str
    mime_type: str
    size_bytes: int
    content_text: str
    is_selected: bool
    created_at: str
    updated_at: str


class UserAssetsStore:
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
                CREATE TABLE IF NOT EXISTS user_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    asset_kind TEXT NOT NULL,
                    asset_name TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    content_text TEXT NOT NULL,
                    is_selected INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_assets_user_id_id ON user_assets(user_id, id DESC)"
            )
            connection.commit()

    def add_asset(
        self,
        *,
        user_id: int,
        asset_kind: str,
        asset_name: str,
        mime_type: str,
        size_bytes: int,
        content_text: str,
        is_selected: bool = True,
    ) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO user_assets (
                    user_id,
                    asset_kind,
                    asset_name,
                    mime_type,
                    size_bytes,
                    content_text,
                    is_selected
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    asset_kind,
                    asset_name,
                    mime_type,
                    size_bytes,
                    content_text,
                    1 if is_selected else 0,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_assets(self, user_id: int) -> list[UserAsset]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, asset_kind, asset_name, mime_type, size_bytes, content_text, is_selected, created_at, updated_at
                FROM user_assets
                WHERE user_id = ?
                ORDER BY id DESC
                """,
                (user_id,),
            ).fetchall()
        return [self._to_asset(row) for row in rows]

    def get_asset(self, user_id: int, asset_id: int) -> UserAsset | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, user_id, asset_kind, asset_name, mime_type, size_bytes, content_text, is_selected, created_at, updated_at
                FROM user_assets
                WHERE user_id = ? AND id = ?
                """,
                (user_id, asset_id),
            ).fetchone()
        return self._to_asset(row) if row else None

    def set_selected(self, user_id: int, asset_id: int, selected: bool) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE user_assets
                SET is_selected = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND id = ?
                """,
                (1 if selected else 0, user_id, asset_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def delete_asset(self, user_id: int, asset_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM user_assets WHERE user_id = ? AND id = ?",
                (user_id, asset_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def search_selected_assets(
        self,
        *,
        user_id: int,
        query: str,
        limit: int,
        max_chars_total: int,
    ) -> list[UserAsset]:
        assets = [asset for asset in self.list_assets(user_id) if asset.is_selected and asset.content_text.strip()]
        if not assets:
            return []

        tokens = self._tokenize(query)
        if tokens:
            scored: list[tuple[int, UserAsset]] = []
            for asset in assets:
                lowered = asset.content_text.lower()
                score = sum(lowered.count(token) for token in tokens)
                if score > 0:
                    scored.append((score, asset))
            if scored:
                scored.sort(key=lambda item: (item[0], item[1].id), reverse=True)
                selected_assets = [item[1] for item in scored[:limit]]
            else:
                selected_assets = assets[:limit]
        else:
            selected_assets = assets[:limit]

        total = 0
        clipped: list[UserAsset] = []
        per_asset_cap = max(800, max_chars_total // max(1, limit))
        for asset in selected_assets:
            text = asset.content_text.strip()
            if len(text) > per_asset_cap:
                text = f"{text[:per_asset_cap]}\n\n[...truncated...]"

            remaining = max_chars_total - total
            if remaining <= 0:
                break
            if len(text) > remaining:
                text = f"{text[:remaining]}\n\n[...truncated...]"

            clipped.append(
                UserAsset(
                    id=asset.id,
                    user_id=asset.user_id,
                    asset_kind=asset.asset_kind,
                    asset_name=asset.asset_name,
                    mime_type=asset.mime_type,
                    size_bytes=asset.size_bytes,
                    content_text=text,
                    is_selected=asset.is_selected,
                    created_at=asset.created_at,
                    updated_at=asset.updated_at,
                )
            )
            total += len(text)

        return clipped

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token for token in re.findall(r"\w+", text.lower()) if len(token) >= 3]

    @staticmethod
    def _to_asset(row: tuple[object, ...]) -> UserAsset:
        return UserAsset(
            id=int(row[0]),
            user_id=int(row[1]),
            asset_kind=str(row[2]),
            asset_name=str(row[3]),
            mime_type=str(row[4]),
            size_bytes=int(row[5]),
            content_text=str(row[6]),
            is_selected=bool(int(row[7])),
            created_at=str(row[8]),
            updated_at=str(row[9]),
        )
