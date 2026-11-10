"""Per-user token-bucket rate limiting (per instance).

Cloud Run may run several instances, so the effective limit is ``limit x instances``; this guards
against runaway clients and accidental loops, not determined abuse (use Cloud Armor / API
Gateway for that).
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from receipt_api.auth import CurrentUser, get_current_user


class TokenBucketLimiter:
    def __init__(self, per_minute: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.capacity = float(per_minute)
        self.rate = per_minute / 60.0
        self._clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str) -> float:
        """Take a token; return 0 if allowed, else seconds until one is available."""
        now = self._clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                return 0.0
            self._buckets[key] = (tokens, now)
            return (1 - tokens) / self.rate


LIMITERS: dict[str, TokenBucketLimiter] = {
    "upload": TokenBucketLimiter(30),
    "review_write": TokenBucketLimiter(60),
    "analytics": TokenBucketLimiter(60),
    "read": TokenBucketLimiter(300),
}


def rate_limit(name: str) -> Callable[[CurrentUser], CurrentUser]:
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:  # noqa: B008
        wait = LIMITERS[name].acquire(user.uid)
        if wait > 0:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many requests. Please slow down.",
                headers={"Retry-After": str(math.ceil(wait))},
            )
        return user

    return dependency
