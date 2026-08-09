"""Abuse controls for issuing short-lived guest access sessions."""

from __future__ import annotations

import asyncio
import time


class GuestSessionRateLimiter:
    """Small in-process sliding-window limiter keyed by the peer address.

    PowerfulTS currently runs one backend process in production. Keeping this
    limiter local avoids adding a distributed cache solely for guest access;
    deployments with multiple workers should replace it with a shared limiter.
    """

    def __init__(self, *, max_requests: int = 20, window_seconds: float = 3600) -> None:
        if max_requests < 1 or window_seconds <= 0:
            raise ValueError("guest session rate-limit values must be positive")
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: dict[str, tuple[float, ...]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window_seconds
        async with self._lock:
            active_requests = {
                request_key: tuple(value for value in values if value > cutoff)
                for request_key, values in self._requests.items()
            }
            active_requests = {
                request_key: values
                for request_key, values in active_requests.items()
                if values
            }
            recent = active_requests.get(key, ())
            if len(recent) >= self._max_requests:
                self._requests = {**active_requests, key: recent}
                return False
            self._requests = {**active_requests, key: (*recent, now)}
            return True
