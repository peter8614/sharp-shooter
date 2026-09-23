"""SQS-triggered Lambda worker for Sharp Shooter video inference."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
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
_RUNTIME_ID = uuid.uuid4().hex
_HANDLER_INVOCATIONS = 0
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


class _TmpUsageSampler:
    """Sample Lambda /tmp usage without touching inference implementation."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.capacity_bytes: int | None = None
        self.before_bytes: int | None = None
        self.peak_bytes: int | None = None
        self.after_bytes: int | None = None

    def _sample(self) -> int | None:
        try:
            usage = shutil.disk_usage(tempfile.gettempdir())
        except OSError:
            return None
        self.capacity_bytes = usage.total
        return usage.used

    def _run(self) -> None:
        while not self._stop.wait(0.5):
            used = self._sample()
            if used is not None:
                self.peak_bytes = max(self.peak_bytes or 0, used)

    def start(self) -> None:
        self.before_bytes = self._sample()
        self.peak_bytes = self.before_bytes
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self.after_bytes = self._sample()
        if self.after_bytes is not None:
            self.peak_bytes = max(self.peak_bytes or 0, self.after_bytes)


def _detector_cached() -> bool | None:
    try:
        from video_pipeline import DEFAULT_WEIGHTS
        from yolo_detector import detector_is_cached

        return detector_is_cached(DEFAULT_WEIGHTS, "cpu")
    except Exception:
        # Diagnostics must never change the inference outcome.
        return None


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
        # S3 sends this one-off connectivity probe when the bucket notification
        # is configured. Unlike upload notifications, it has no Records array.
        if (
            isinstance(body, dict)
            and body.get("Service") == "Amazon S3"
            and body.get("Event") == "s3:TestEvent"
            and isinstance(body.get("Bucket"), str)
            and body["Bucket"]
        ):
            continue
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
    invocation_number: int | None = None,
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
    diagnostics = os.environ.get("WORKER_DIAGNOSTICS_ENABLED") == "1"
    sampler = _TmpUsageSampler() if diagnostics else None
    cached_before = _detector_cached() if diagnostics else None
    started = time.perf_counter()
    if sampler is not None:
        try:
            sampler.start()
        except Exception:
            sampler = None
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
    finally:
        if sampler is not None:
            try:
                sampler.stop()
                print(
                    "WORKER_DIAGNOSTIC "
                    + json.dumps(
                        {
                            "job_id": upload.job_id,
                            "runtime_id": _RUNTIME_ID,
                            "invocation_number": invocation_number,
                            "attempt_count": attempt_count,
                            "elapsed_seconds": round(time.perf_counter() - started, 3),
                            "detector_cached_before": cached_before,
                            "detector_cached_after": _detector_cached(),
                            "tmp_capacity_bytes": sampler.capacity_bytes,
                            "tmp_used_before_bytes": sampler.before_bytes,
                            "tmp_used_peak_sampled_bytes": sampler.peak_bytes,
                            "tmp_used_after_bytes": sampler.after_bytes,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            except Exception:
                logger.warning("Worker diagnostics unavailable for %s", upload.job_id)


def _worker_token(context) -> str:
    request_id = getattr(context, "aws_request_id", None)
    return str(request_id or uuid.uuid4())


def lambda_handler(event, context):
    """Handle SQS records and report failures for Lambda partial batch response."""
    global _HANDLER_INVOCATIONS
    _HANDLER_INVOCATIONS += 1
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
        outcome = process_upload(
            message.upload,
            worker_token=token,
            invocation_number=_HANDLER_INVOCATIONS,
        )
        if outcome["outcome"] in _RETRYABLE_OUTCOMES | _DLQ_OUTCOMES:
            failures.append({"itemIdentifier": message.message_id})
    return {"batchItemFailures": failures}
