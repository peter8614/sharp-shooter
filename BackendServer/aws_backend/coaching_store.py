"""Conditional, token-owned updates to the independent coaching sub-state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import job_store


class CoachingClaimRejected(RuntimeError):
    def __init__(self, job: dict | None):
        self.job = job
        super().__init__("Coaching lease cannot be claimed")


class CoachingOwnershipLost(RuntimeError):
    pass


def _timestamp(value: datetime | None = None) -> str:
    return job_store._format_timestamp(job_store._as_utc(value))


def claim(
    job_id: str,
    token: str,
    *,
    lease_seconds: int,
    max_attempts: int,
    now: datetime | None = None,
    table=None,
) -> dict:
    current = job_store._as_utc(now)
    values = {
        ":completed": job_store.COMPLETED,
        ":queued": "queued",
        ":processing": "processing",
        ":now": _timestamp(current),
        ":expiry": _timestamp(current + timedelta(seconds=lease_seconds)),
        ":token": token,
        ":zero": 0,
        ":one": 1,
        ":limit": max_attempts,
    }
    table = table or job_store._get_table()
    try:
        response = table.update_item(
            Key={"job_id": job_id},
            UpdateExpression=(
                "SET #result.#coach_status = :processing, "
                "coaching_started_at = :now, coaching_lease_expires_at = :expiry, "
                "coaching_worker_token = :token, "
                "coaching_attempt_count = if_not_exists(coaching_attempt_count, :zero) + :one"
            ),
            ConditionExpression=(
                "#status = :completed AND "
                "(#result.#coach_status = :queued OR "
                "(#result.#coach_status = :processing AND coaching_lease_expires_at < :now)) "
                "AND (attribute_not_exists(coaching_attempt_count) OR coaching_attempt_count < :limit)"
            ),
            ExpressionAttributeNames={
                "#status": "status", "#result": "result", "#coach_status": "coaching_status"
            },
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
    except Exception as error:
        if job_store._is_conditional_failure(error):
            raise CoachingClaimRejected(job_store.get_job(job_id, table=table)) from error
        raise
    return job_store._from_dynamodb(response["Attributes"])


def _owned_update(
    job_id: str,
    token: str,
    *,
    status: str,
    text: str | None = None,
    table=None,
) -> dict:
    table = table or job_store._get_table()
    update = "SET #result.#coach_status = :target, updated_at = :now"
    values = {
        ":completed": job_store.COMPLETED,
        ":processing": "processing",
        ":target": status,
        ":token": token,
        ":now": _timestamp(),
    }
    names = {
        "#status": "status", "#result": "result",
        "#coach_status": "coaching_status",
    }
    if text is not None:
        update += ", #result.#coach_text = :text"
        values[":text"] = text
        names["#coach_text"] = "coaching_text"
    update += " REMOVE coaching_started_at, coaching_lease_expires_at, coaching_worker_token"
    try:
        response = table.update_item(
            Key={"job_id": job_id},
            UpdateExpression=update,
            ConditionExpression=(
                "#status = :completed AND #result.#coach_status = :processing "
                "AND coaching_worker_token = :token"
            ),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
    except Exception as error:
        if job_store._is_conditional_failure(error):
            raise CoachingOwnershipLost(job_id) from error
        raise
    return job_store._from_dynamodb(response["Attributes"])


def finish(job_id: str, token: str, text: str, *, table=None) -> dict:
    return _owned_update(job_id, token, status="ready", text=text, table=table)


def retry(job_id: str, token: str, *, table=None) -> dict:
    return _owned_update(job_id, token, status="queued", table=table)


def unavailable(job_id: str, token: str, *, table=None) -> dict:
    return _owned_update(job_id, token, status="unavailable", table=table)


def unavailable_expired(job_id: str, *, max_attempts: int, now: datetime | None = None, table=None) -> dict:
    """Finalize a dead lease after the attempt budget, without stealing a new owner."""
    table = table or job_store._get_table()
    try:
        response = table.update_item(
            Key={"job_id": job_id},
            UpdateExpression=(
                "SET #result.#coach_status = :unavailable, updated_at = :now "
                "REMOVE coaching_started_at, coaching_lease_expires_at, coaching_worker_token"
            ),
            ConditionExpression=(
                "#status = :completed AND #result.#coach_status = :processing "
                "AND coaching_lease_expires_at < :now AND coaching_attempt_count >= :limit"
            ),
            ExpressionAttributeNames={
                "#status": "status", "#result": "result", "#coach_status": "coaching_status"
            },
            ExpressionAttributeValues={
                ":completed": job_store.COMPLETED,
                ":processing": "processing",
                ":unavailable": "unavailable",
                ":now": _timestamp(now),
                ":limit": max_attempts,
            },
            ReturnValues="ALL_NEW",
        )
    except Exception as error:
        if job_store._is_conditional_failure(error):
            raise CoachingOwnershipLost(job_id) from error
        raise
    return job_store._from_dynamodb(response["Attributes"])
