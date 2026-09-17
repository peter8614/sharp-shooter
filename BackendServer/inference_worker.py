"""SQS-triggered Lambda worker for Sharp Shooter video inference."""

from __future__ import annotations

import json
import logging
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote_plus

from aws_backend import job_store, s3_service
from aws_backend.config import (
    SUPPORTED_VIDEO_TYPES,
    max_processing_attempts,
    processing_lease_seconds,
)
from core.inference import predict_video


logger = logging.getLogger(__name__)
_KEY_PATTERN = re.compile(
    r"^uploads/(?P<job_id>[A-Za-z0-9-]+)/input(?P<extension>\.[A-Za-z0-9]+)$"
)
_SUPPORTED_EXTENSIONS = frozenset(SUPPORTED_VIDEO_TYPES.values())
_RETRYABLE_OUTCOMES = frozenset(
    {"active_lease", "retryable_failure", "ownership_lost"}
)
_DLQ_OUTCOMES = frozenset(
    {"failed", "attempts_exhausted", "missing_job", "object_mismatch"}
)


@dataclass(frozen=True)
class UploadRecord:
    bucket: str
    key: str
    job_id: str
    extension: str


@dataclass(frozen=True)
class SqsUploadMessage:
    message_id: str
    upload: UploadRecord


def parse_s3_event(event: dict) -> list[UploadRecord]:
    """Parse the S3 notification nested inside an SQS message body."""
    records = event.get("Records") if isinstance(event, dict) else None
    if not isinstance(records, list) or not records:
        raise ValueError("S3 event does not contain records")

    uploads = []
    for record in records:
        try:
            bucket = record["s3"]["bucket"]["name"]
            key = unquote_plus(record["s3"]["object"]["key"])
        except (KeyError, TypeError) as error:
            raise ValueError("Malformed S3 event record") from error
        if not isinstance(bucket, str) or not bucket:
            raise ValueError("Malformed S3 bucket name")
        match = _KEY_PATTERN.fullmatch(key)
        if match is None or match.group("extension").lower() not in _SUPPORTED_EXTENSIONS:
            raise ValueError("Unexpected S3 object key")
        uploads.append(
            UploadRecord(
                bucket=bucket,
                key=key,
                job_id=match.group("job_id"),
                extension=match.group("extension").lower(),
            )
        )
    return uploads


def parse_sqs_event(event: dict) -> list[SqsUploadMessage]:
    """Extract one embedded S3 notification from each SQS record."""
    records = event.get("Records") if isinstance(event, dict) else None
    if not isinstance(records, list) or not records:
        raise ValueError("SQS event does not contain records")

    messages = []
    for record in records:
        try:
            message_id = record["messageId"]
            body = json.loads(record["body"])
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError("Malformed SQS event record") from error
        if not isinstance(message_id, str) or not message_id:
            raise ValueError("SQS message ID is required")
        uploads = parse_s3_event(body)
        if len(uploads) != 1:
            raise ValueError("Each SQS message must contain one S3 upload record")
        messages.append(SqsUploadMessage(message_id=message_id, upload=uploads[0]))
    return messages


def _claim_or_outcome(
    upload: UploadRecord,
    *,
    worker_token: str,
    now: datetime | None,
    lease_seconds: int,
    max_attempts: int,
) -> tuple[dict | None, dict | None]:
    job = job_store.get_job(upload.job_id)
    if job is None:
        logger.error("Upload references missing job %s", upload.job_id)
        return None, {"job_id": upload.job_id, "outcome": "missing_job"}
    if job.get("s3_bucket") != upload.bucket or job.get("s3_key") != upload.key:
        logger.error("Upload does not match job %s", upload.job_id)
        return None, {"job_id": upload.job_id, "outcome": "object_mismatch"}
    if job.get("status") == job_store.COMPLETED:
        return None, {"job_id": upload.job_id, "outcome": "completed_duplicate"}
    if job.get("status") == job_store.FAILED:
        return None, {"job_id": upload.job_id, "outcome": "failed"}

    try:
        claimed = job_store.mark_job_processing(
            upload.job_id,
            worker_token=worker_token,
            now=now,
            lease_seconds=lease_seconds,
            max_attempts=max_attempts,
        )
        return claimed, None
    except job_store.JobNotFoundError:
        return None, {"job_id": upload.job_id, "outcome": "missing_job"}
    except job_store.JobClaimRejectedError as error:
        current = error.job
        if current.get("status") == job_store.COMPLETED:
            return None, {
                "job_id": upload.job_id,
                "outcome": "completed_duplicate",
            }
        if current.get("status") == job_store.FAILED:
            return None, {"job_id": upload.job_id, "outcome": "failed"}
        if (
            current.get("status") == job_store.PROCESSING
            and int(current.get("attempt_count", 0)) >= max_attempts
            and current.get("worker_token")
        ):
            try:
                job_store.fail_expired_job(
                    upload.job_id,
                    worker_token=current["worker_token"],
                    now=now,
                    max_attempts=max_attempts,
                )
                return None, {
                    "job_id": upload.job_id,
                    "outcome": "attempts_exhausted",
                }
            except job_store.JobOwnershipError:
                pass
        return None, {"job_id": upload.job_id, "outcome": "active_lease"}


def process_upload(
    upload: UploadRecord,
    *,
    worker_token: str,
    now: datetime | None = None,
    lease_seconds: int | None = None,
    max_attempts: int | None = None,
) -> dict:
    """Claim and process one upload independently of its AWS event envelope."""
    lease_duration = (
        processing_lease_seconds() if lease_seconds is None else lease_seconds
    )
    attempt_limit = (
        max_processing_attempts() if max_attempts is None else max_attempts
    )
    claimed, early_outcome = _claim_or_outcome(
        upload,
        worker_token=worker_token,
        now=now,
        lease_seconds=lease_duration,
        max_attempts=attempt_limit,
    )
    if early_outcome is not None:
        return early_outcome

    attempt_count = int(claimed.get("attempt_count", 1))
    try:
        with tempfile.TemporaryDirectory(
            prefix=f"sharp-shooter-{upload.job_id}-"
        ) as temporary_dir:
            local_video = Path(temporary_dir) / f"input{upload.extension}"
            s3_service.download_video(
                bucket=upload.bucket,
                key=upload.key,
                destination=local_video,
            )
            result = predict_video(local_video)
        job_store.complete_job(
            upload.job_id,
            result,
            worker_token=worker_token,
        )
        return {"job_id": upload.job_id, "outcome": "completed"}
    except job_store.JobOwnershipError:
        logger.warning("Worker lease was replaced for job %s", upload.job_id)
        return {"job_id": upload.job_id, "outcome": "ownership_lost"}
    except Exception:
        logger.exception(
            "Inference attempt %s failed for job %s", attempt_count, upload.job_id
        )
        try:
            if attempt_count >= attempt_limit:
                job_store.fail_job(upload.job_id, worker_token=worker_token)
                return {"job_id": upload.job_id, "outcome": "failed"}
            job_store.release_job_for_retry(
                upload.job_id,
                worker_token=worker_token,
            )
            return {"job_id": upload.job_id, "outcome": "retryable_failure"}
        except job_store.JobOwnershipError:
            logger.warning("Worker lost lease while failing job %s", upload.job_id)
            return {"job_id": upload.job_id, "outcome": "ownership_lost"}


def _worker_token(context) -> str:
    request_id = getattr(context, "aws_request_id", None)
    return str(request_id or uuid.uuid4())


def lambda_handler(event, context):
    """Handle SQS records and report failures for Lambda partial batch response."""
    try:
        messages = parse_sqs_event(event)
    except ValueError:
        logger.exception("Unable to parse SQS inference event")
        records = event.get("Records", []) if isinstance(event, dict) else []
        failures = [
            {"itemIdentifier": record.get("messageId", "unknown")}
            for record in records
        ]
        return {"batchItemFailures": failures}

    token = _worker_token(context)
    failures = []
    for message in messages:
        outcome = process_upload(message.upload, worker_token=token)
        if outcome["outcome"] in _RETRYABLE_OUTCOMES | _DLQ_OUTCOMES:
            failures.append({"itemIdentifier": message.message_id})
    return {"batchItemFailures": failures}
