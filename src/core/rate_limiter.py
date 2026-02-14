from __future__ import annotations

from collections import deque
from time import monotonic
from typing import Callable


class SlidingWindowRateLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        now_provider: Callable[[], float] | None = None,
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests must be >= 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be >= 1")

        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._now_provider = now_provider or monotonic
        self._events_by_user: dict[int, deque[float]] = {}

    def allow(self, user_id: int) -> bool:
        now = self._now_provider()
        window_start = now - self._window_seconds

        events = self._events_by_user.setdefault(user_id, deque())
        while events and events[0] <= window_start:
            events.popleft()

        if len(events) >= self._max_requests:
            return False

        events.append(now)
        return True
