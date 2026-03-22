"""Per-user in-memory session state with automatic TTL cleanup."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class _Entry:
    """Single user's transient session data."""

    model_search_query: str = ""
    web_model_search_query: str = ""
    web_model_search_mode: bool = False
    web_search_mode: bool = False
    askfile_target: int | None = None
    upload_mode: bool = False
    last_active: float = field(default_factory=time.monotonic)


class UserSessionStore:
    """Manages per-user session flags with TTL-based eviction.

    Replaces the scattered ``dict[int, …]`` / ``set[int]`` fields that
    previously lived in ``BotHandlers``.
    """

    __slots__ = ("_sessions", "_ttl")

    def __init__(self, ttl_seconds: float = 3600.0) -> None:
        self._sessions: dict[int, _Entry] = {}
        self._ttl = ttl_seconds

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, user_id: int) -> _Entry:
        entry = self._sessions.get(user_id)
        if entry is None:
            entry = _Entry()
            self._sessions[user_id] = entry
        entry.last_active = time.monotonic()
        return entry

    def _get_if_exists(self, user_id: int) -> _Entry | None:
        entry = self._sessions.get(user_id)
        if entry is not None:
            entry.last_active = time.monotonic()
        return entry

    # ------------------------------------------------------------------
    # Model search query
    # ------------------------------------------------------------------

    def get_model_search_query(self, user_id: int) -> str:
        entry = self._get_if_exists(user_id)
        return entry.model_search_query if entry else ""

    def set_model_search_query(self, user_id: int, query: str) -> None:
        self._get(user_id).model_search_query = query

    def clear_model_search_query(self, user_id: int) -> None:
        entry = self._get_if_exists(user_id)
        if entry:
            entry.model_search_query = ""

    # ------------------------------------------------------------------
    # Web model search query
    # ------------------------------------------------------------------

    def get_web_model_search_query(self, user_id: int) -> str:
        entry = self._get_if_exists(user_id)
        return entry.web_model_search_query if entry else ""

    def set_web_model_search_query(self, user_id: int, query: str) -> None:
        self._get(user_id).web_model_search_query = query

    def clear_web_model_search_query(self, user_id: int) -> None:
        entry = self._get_if_exists(user_id)
        if entry:
            entry.web_model_search_query = ""

    # ------------------------------------------------------------------
    # Mode flags
    # ------------------------------------------------------------------

    def is_web_model_search_mode(self, user_id: int) -> bool:
        entry = self._get_if_exists(user_id)
        return entry.web_model_search_mode if entry else False

    def set_web_model_search_mode(self, user_id: int, value: bool) -> None:
        self._get(user_id).web_model_search_mode = value

    def is_web_search_mode(self, user_id: int) -> bool:
        entry = self._get_if_exists(user_id)
        return entry.web_search_mode if entry else False

    def set_web_search_mode(self, user_id: int, value: bool) -> None:
        self._get(user_id).web_search_mode = value

    def is_upload_mode(self, user_id: int) -> bool:
        entry = self._get_if_exists(user_id)
        return entry.upload_mode if entry else False

    def set_upload_mode(self, user_id: int, value: bool) -> None:
        self._get(user_id).upload_mode = value

    # ------------------------------------------------------------------
    # Ask-file target
    # ------------------------------------------------------------------

    def get_askfile_target(self, user_id: int) -> int | None:
        entry = self._get_if_exists(user_id)
        return entry.askfile_target if entry else None

    def set_askfile_target(self, user_id: int, asset_id: int) -> None:
        self._get(user_id).askfile_target = asset_id

    def pop_askfile_target(self, user_id: int) -> int | None:
        entry = self._get_if_exists(user_id)
        if entry is None:
            return None
        val = entry.askfile_target
        entry.askfile_target = None
        return val

    # ------------------------------------------------------------------
    # Cancel all modes for a user
    # ------------------------------------------------------------------

    def clear_all(self, user_id: int) -> dict[str, bool]:
        """Reset every mode/flag for *user_id*. Returns what was active."""
        entry = self._get_if_exists(user_id)
        if entry is None:
            return {
                "upload_mode": False,
                "web_model_search_mode": False,
                "web_search_mode": False,
                "askfile_target": False,
            }
        status = {
            "upload_mode": entry.upload_mode,
            "web_model_search_mode": entry.web_model_search_mode,
            "web_search_mode": entry.web_search_mode,
            "askfile_target": entry.askfile_target is not None,
        }
        entry.upload_mode = False
        entry.web_model_search_mode = False
        entry.web_search_mode = False
        entry.askfile_target = None
        return status

    # ------------------------------------------------------------------
    # TTL cleanup
    # ------------------------------------------------------------------

    def purge_expired(self) -> int:
        """Remove entries older than *ttl_seconds*. Returns count purged."""
        now = time.monotonic()
        expired = [
            uid
            for uid, e in self._sessions.items()
            if now - e.last_active > self._ttl
        ]
        for uid in expired:
            del self._sessions[uid]
        return len(expired)

    def __len__(self) -> int:
        return len(self._sessions)
