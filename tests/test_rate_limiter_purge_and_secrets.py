"""Tests for rate limiter purge_inactive and SecretFilter."""

from __future__ import annotations

import logging

from src.core.rate_limiter import SlidingWindowRateLimiter
from src.utils.logging import SecretFilter


def test_purge_inactive_removes_stale_users() -> None:
    now = 1000.0

    def now_provider() -> float:
        return now

    limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60, now_provider=now_provider)

    limiter.allow(1)
    limiter.allow(2)

    now = 2000.0  # 1000 seconds later
    limiter.allow(3)  # Recent user

    purged = limiter.purge_inactive(max_idle_seconds=500.0)
    assert purged == 2  # Users 1 and 2 are stale

    # User 3 still active
    assert limiter.allow(3) is True


def test_purge_inactive_returns_zero_when_all_active() -> None:
    now = 100.0
    limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60, now_provider=lambda: now)

    limiter.allow(1)
    limiter.allow(2)

    purged = limiter.purge_inactive(max_idle_seconds=500.0)
    assert purged == 0


def test_secret_filter_redacts_bearer_token() -> None:
    f = SecretFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="Got token Bearer abc123xyz in header",
        args=(), exc_info=None,
    )
    f.filter(record)
    assert "abc123xyz" not in record.msg
    assert "***" in record.msg


def test_secret_filter_redacts_api_key() -> None:
    f = SecretFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg='Config api_key=secret_value_here',
        args=(), exc_info=None,
    )
    f.filter(record)
    assert "secret_value_here" not in record.msg


def test_secret_filter_preserves_normal_messages() -> None:
    f = SecretFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="Normal log message with no secrets",
        args=(), exc_info=None,
    )
    f.filter(record)
    assert record.msg == "Normal log message with no secrets"
