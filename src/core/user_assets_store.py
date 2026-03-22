from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
import threading

logger = logging.getLogger(__name__)


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
    _SCHEMA_VERSION = 3

    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, timeout=5)
            self._local.conn = conn
        return conn

    def _get_schema_version(self, connection: sqlite3.Connection) -> int:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_versions "
            "(table_name TEXT PRIMARY KEY, version INTEGER NOT NULL)"
        )
        row = connection.execute(
            "SELECT version FROM schema_versions WHERE table_name = 'user_assets'"
        ).fetchone()
        return int(row[0]) if row else 0

    def _set_schema_version(self, connection: sqlite3.Connection, version: int) -> None:
        connection.execute(
            "INSERT INTO schema_versions (table_name, version) VALUES ('user_assets', ?) "
            "ON CONFLICT(table_name) DO UPDATE SET version = excluded.version",
            (version,),
        )

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

            current_version = self._get_schema_version(connection)

            if current_version < 1:
                # Migration v1: add content_hash and image_base64 columns
                cols = {row[1] for row in connection.execute("PRAGMA table_info(user_assets)")}
                if "content_hash" not in cols:
                    connection.execute(
                        "ALTER TABLE user_assets ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''"
                    )
                    connection.execute(
                        "CREATE INDEX IF NOT EXISTS idx_user_assets_content_hash "
                        "ON user_assets(user_id, content_hash)"
                    )
                if "image_base64" not in cols:
                    connection.execute(
                        "ALTER TABLE user_assets ADD COLUMN image_base64 TEXT NOT NULL DEFAULT ''"
                    )
                logger.info("user_assets_store migration_applied version=1")

            if current_version < 2:
                # Migration v2: add index on created_at for TTL purge
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_user_assets_created_at "
                    "ON user_assets(created_at)"
                )
                logger.info("user_assets_store migration_applied version=2")

            if current_version < 3:
                # Migration v3: FTS5 virtual table for full-text search
                connection.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS user_assets_fts "
                    "USING fts5(content_text, content='user_assets', content_rowid='id')"
                )
                # Populate FTS index from existing rows
                connection.execute(
                    "INSERT OR IGNORE INTO user_assets_fts(rowid, content_text) "
                    "SELECT id, content_text FROM user_assets"
                )
                logger.info("user_assets_store migration_applied version=3")

            self._set_schema_version(connection, self._SCHEMA_VERSION)
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
            new_id = int(cursor.lastrowid)
            # Keep FTS index in sync
            connection.execute(
                "INSERT INTO user_assets_fts(rowid, content_text) VALUES (?, ?)",
                (new_id, content_text),
            )
            connection.commit()
            return new_id

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
            if cursor.rowcount > 0:
                # Keep FTS index in sync
                connection.execute(
                    "INSERT INTO user_assets_fts(user_assets_fts, rowid, content_text) "
                    "VALUES('delete', ?, '')",
                    (asset_id,),
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
            # Use FTS5 for fast full-text ranking when available
            fts_ranked_ids: list[int] | None = None
            fts_query = " OR ".join(tokens)
            try:
                with self._connect() as connection:
                    rows = connection.execute(
                        "SELECT rowid FROM user_assets_fts WHERE user_assets_fts MATCH ? "
                        "ORDER BY rank LIMIT ?",
                        (fts_query, limit * 3),
                    ).fetchall()
                    fts_ranked_ids = [int(r[0]) for r in rows]
            except Exception:
                fts_ranked_ids = None

            if fts_ranked_ids is not None:
                asset_by_id = {a.id: a for a in assets}
                # Preserve FTS rank order, then fill with remaining assets
                scored_assets = [asset_by_id[aid] for aid in fts_ranked_ids if aid in asset_by_id]
                seen = set(fts_ranked_ids)
                remaining = [a for a in assets if a.id not in seen]
                selected_assets = (scored_assets + remaining)[:limit]
            else:
                # Fallback: in-memory scoring
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
                selected_assets = [item[1] for item in scored[:limit]]
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
        return [token for token in re.findall(r"\w+", text.lower()) if len(token) >= 2]

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
