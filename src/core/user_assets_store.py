from __future__ import annotations

import hashlib
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
    image_base64: str = ""


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
            # Schema migration: add content_hash column for deduplication
            try:
                connection.execute(
                    "ALTER TABLE user_assets ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_user_assets_content_hash "
                    "ON user_assets(user_id, content_hash)"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
            # Schema migration: add image_base64 column for image RAG replay
            try:
                connection.execute(
                    "ALTER TABLE user_assets ADD COLUMN image_base64 TEXT NOT NULL DEFAULT ''"
                )
            except sqlite3.OperationalError:
                pass  # Column already exists
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
        image_base64: str = "",
    ) -> int:
        content_hash = self._compute_hash(content_text)
        with self._connect() as connection:
            # Deduplication: return existing asset ID if content already stored
            existing = connection.execute(
                "SELECT id FROM user_assets WHERE user_id = ? AND content_hash = ? LIMIT 1",
                (user_id, content_hash),
            ).fetchone()
            if existing:
                return int(existing[0])
            cursor = connection.execute(
                """
                INSERT INTO user_assets (
                    user_id,
                    asset_kind,
                    asset_name,
                    mime_type,
                    size_bytes,
                    content_text,
                    is_selected,
                    content_hash,
                    image_base64
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    asset_kind,
                    asset_name,
                    mime_type,
                    size_bytes,
                    content_text,
                    1 if is_selected else 0,
                    content_hash,
                    image_base64,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_assets(self, user_id: int) -> list[UserAsset]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, asset_kind, asset_name, mime_type, size_bytes, content_text, is_selected, created_at, updated_at, image_base64
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
                SELECT id, user_id, asset_kind, asset_name, mime_type, size_bytes, content_text, is_selected, created_at, updated_at, image_base64
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

    def purge_expired_assets(self, ttl_days: int) -> int:
        """Delete assets older than ttl_days days. Returns number of deleted rows."""
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM user_assets WHERE datetime(created_at) < datetime('now', ?)",
                (f"-{ttl_days} days",),
            )
            connection.commit()
            return cursor.rowcount

    def search_selected_assets(
        self,
        *,
        user_id: int,
        query: str,
        limit: int,
        max_chars_total: int,
        asset_kinds: set[str] | None = None,
    ) -> list[UserAsset]:
        assets = [
            asset for asset in self.list_assets(user_id)
            if asset.is_selected
            and asset.content_text.strip()
            and (asset_kinds is None or asset.asset_kind in asset_kinds)
        ]
        if not assets:
            return []

        tokens = self._tokenize(query)
        if tokens:
            scored: list[tuple[int, UserAsset]] = []
            unscored: list[UserAsset] = []
            for asset in assets:
                lowered = asset.content_text.lower()
                score = sum(lowered.count(token) for token in tokens)
                if score > 0:
                    scored.append((score, asset))
                else:
                    unscored.append(asset)
            scored.sort(key=lambda item: (item[0], item[1].id), reverse=True)
            selected_assets: list[UserAsset] = [item[1] for item in scored[:limit]]
            # Fill remaining slots with unscored assets (recency order)
            remaining_slots = limit - len(selected_assets)
            if remaining_slots > 0:
                selected_assets.extend(unscored[:remaining_slots])
        else:
            selected_assets = assets[:limit]

        # Budget: allocate proportionally based on actual asset count (not limit cap)
        actual_count = len(selected_assets)
        total = 0
        clipped: list[UserAsset] = []
        per_asset_cap = max(800, max_chars_total // max(1, actual_count))
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
                    image_base64=asset.image_base64,
                )
            )
            total += len(text)

        return clipped

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token for token in re.findall(r"\w+", text.lower()) if len(token) >= 3]

    @staticmethod
    def _compute_hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

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
            image_base64=str(row[10]) if len(row) > 10 else "",
        )
