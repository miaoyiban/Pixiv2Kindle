"""Abstract task queue protocol.

Concrete implementations:
  - ``LocalBackgroundQueue`` (M1 – in-process asyncio task)
  - ``CloudTasksQueue``      (M2 – GCP Cloud Tasks)

Spec reference: §17.4.
"""

from __future__ import annotations

from typing import Protocol

from packages.core.domain.value_objects import TaskPayload


class TaskQueue(Protocol):
    """Enqueue a pixiv-to-kindle task for asynchronous execution."""

    async def enqueue_send_novel(self, payload: TaskPayload) -> None:
        """Accept *payload* for background processing.

        The implementation decides whether the work happens in-process
        (local) or via an external queue (Cloud Tasks).
        """
        ...
