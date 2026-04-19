"""Cloud Tasks queue implementation for GCP Cloud Run deployment.

Creates HTTP tasks that target the Cloud Run ``/internal/tasks/execute``
endpoint.  The task handler runs as a normal HTTP request with full
CPU allocation (no post-response throttling).

Spec references: §14, §17.1, §17.2.
"""

from __future__ import annotations

import json

from google.cloud import tasks_v2
from google.protobuf import timestamp_pb2
from loguru import logger

from packages.core.domain.value_objects import TaskPayload


class CloudTasksQueue:
    """Enqueue tasks via GCP Cloud Tasks."""

    def __init__(
        self,
        *,
        project_id: str,
        location: str,
        queue_name: str,
        task_handler_url: str,
        internal_api_token: str,
    ) -> None:
        self._client = tasks_v2.CloudTasksClient()
        self._parent = self._client.queue_path(project_id, location, queue_name)
        self._handler_url = task_handler_url
        self._internal_token = internal_api_token

    async def enqueue_send_novel(self, payload: TaskPayload) -> None:
        """Create an HTTP task in Cloud Tasks.

        The actual execution happens when Cloud Tasks invokes the
        task handler endpoint on Cloud Run.
        """
        body = json.dumps(payload.model_dump(), ensure_ascii=False).encode("utf-8")

        task = tasks_v2.Task(
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=self._handler_url,
                headers={
                    "Content-Type": "application/json",
                    "X-Internal-Token": self._internal_token,
                },
                body=body,
            ),
        )

        # Cloud Tasks client is synchronous – but calling it is fast
        # (it's just an API call to enqueue, not to execute the task).
        created = self._client.create_task(
            parent=self._parent,
            task=task,
        )

        logger.info(
            "[queue:cloud_tasks] Created task {} for request_id={}",
            created.name,
            payload.request_id,
        )
