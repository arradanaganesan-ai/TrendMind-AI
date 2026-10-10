"""Simple in-memory sliding-window rate limiter for expensive endpoints.

Single-process only (documented limitation). No external dependencies.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    """Allows at most `limit` events per `window_seconds` per key."""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = max(1, limit)
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Returns (allowed, seconds_until_next_slot)."""
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - self.window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) < self.limit:
                bucket.append(now)
                return True, 0

            retry_after = int(self.window_seconds - (now - bucket[0])) + 1
            return False, max(1, retry_after)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
