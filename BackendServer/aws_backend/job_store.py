"""DynamoDB-backed state machine for asynchronous inference jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .config import (
    aws_region,
    jobs_table,
    max_processing_attempts,
    processing_lease_seconds,
)

try:
    import boto3
except ImportError:  # Allows mock-only unit tests without installing the AWS SDK.
    boto3 = None


PENDING = "pending"
PROCESSING = "processing"
COMPLETED = "completed"
FAILED = "failed"
ALLOWED_STATUSES = frozenset({PENDING, PROCESSING, COMPLETED, FAILED})
SAFE_PROCESSING_ERROR = "Video processing failed."

_dynamodb_resource = None
_table_cache: dict[str, Any] = {}


class JobNotFoundError(LookupError):
    """Raised when a requested job does not exist."""


class JobClaimRejectedError(RuntimeError):
    """Raised when another worker already owns or finished a job."""

    def __init__(self, job: dict):
        self.job = job
        self.status = job.get("status")
        super().__init__(f"Job cannot transition from status {self.status!r}")


class JobOwnershipError(RuntimeError):
    """Raised when a stale worker attempts to mutate another worker's lease."""


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _as_utc(value: datetime | None = None) -> datetime:
    resolved = value or datetime.now(timezone.utc)
    if resolved.tzinfo is None:
        raise ValueError("Lease timestamps must be timezone-aware")
    return resolved.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _get_dynamodb_resource():
    global _dynamodb_resource
    if _dynamodb_resource is None:
        if boto3 is None:
            raise RuntimeError("boto3 is required for DynamoDB operations")
        _dynamodb_resource = boto3.resource("dynamodb", region_name=aws_region())
    return _dynamodb_resource


def _get_table(table_name: str | None = None):
    resolved_name = table_name or jobs_table()
    if resolved_name not in _table_cache:
        _table_cache[resolved_name] = _get_dynamodb_resource().Table(resolved_name)
    return _table_cache[resolved_name]


def _is_conditional_failure(error: Exception) -> bool:
    response = getattr(error, "response", {})
    return response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def _to_dynamodb(value: Any) -> Any:
    """Convert JSON-compatible floats to DynamoDB-compatible decimals."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _to_dynamodb(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_dynamodb(item) for item in value]
    if isinstance(value, tuple):
        return [_to_dynamodb(item) for item in value]
    return value


def _from_dynamodb(value: Any) -> Any:
    """Return ordinary JSON-compatible values from DynamoDB responses."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: _from_dynamodb(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_dynamodb(item) for item in value]
    return value


def create_job(
    *,
    job_id: str,
    s3_bucket: str,
    s3_key: str,
    table=None,
    timestamp: str | None = None,
) -> dict:
    now = timestamp or _utc_timestamp()
    item = {
        "job_id": job_id,
        "status": PENDING,
        "attempt_count": 0,
        "created_at": now,
        "updated_at": now,
        "s3_bucket": s3_bucket,
        "s3_key": s3_key,
    }
    (table or _get_table()).put_item(
        Item=item,
        ConditionExpression="attribute_not_exists(job_id)",
    )
    return item.copy()


def get_job(job_id: str, *, table=None) -> dict | None:
    response = (table or _get_table()).get_item(
        Key={"job_id": job_id},
        ConsistentRead=True,
    )
    item = response.get("Item")
    return _from_dynamodb(item) if item is not None else None


def mark_job_processing(
    job_id: str,
    *,
    worker_token: str,
    table=None,
    now: datetime | None = None,
    lease_seconds: int | None = None,
    max_attempts: int | None = None,
) -> dict:
    if not worker_token:
        raise ValueError("worker_token is required")
    claim_time = _as_utc(now)
    lease_duration = (
        processing_lease_seconds() if lease_seconds is None else lease_seconds
    )
    attempt_limit = (
        max_processing_attempts() if max_attempts is None else max_attempts
    )
    if lease_duration <= 0 or attempt_limit <= 0:
        raise ValueError("Lease duration and attempt limit must be positive")
    claim_timestamp = _format_timestamp(claim_time)
    lease_expiration = _format_timestamp(
        claim_time + timedelta(seconds=lease_duration)
    )
    resolved_table = table or _get_table()
    try:
        response = resolved_table.update_item(
            Key={"job_id": job_id},
            UpdateExpression=(
                "SET #status = :processing, updated_at = :now, "
                "processing_started_at = :now, lease_expires_at = :lease_expires_at, "
                "worker_token = :worker_token, "
                "attempt_count = if_not_exists(attempt_count, :zero) + :one "
                "REMOVE #result, #error"
            ),
            ConditionExpression=(
                "attribute_exists(job_id) AND "
                "(attribute_not_exists(attempt_count) OR attempt_count < :max_attempts) "
                "AND (#status = :pending OR (#status = :processing AND "
                "(attribute_not_exists(lease_expires_at) OR lease_expires_at < :now)))"
            ),
            ExpressionAttributeNames={
                "#status": "status",
                "#result": "result",
                "#error": "error",
            },
            ExpressionAttributeValues={
                ":pending": PENDING,
                ":processing": PROCESSING,
                ":now": claim_timestamp,
                ":lease_expires_at": lease_expiration,
                ":worker_token": worker_token,
                ":zero": 0,
                ":one": 1,
                ":max_attempts": attempt_limit,
            },
            ReturnValues="ALL_NEW",
        )
    except Exception as error:
        if not _is_conditional_failure(error):
            raise
        current = get_job(job_id, table=resolved_table)
        if current is None:
            raise JobNotFoundError(job_id) from error
        raise JobClaimRejectedError(current) from error
    return _from_dynamodb(response.get("Attributes", {}))


def _owned_update(
    *,
    table,
    job_id: str,
    worker_token: str,
    update_expression: str,
    expression_names: dict,
    expression_values: dict,
    extra_condition: str | None = None,
) -> dict:
    condition = "#status = :processing AND worker_token = :worker_token"
    if extra_condition:
        condition = f"{condition} AND {extra_condition}"
    values = {
        ":processing": PROCESSING,
        ":worker_token": worker_token,
        **expression_values,
    }
    try:
        response = table.update_item(
            Key={"job_id": job_id},
            UpdateExpression=update_expression,
            ConditionExpression=condition,
            ExpressionAttributeNames={"#status": "status", **expression_names},
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
    except Exception as error:
        if _is_conditional_failure(error):
            raise JobOwnershipError(job_id) from error
        raise
    return _from_dynamodb(response.get("Attributes", {}))


def complete_job(
    job_id: str,
    result: dict,
    *,
    worker_token: str,
    table=None,
    timestamp: str | None = None,
) -> dict:
    return _owned_update(
        table=table or _get_table(),
        job_id=job_id,
        worker_token=worker_token,
        update_expression=(
            "SET #status = :completed, updated_at = :updated_at, #result = :result "
            "REMOVE #error, processing_started_at, lease_expires_at, worker_token"
        ),
        expression_names={"#result": "result", "#error": "error"},
        expression_values={
            ":processing": PROCESSING,
            ":completed": COMPLETED,
            ":updated_at": timestamp or _utc_timestamp(),
            ":result": _to_dynamodb(result),
        },
    )


def fail_job(
    job_id: str,
    *,
    worker_token: str,
    table=None,
    timestamp: str | None = None,
) -> dict:
    return _owned_update(
        table=table or _get_table(),
        job_id=job_id,
        worker_token=worker_token,
        update_expression=(
            "SET #status = :failed, updated_at = :updated_at, #error = :error "
            "REMOVE #result, processing_started_at, lease_expires_at, worker_token"
        ),
        expression_names={"#result": "result", "#error": "error"},
        expression_values={
            ":processing": PROCESSING,
            ":failed": FAILED,
            ":updated_at": timestamp or _utc_timestamp(),
            ":error": SAFE_PROCESSING_ERROR,
        },
    )


def release_job_for_retry(
    job_id: str,
    *,
    worker_token: str,
    table=None,
    timestamp: str | None = None,
) -> dict:
    """Return an owned failed attempt to pending so SQS can retry it."""
    return _owned_update(
        table=table or _get_table(),
        job_id=job_id,
        worker_token=worker_token,
        update_expression=(
            "SET #status = :pending, updated_at = :updated_at "
            "REMOVE #result, #error, processing_started_at, lease_expires_at, worker_token"
        ),
        expression_names={"#result": "result", "#error": "error"},
        expression_values={
            ":pending": PENDING,
            ":updated_at": timestamp or _utc_timestamp(),
        },
    )


def fail_expired_job(
    job_id: str,
    *,
    worker_token: str,
    now: datetime | None = None,
    max_attempts: int | None = None,
    table=None,
) -> dict:
    """Safely finalize an expired lease that exhausted its attempt budget."""
    current_time = _format_timestamp(_as_utc(now))
    attempt_limit = (
        max_processing_attempts() if max_attempts is None else max_attempts
    )
    return _owned_update(
        table=table or _get_table(),
        job_id=job_id,
        worker_token=worker_token,
        update_expression=(
            "SET #status = :failed, updated_at = :now, #error = :error "
            "REMOVE #result, processing_started_at, lease_expires_at, worker_token"
        ),
        expression_names={"#result": "result", "#error": "error"},
        expression_values={
            ":failed": FAILED,
            ":now": current_time,
            ":error": SAFE_PROCESSING_ERROR,
            ":max_attempts": attempt_limit,
        },
        extra_condition=(
            "lease_expires_at < :now AND attempt_count >= :max_attempts"
        ),
    )
