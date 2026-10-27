import time
from collections import defaultdict, deque

from app.exceptions.exception import TooManyRequestsError


class RateLimiter:
    """Small in-memory sliding-window limiter.

    Good enough for a single server process. If you run several workers or servers, back this with Redis.
    """

    def __init__(self, limit: int, window_seconds: int, message: str):
        self.limit = limit
        self.window = window_seconds
        self.message = message
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def hit(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            raise TooManyRequestsError(self.message)
        hits.append(now)

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)

    def clear(self) -> None:
        self._hits.clear()


login_limiter = RateLimiter(10, 15 * 60, "Too many login attempts. Try again in a few minutes.")
email_limiter = RateLimiter(5, 60 * 60, "Too many requests for this email address. Try again later.")
register_limiter = RateLimiter(10, 60 * 60, "Too many sign-ups from this network. Try again later.")

ALL_LIMITERS = (login_limiter, email_limiter, register_limiter)
