"""Tests for duplicate task protection (Cloud Tasks re-dispatch)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api_server.main import create_app
from packages.core.domain.models import SendNovelResult
from packages.core.utils.task_dedupe import TaskDeduper


# ── TaskDeduper ───────────────────────────────────────


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_first_start_is_allowed() -> None:
    d = TaskDeduper()
    assert d.try_start("req-1") is True


def test_same_id_is_rejected() -> None:
    d = TaskDeduper()
    d.try_start("req-1")
    assert d.try_start("req-1") is False


def test_different_ids_are_independent() -> None:
    d = TaskDeduper()
    d.try_start("req-1")
    assert d.try_start("req-2") is True


def test_id_is_forgotten_after_ttl() -> None:
    clock = FakeClock()
    d = TaskDeduper(ttl_seconds=100, clock=clock)
    d.try_start("req-1")
    clock.now = 101
    assert d.try_start("req-1") is True


# ── /internal/tasks/execute ───────────────────────────


@pytest.fixture()
def client():
    from apps.api_server.dependencies import (
        get_pixiv_to_kindle_service,
        get_settings,
        get_task_deduper,
    )
    from packages.core.config import Settings

    app = create_app()
    settings = MagicMock(spec=Settings)
    settings.internal_api_token = "tok"
    service = MagicMock()
    service.execute = AsyncMock(
        return_value=SendNovelResult(success=True, title="t", novel_id=1, message="ok")
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_pixiv_to_kindle_service] = lambda: service
    deduper = TaskDeduper()
    app.dependency_overrides[get_task_deduper] = lambda: deduper
    c = TestClient(app)
    c.service = service  # type: ignore[attr-defined]
    return c


_PAYLOAD = {"request_id": "req-1", "command": {"novel_input": "123", "translate": True}}


def test_redelivered_task_is_not_executed_twice(client) -> None:
    headers = {"X-Internal-Token": "tok"}
    r1 = client.post("/internal/tasks/execute", json=_PAYLOAD, headers=headers)
    r2 = client.post("/internal/tasks/execute", json=_PAYLOAD, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200  # 2xx so Cloud Tasks stops retrying
    assert r2.json()["duplicate"] is True
    assert client.service.execute.await_count == 1


def test_bad_token_does_not_consume_request_id(client) -> None:
    client.post("/internal/tasks/execute", json=_PAYLOAD, headers={"X-Internal-Token": "bad"})
    r = client.post("/internal/tasks/execute", json=_PAYLOAD, headers={"X-Internal-Token": "tok"})
    assert r.json().get("duplicate") is not True
    assert client.service.execute.await_count == 1


# ── Cloud Tasks dispatch deadline ─────────────────────


def test_cloud_tasks_sets_dispatch_deadline() -> None:
    from packages.core.domain.value_objects import CommandPayload, TaskPayload

    with patch("packages.core.queue.cloud_tasks.tasks_v2.CloudTasksClient") as client_cls:
        from packages.core.queue.cloud_tasks import CloudTasksQueue

        q = CloudTasksQueue(
            project_id="p",
            location="l",
            queue_name="q",
            task_handler_url="https://x/internal/tasks/execute",
            internal_api_token="tok",
            dispatch_deadline_seconds=1800,
        )
        import asyncio

        asyncio.run(
            q.enqueue_send_novel(
                TaskPayload(request_id="r", command=CommandPayload(novel_input="1"))
            )
        )
        task = client_cls.return_value.create_task.call_args.kwargs["task"]
        assert task.dispatch_deadline.total_seconds() == 1800
