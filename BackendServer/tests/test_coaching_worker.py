"""Independent coaching lease, retry, privacy, and queue behavior."""

from __future__ import annotations

import json
import os
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import coaching_worker
from aws_backend import coaching_queue, coaching_store


class ConditionalFailure(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class InMemoryCoachingTable:
    def __init__(self):
        self.item = completed_job(attempt=0)

    def get_item(self, **_kwargs):
        return {"Item": deepcopy(self.item)}

    def update_item(self, **kwargs):
        values = kwargs["ExpressionAttributeValues"]
        result = self.item["result"]
        if ":expiry" in values:
            eligible = result["coaching_status"] == "queued" or (
                result["coaching_status"] == "processing"
                and self.item.get("coaching_lease_expires_at", "") < values[":now"]
            )
            if not eligible or self.item["coaching_attempt_count"] >= values[":limit"]:
                raise ConditionalFailure()
            result["coaching_status"] = "processing"
            self.item["coaching_worker_token"] = values[":token"]
            self.item["coaching_lease_expires_at"] = values[":expiry"]
            self.item["coaching_attempt_count"] += 1
        else:
            if (result["coaching_status"] != "processing" or
                    self.item.get("coaching_worker_token") != values[":token"]):
                raise ConditionalFailure()
            result["coaching_status"] = values[":target"]
            if ":text" in values:
                result["coaching_text"] = values[":text"]
            self.item.pop("coaching_worker_token", None)
            self.item.pop("coaching_lease_expires_at", None)
        return {"Attributes": deepcopy(self.item)}


def completed_job(*, status="queued", attempt=1):
    return {
        "job_id": "job-1",
        "status": "completed",
        "owner_sub": "private-user-id",
        "coaching_attempt_count": attempt,
        "result": {
            "coaching_status": status,
            "coaching_summary": {"schema_version": 1, "data_quality": {}, "measurements": {}},
            "coaching_labels": [],
        },
    }


class CoachingWorkerTests(unittest.TestCase):
    def test_expired_lease_recovery_blocks_stale_completion(self):
        table = InMemoryCoachingTable()
        first_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        first = coaching_store.claim("job-1", "old", lease_seconds=90,
                                     max_attempts=3, now=first_time, table=table)
        self.assertEqual(first["coaching_attempt_count"], 1)
        with self.assertRaises(coaching_store.CoachingClaimRejected):
            coaching_store.claim("job-1", "duplicate", lease_seconds=90,
                                 max_attempts=3, now=first_time, table=table)
        second_time = datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc)
        second = coaching_store.claim("job-1", "new", lease_seconds=90,
                                      max_attempts=3, now=second_time, table=table)
        self.assertEqual(second["coaching_attempt_count"], 2)
        with self.assertRaises(coaching_store.CoachingOwnershipLost):
            coaching_store.finish("job-1", "old", "stale", table=table)
        finished = coaching_store.finish("job-1", "new", "fresh", table=table)
        self.assertEqual(finished["result"]["coaching_text"], "fresh")

    def test_queue_message_contains_only_job_id(self):
        client = Mock()
        with patch.dict(os.environ, {"COACHING_QUEUE_URL": "https://sqs.example/queue"}):
            coaching_queue.enqueue("job-1", client=client)
        sent = client.send_message.call_args.kwargs
        self.assertEqual(json.loads(sent["MessageBody"]), {"job_id": "job-1"})
        self.assertEqual(sent["DelaySeconds"], 10)

    def test_sqs_envelope_requires_valid_job_id(self):
        event = {"Records": [{
            "eventSource": "aws:sqs", "messageId": "msg-1",
            "body": json.dumps({"job_id": "job-1"}),
        }]}
        self.assertEqual(coaching_worker.parse_sqs_event(event), [("msg-1", "job-1")])
        event["Records"][0]["body"] = "not-json"
        with self.assertRaises(ValueError):
            coaching_worker.parse_sqs_event(event)

    def test_claim_condition_and_token_protected_completion(self):
        table = Mock()
        table.update_item.return_value = {"Attributes": completed_job(status="processing")}
        current = datetime(2026, 1, 1, tzinfo=timezone.utc)
        coaching_store.claim("job-1", "new-token", lease_seconds=90, max_attempts=3,
                             now=current, table=table)
        claim_call = table.update_item.call_args.kwargs
        self.assertIn("coaching_lease_expires_at < :now", claim_call["ConditionExpression"])
        self.assertIn("coaching_attempt_count < :limit", claim_call["ConditionExpression"])
        self.assertEqual(claim_call["ExpressionAttributeValues"][":expiry"],
                         "2026-01-01T00:01:30.000Z")
        coaching_store.finish("job-1", "new-token", "Main Findings\nNo specific cause.\nHow to Improve\nRetest.", table=table)
        finish_call = table.update_item.call_args.kwargs
        self.assertIn("coaching_worker_token = :token", finish_call["ConditionExpression"])
        self.assertEqual(finish_call["ExpressionAttributeValues"][":token"], "new-token")

    def test_active_duplicate_is_acked_and_stale_lease_is_reclaimable(self):
        with patch.object(coaching_worker.coaching_store, "claim", side_effect=(
            coaching_store.CoachingClaimRejected(completed_job(status="processing"))
        )):
            self.assertEqual(coaching_worker.process_job("job-1", worker_token="other"), "duplicate")
        with patch.object(coaching_worker.coaching_store, "claim", return_value=completed_job(attempt=2)) as claim, \
             patch.object(coaching_worker, "_api_key", return_value="test-key"), \
             patch.object(coaching_worker, "create_llm_analysis_from_summary", return_value="Main Findings\nNo specific cause.\nHow to Improve\nRetest.") as generate, \
             patch.object(coaching_worker.coaching_store, "finish") as finish:
            outcome = coaching_worker.process_job("job-1", worker_token="new-token",
                                                  openai_client=Mock())
        self.assertEqual(outcome, "ready")
        self.assertEqual(claim.call_args.kwargs["max_attempts"], 3)
        self.assertEqual(generate.call_args.kwargs["output_language"], "English")
        self.assertNotEqual(generate.call_args.args[1], "private-user-id")
        finish.assert_called_once_with("job-1", "new-token", "Main Findings\nNo specific cause.\nHow to Improve\nRetest.")

    def test_old_worker_cannot_overwrite_new_worker(self):
        table = Mock()
        table.update_item.side_effect = ConditionalFailure()
        with self.assertRaises(coaching_store.CoachingOwnershipLost):
            coaching_store.finish("job-1", "old-token", "stale text", table=table)

    def test_retry_then_unavailable_and_dlq_failure_signal(self):
        with patch.object(coaching_worker.coaching_store, "claim", return_value=completed_job(attempt=1)), \
             patch.object(coaching_worker, "_api_key", side_effect=RuntimeError("secret absent")), \
             patch.object(coaching_worker.coaching_store, "retry") as retry:
            self.assertEqual(coaching_worker.process_job("job-1", worker_token="token"), "retry")
            retry.assert_called_once_with("job-1", "token")
        with patch.object(coaching_worker.coaching_store, "claim", return_value=completed_job(attempt=3)), \
             patch.object(coaching_worker, "_api_key", side_effect=RuntimeError("secret absent")), \
             patch.object(coaching_worker.coaching_store, "unavailable") as unavailable:
            self.assertEqual(coaching_worker.process_job("job-1", worker_token="token"), "retry")
            unavailable.assert_called_once_with("job-1", "token")
        event = {"Records": [{"eventSource": "aws:sqs", "messageId": "msg-1",
                              "body": json.dumps({"job_id": "job-1"})}]}
        with patch.object(coaching_worker, "process_job", return_value="retry"):
            self.assertEqual(coaching_worker.lambda_handler(event, SimpleNamespace()),
                             {"batchItemFailures": [{"itemIdentifier": "msg-1"}]})

    def test_secure_string_is_decrypted_only_in_coaching_worker(self):
        ssm = Mock()
        ssm.get_parameter.return_value = {"Parameter": {"Value": "test-key"}}
        with patch.dict(os.environ, {"OPENAI_API_KEY_PARAMETER": "/sharp-shooter/dev/openai-api-key"}):
            self.assertEqual(coaching_worker._api_key(ssm_client=ssm), "test-key")
        ssm.get_parameter.assert_called_once_with(
            Name="/sharp-shooter/dev/openai-api-key", WithDecryption=True
        )


if __name__ == "__main__":
    unittest.main()
