"""Asynchronous, optional coaching for already completed inference jobs."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid

from aws_backend import coaching_store, job_store
from llm_analysis import create_llm_analysis_from_summary


logger = logging.getLogger(__name__)


def parse_sqs_event(event: dict) -> list[tuple[str, str]]:
    records = event.get("Records") if isinstance(event, dict) else None
    if not isinstance(records, list) or not records:
        raise ValueError("Expected SQS records")
    messages = []
    for record in records:
        if record.get("eventSource") != "aws:sqs" or not record.get("messageId"):
            raise ValueError("Expected an SQS record with a message ID")
        try:
            body = json.loads(record["body"])
            job_id = body["job_id"]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Invalid coaching message") from error
        if not isinstance(job_id, str) or not job_id or len(job_id) > 128:
            raise ValueError("Invalid coaching job ID")
        messages.append((record["messageId"], job_id))
    return messages


def _api_key(*, ssm_client=None) -> str:
    name = os.environ.get("OPENAI_API_KEY_PARAMETER", "").strip()
    if not name:
        raise RuntimeError("OPENAI_API_KEY_PARAMETER is required")
    if ssm_client is None:
        import boto3

        ssm_client = boto3.client("ssm")
    key = ssm_client.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
    if not key:
        raise RuntimeError("OpenAI API key parameter is empty")
    return key


def _safety_identifier(job: dict, key: str) -> str:
    identity = str(job.get("owner_sub") or job["job_id"])
    return hmac.new(key.encode(), identity.encode(), hashlib.sha256).hexdigest()


def process_job(
    job_id: str,
    *,
    worker_token: str,
    ssm_client=None,
    openai_client=None,
) -> str:
    lease_seconds = int(os.environ.get("COACHING_LEASE_SECONDS", "90"))
    max_attempts = int(os.environ.get("MAX_COACHING_ATTEMPTS", "3"))
    if lease_seconds <= 0 or max_attempts <= 0:
        raise ValueError("Invalid coaching retry configuration")
    try:
        job = coaching_store.claim(
            job_id, worker_token,
            lease_seconds=lease_seconds, max_attempts=max_attempts,
        )
    except coaching_store.CoachingClaimRejected as error:
        current = error.job
        if current is None or current.get("status") != job_store.COMPLETED:
            return "retry"
        status = (current.get("result") or {}).get("coaching_status")
        if status == "ready":
            return "duplicate"
        if status == "unavailable":
            return "retry"  # Preserve permanent failures in the DLQ.
        if status == "processing":
            # The original SQS receipt remains in flight; a duplicate can be acked.
            if int(current.get("coaching_attempt_count", 0)) >= max_attempts:
                try:
                    coaching_store.unavailable_expired(job_id, max_attempts=max_attempts)
                    return "retry"
                except coaching_store.CoachingOwnershipLost:
                    pass
            return "duplicate"
        return "retry"

    attempt = int(job.get("coaching_attempt_count", 1))
    try:
        result = job["result"]
        summary = result["coaching_summary"]
        key = _api_key(ssm_client=ssm_client)
        if openai_client is None:
            from openai import OpenAI

            openai_client = OpenAI(api_key=key, timeout=20.0, max_retries=0)
        analysis = create_llm_analysis_from_summary(
            summary,
            _safety_identifier(job, key),
            client=openai_client,
            coaching_context={"coaching_labels": result.get("coaching_labels", [])},
            output_language="English",
        )
        coaching_store.finish(job_id, worker_token, analysis)
        return "ready"
    except coaching_store.CoachingOwnershipLost:
        return "duplicate"
    except Exception:
        logger.exception("Coaching attempt %s failed for job %s", attempt, job_id)
        try:
            if attempt >= max_attempts:
                coaching_store.unavailable(job_id, worker_token)
            else:
                coaching_store.retry(job_id, worker_token)
        except coaching_store.CoachingOwnershipLost:
            return "duplicate"
        return "retry"


def lambda_handler(event, context):
    try:
        messages = parse_sqs_event(event)
    except ValueError:
        logger.exception("Invalid coaching queue event")
        records = event.get("Records", []) if isinstance(event, dict) else []
        return {"batchItemFailures": [
            {"itemIdentifier": record.get("messageId", "unknown")}
            for record in records
        ]}
    failures = []
    for message_id, job_id in messages:
        token = f"{getattr(context, 'aws_request_id', '') or uuid.uuid4()}:{message_id}"
        try:
            outcome = process_job(job_id, worker_token=token)
        except Exception:
            logger.exception("Unexpected coaching worker failure for job %s", job_id)
            outcome = "retry"
        if outcome == "retry":
            failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": failures}
