from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable

from .models import ClientConfig


class RequestThrottle:
    def __init__(
        self,
        *,
        min_seconds: float = 0.0,
        max_seconds: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.min_seconds = max(0.0, float(min_seconds))
        self.max_seconds = max(self.min_seconds, float(max_seconds))
        self._sleep = sleep
        self._monotonic = monotonic
        self._uniform = uniform
        self._lock = threading.Lock()
        self._next_request_at: float | None = None

    @classmethod
    def from_config(cls, config: ClientConfig) -> "RequestThrottle":
        return cls(
            min_seconds=config.request_delay_min_seconds,
            max_seconds=config.request_delay_max_seconds,
        )

    @property
    def enabled(self) -> bool:
        return self.max_seconds > 0.0

    def wait(self) -> None:
        if not self.enabled:
            return

        sleep_seconds = 0.0
        with self._lock:
            now = self._monotonic()
            if self._next_request_at is None:
                scheduled_at = now
            else:
                scheduled_at = max(now, self._next_request_at)
                sleep_seconds = scheduled_at - now
            self._next_request_at = scheduled_at + self._next_delay()

        if sleep_seconds > 0:
            self._sleep(sleep_seconds)

    def _next_delay(self) -> float:
        if self.min_seconds == self.max_seconds:
            return self.min_seconds
        return self._uniform(self.min_seconds, self.max_seconds)
