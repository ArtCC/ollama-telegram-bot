"""Tests for UserSessionStore."""

from __future__ import annotations

import time
from unittest.mock import patch

from src.core.user_session import UserSessionStore


def test_session_get_set_model_search_query() -> None:
    store = UserSessionStore()
    assert store.get_model_search_query(1) == ""

    store.set_model_search_query(1, "llama")
    assert store.get_model_search_query(1) == "llama"

    store.clear_model_search_query(1)
    assert store.get_model_search_query(1) == ""


def test_session_get_set_web_model_search_query() -> None:
    store = UserSessionStore()
    store.set_web_model_search_query(1, "gemma")
    assert store.get_web_model_search_query(1) == "gemma"

    store.clear_web_model_search_query(1)
    assert store.get_web_model_search_query(1) == ""


def test_session_mode_flags() -> None:
    store = UserSessionStore()
    assert store.is_web_model_search_mode(1) is False
    assert store.is_web_search_mode(1) is False
    assert store.is_upload_mode(1) is False

    store.set_web_model_search_mode(1, True)
    assert store.is_web_model_search_mode(1) is True

    store.set_web_search_mode(1, True)
    assert store.is_web_search_mode(1) is True

    store.set_upload_mode(1, True)
    assert store.is_upload_mode(1) is True

    store.set_upload_mode(1, False)
    assert store.is_upload_mode(1) is False


def test_session_askfile_target() -> None:
    store = UserSessionStore()
    assert store.get_askfile_target(1) is None

    store.set_askfile_target(1, 42)
    assert store.get_askfile_target(1) == 42

    val = store.pop_askfile_target(1)
    assert val == 42
    assert store.get_askfile_target(1) is None

    # Pop when nothing set
    assert store.pop_askfile_target(999) is None


def test_session_clear_all_returns_previous_state() -> None:
    store = UserSessionStore()
    store.set_upload_mode(1, True)
    store.set_web_model_search_mode(1, True)
    store.set_askfile_target(1, 10)

    prev = store.clear_all(1)
    assert prev["upload_mode"] is True
    assert prev["web_model_search_mode"] is True
    assert prev["askfile_target"] is True

    # After clear, all modes are off
    assert store.is_upload_mode(1) is False
    assert store.is_web_model_search_mode(1) is False
    assert store.get_askfile_target(1) is None


def test_session_clear_all_nonexistent_user() -> None:
    store = UserSessionStore()
    prev = store.clear_all(999)
    assert all(v is False for v in prev.values())


def test_session_purge_expired() -> None:
    store = UserSessionStore(ttl_seconds=10.0)

    base = 1000.0
    with patch("src.core.user_session.time.monotonic", return_value=base):
        store.set_upload_mode(1, True)

    with patch("src.core.user_session.time.monotonic", return_value=base + 5):
        store.set_upload_mode(2, True)

    # At base + 12, user 1 has expired (12 > 10), user 2 has not (7 < 10)
    with patch("src.core.user_session.time.monotonic", return_value=base + 12):
        purged = store.purge_expired()

    assert purged == 1
    assert len(store) == 1
    # User 2 still present
    with patch("src.core.user_session.time.monotonic", return_value=base + 12):
        assert store.is_upload_mode(2) is True


def test_session_per_user_isolation() -> None:
    store = UserSessionStore()
    store.set_model_search_query(1, "alpha")
    store.set_model_search_query(2, "beta")

    assert store.get_model_search_query(1) == "alpha"
    assert store.get_model_search_query(2) == "beta"


def test_session_len() -> None:
    store = UserSessionStore()
    assert len(store) == 0

    store.set_upload_mode(1, True)
    assert len(store) == 1

    store.set_upload_mode(2, True)
    assert len(store) == 2
