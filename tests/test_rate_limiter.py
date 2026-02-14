from src.core.rate_limiter import SlidingWindowRateLimiter


def test_rate_limiter_blocks_after_limit() -> None:
    now = 100.0

    def now_provider() -> float:
        return now

    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=30, now_provider=now_provider)

    assert limiter.allow(123) is True
    assert limiter.allow(123) is True
    assert limiter.allow(123) is False


def test_rate_limiter_resets_after_window() -> None:
    now = 100.0

    def now_provider() -> float:
        return now

    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=30, now_provider=now_provider)

    assert limiter.allow(123) is True
    assert limiter.allow(123) is True
    assert limiter.allow(123) is False

    now = 131.0

    assert limiter.allow(123) is True


def test_rate_limiter_is_per_user() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=30, now_provider=lambda: 100.0)

    assert limiter.allow(1) is True
    assert limiter.allow(1) is False
    assert limiter.allow(2) is True
