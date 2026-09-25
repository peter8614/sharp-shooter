"""Queue anonymous, completed-job coaching work without delaying inference."""

from __future__ import annotations

import json
import os


def enqueue(job_id: str, *, client=None) -> None:
    queue_url = os.environ.get("COACHING_QUEUE_URL", "").strip()
    if not queue_url:
        raise RuntimeError("COACHING_QUEUE_URL is required")
    if client is None:
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "sqs",
            config=Config(connect_timeout=2, read_timeout=3,
                          retries={"max_attempts": 2}),
        )
    client.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({"job_id": job_id}),
        DelaySeconds=10,
    )
