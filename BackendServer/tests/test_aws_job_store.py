"""Unit tests for the DynamoDB job state adapter."""

from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock

from aws_backend import job_store


class ConditionalFailure(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class InMemoryLeaseTable:
    """Small DynamoDB conditional-update simulation for lease races."""

    def __init__(self, item: dict):
        self.item = deepcopy(item)

    def get_item(self, **_kwargs):
        return {"Item": deepcopy(self.item)}

    def update_item(self, **kwargs):
        values = kwargs["ExpressionAttributeValues"]
        if ":lease_expires_at" in values:
            active_status = self.item["status"]
            may_claim = active_status == "pending" or (
                active_status == "processing"
                and self.item.get("lease_expires_at", "") < values[":now"]
            )
            within_budget = self.item.get("attempt_count", 0) < values[":max_attempts"]
            if not may_claim or not within_budget:
                raise ConditionalFailure()
            self.item.update(
                {
                    "status": "processing",
                    "updated_at": values[":now"],
                    "processing_started_at": values[":now"],
                    "lease_expires_at": values[":lease_expires_at"],
                    "worker_token": values[":worker_token"],
                    "attempt_count": self.item.get("attempt_count", 0) + 1,
                }
            )
        else:
            if (
                self.item.get("status") != "processing"
                or self.item.get("worker_token") != values[":worker_token"]
            ):
                raise ConditionalFailure()
            if ":completed" in values:
                self.item["status"] = "completed"
                self.item["result"] = values[":result"]
                for field in (
                    "processing_started_at",
                    "lease_expires_at",
                    "worker_token",
                    "error",
                ):
                    self.item.pop(field, None)
        return {"Attributes": deepcopy(self.item)}


class JobStoreTests(unittest.TestCase):
    def test_create_job_writes_pending_schema(self):
        table = Mock()
        job = job_store.create_job(
            job_id="job-1",
            s3_bucket="videos",
            s3_key="uploads/job-1/input.mp4",
            table=table,
            timestamp="2026-01-02T03:04:05.000Z",
        )

        self.assertEqual(job["status"], "pending")
        self.assertEqual(job["created_at"], job["updated_at"])
        table.put_item.assert_called_once_with(
            Item=job,
            ConditionExpression="attribute_not_exists(job_id)",
        )

    def test_get_pending_job_uses_consistent_read(self):
        item = {"job_id": "job-1", "status": "pending"}
        table = Mock()
        table.get_item.return_value = {"Item": item}

        self.assertEqual(job_store.get_job("job-1", table=table), item)
        table.get_item.assert_called_once_with(
            Key={"job_id": "job-1"}, ConsistentRead=True
        )

    def test_get_missing_job_returns_none(self):
        table = Mock()
        table.get_item.return_value = {}
        self.assertIsNone(job_store.get_job("missing", table=table))

    def test_mark_processing_is_conditional_on_pending(self):
        table = Mock()
        table.update_item.return_value = {
            "Attributes": {"job_id": "job-1", "status": "processing"}
        }

        result = job_store.mark_job_processing(
            "job-1",
            worker_token="worker-1",
            table=table,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
            lease_seconds=60,
            max_attempts=3,
        )

        self.assertEqual(result["status"], "processing")
        call = table.update_item.call_args.kwargs
        self.assertIn("#status = :pending OR", call["ConditionExpression"])
        self.assertIn("lease_expires_at < :now", call["ConditionExpression"])
        self.assertEqual(call["ExpressionAttributeValues"][":pending"], "pending")
        self.assertEqual(
            call["ExpressionAttributeValues"][":lease_expires_at"],
            "2026-01-01T00:01:00.000Z",
        )

    def test_rejected_claim_reports_existing_status(self):
        table = Mock()
        table.update_item.side_effect = ConditionalFailure()
        table.get_item.return_value = {
            "Item": {"job_id": "job-1", "status": "completed"}
        }

        with self.assertRaises(job_store.JobClaimRejectedError) as caught:
            job_store.mark_job_processing(
                "job-1",
                worker_token="worker-2",
                table=table,
                lease_seconds=60,
                max_attempts=3,
            )
        self.assertEqual(caught.exception.status, "completed")

    def test_rejected_claim_reports_missing_job(self):
        table = Mock()
        table.update_item.side_effect = ConditionalFailure()
        table.get_item.return_value = {}
        with self.assertRaises(job_store.JobNotFoundError):
            job_store.mark_job_processing(
                "missing",
                worker_token="worker-1",
                table=table,
                lease_seconds=60,
                max_attempts=3,
            )

    def test_complete_job_converts_floats_for_dynamodb(self):
        table = Mock()
        table.update_item.return_value = {
            "Attributes": {
                "job_id": "job-1",
                "status": "completed",
                "result": {"confidence": Decimal("0.875")},
            }
        }

        result = job_store.complete_job(
            "job-1",
            {"confidence": 0.875},
            worker_token="worker-1",
            table=table,
            timestamp="now",
        )

        stored = table.update_item.call_args.kwargs["ExpressionAttributeValues"]
        self.assertEqual(stored[":result"]["confidence"], Decimal("0.875"))
        self.assertEqual(result["result"]["confidence"], 0.875)

    def test_fail_job_stores_only_safe_message(self):
        table = Mock()
        table.update_item.return_value = {
            "Attributes": {
                "job_id": "job-1",
                "status": "failed",
                "error": job_store.SAFE_PROCESSING_ERROR,
            }
        }

        result = job_store.fail_job(
            "job-1", worker_token="worker-1", table=table, timestamp="now"
        )

        self.assertEqual(result["error"], "Video processing failed.")
        call = table.update_item.call_args.kwargs
        self.assertIn("REMOVE #result", call["UpdateExpression"])
        self.assertIn("worker_token = :worker_token", call["ConditionExpression"])

    def test_expired_lease_reclaim_blocks_old_worker_and_allows_new_worker(self):
        table = InMemoryLeaseTable(
            {
                "job_id": "job-1",
                "status": "pending",
                "attempt_count": 0,
            }
        )
        first_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        first = job_store.mark_job_processing(
            "job-1",
            worker_token="old-worker",
            table=table,
            now=first_time,
            lease_seconds=60,
            max_attempts=3,
        )
        self.assertEqual(first["attempt_count"], 1)

        with self.assertRaises(job_store.JobClaimRejectedError):
            job_store.mark_job_processing(
                "job-1",
                worker_token="duplicate-worker",
                table=table,
                now=datetime(2026, 1, 1, 0, 0, 30, tzinfo=timezone.utc),
                lease_seconds=60,
                max_attempts=3,
            )

        second = job_store.mark_job_processing(
            "job-1",
            worker_token="new-worker",
            table=table,
            now=datetime(2026, 1, 1, 0, 1, 1, tzinfo=timezone.utc),
            lease_seconds=60,
            max_attempts=3,
        )
        self.assertEqual(second["attempt_count"], 2)
        self.assertEqual(second["worker_token"], "new-worker")

        with self.assertRaises(job_store.JobOwnershipError):
            job_store.complete_job(
                "job-1",
                {"success": True},
                worker_token="old-worker",
                table=table,
            )
        with self.assertRaises(job_store.JobOwnershipError):
            job_store.fail_job(
                "job-1",
                worker_token="old-worker",
                table=table,
            )

        completed = job_store.complete_job(
            "job-1",
            {"success": True},
            worker_token="new-worker",
            table=table,
        )
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["attempt_count"], 2)


if __name__ == "__main__":
    unittest.main()
