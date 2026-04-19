"""Time-budget helpers for Discord follow-up deadline enforcement.

Discord interaction tokens are valid for ~15 minutes.  The system
uses a configurable soft deadline (default 12 min) to decide whether
it can still send a follow-up message.

Spec references: §2.1, §15.2, §15.3.
"""

from __future__ import annotations

import time

from packages.core.exceptions import TimeBudgetExceededError


def calculate_followup_deadline(
    interaction_epoch_ms: int,
    *,
    soft_seconds: int = 720,
) -> int:
    """Return the soft-deadline epoch (milliseconds).

    Parameters
    ----------
    interaction_epoch_ms:
        Unix epoch in **milliseconds** when Discord created the interaction.
    soft_seconds:
        How many seconds after creation we consider "safe" for follow-up.

    Returns
    -------
    int
        Epoch in milliseconds.
    """
    return interaction_epoch_ms + soft_seconds * 1000


def is_within_deadline(deadline_epoch_ms: int) -> bool:
    """Return *True* if the current time is before *deadline_epoch_ms*."""
    now_ms = int(time.time() * 1000)
    return now_ms < deadline_epoch_ms


def ensure_time_budget(deadline_epoch_ms: int) -> None:
    """Raise if there is no time left.

    Should be called at the start of the task handler to bail out
    early on stale tasks.
    """
    if deadline_epoch_ms > 0 and not is_within_deadline(deadline_epoch_ms):
        raise TimeBudgetExceededError("Task has already exceeded follow-up deadline")


def remaining_seconds(deadline_epoch_ms: int) -> float:
    """Return seconds remaining until *deadline_epoch_ms*."""
    now_ms = int(time.time() * 1000)
    return max(0.0, (deadline_epoch_ms - now_ms) / 1000)
