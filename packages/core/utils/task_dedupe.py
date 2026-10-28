"""Remember which tasks this instance has already accepted.

Cloud Tasks may deliver the same task more than once (e.g. when the
dispatch deadline passes while the first run is still translating).
Without this guard, a long novel gets translated — and billed — twice.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class TaskDeduper:
    """In-memory set of seen task IDs that expire after ``ttl_seconds``."""

    def __init__(
        self,
        *,
        ttl_seconds: float = 6 * 3600,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def try_start(self, task_id: str) -> bool:
        """Return True the first time ``task_id`` is seen, False on repeats."""
        now = self._clock()
        with self._lock:
            self._seen = {k: t for k, t in self._seen.items() if now - t < self._ttl}
            if task_id in self._seen:
                return False
            self._seen[task_id] = now
            return True
