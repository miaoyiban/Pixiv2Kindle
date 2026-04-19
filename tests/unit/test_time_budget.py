"""Tests for packages.core.utils.time_budget."""

import time

from packages.core.utils.time_budget import (
    calculate_followup_deadline,
    is_within_deadline,
    remaining_seconds,
)


class TestTimeBudget:
    def test_calculate_deadline(self) -> None:
        now_ms = int(time.time() * 1000)
        deadline = calculate_followup_deadline(now_ms, soft_seconds=720)
        assert deadline == now_ms + 720_000

    def test_within_deadline_true(self) -> None:
        future = int(time.time() * 1000) + 60_000
        assert is_within_deadline(future) is True

    def test_within_deadline_false(self) -> None:
        past = int(time.time() * 1000) - 1000
        assert is_within_deadline(past) is False

    def test_remaining_seconds_positive(self) -> None:
        future = int(time.time() * 1000) + 30_000
        remaining = remaining_seconds(future)
        assert 29.0 <= remaining <= 31.0

    def test_remaining_seconds_past(self) -> None:
        past = int(time.time() * 1000) - 10_000
        assert remaining_seconds(past) == 0.0
