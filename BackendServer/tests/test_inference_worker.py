"""Simulated SQS/S3 lifecycle tests for the inference worker."""

from __future__ import annotations

import json
import os
import io
import re
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import inference_worker
from aws_backend import job_store


def s3_event(key: str = "uploads/test-job-id/input.mp4") -> dict:
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": key},
                }
            }
        ]
    }


def sqs_event(
    key: str = "uploads/test-job-id/input.mp4",
    message_id: str = "sqs-message-1",
) -> dict:
    return {
        "Records": [
            {
                "eventSource": "aws:sqs",
                "messageId": message_id,
                "body": json.dumps(s3_event(key)),
            }
        ]
    }


def pending_job() -> dict:
    return {
        "job_id": "test-job-id",
        "status": "pending",
        "attempt_count": 0,
        "s3_bucket": "test-bucket",
        "s3_key": "uploads/test-job-id/input.mp4",
    }


def claimed_job(attempt_count: int = 1, token: str = "worker-1") -> dict:
    return {
        **pending_job(),
        "status": "processing",
        "attempt_count": attempt_count,
        "worker_token": token,
        "lease_expires_at": "2026-01-01T00:15:00.000Z",
    }


class InferenceWorkerTests(unittest.TestCase):
    def test_coaching_queue_failure_does_not_fail_inference(self):
        upload = inference_worker.parse_s3_event(s3_event())[0]
        def fake_download(*, destination, **_kwargs):
            Path(destination).write_bytes(b"input")
        def fake_predict(_video, *, work_dir):
            work_dir.mkdir()
            landmarks = work_dir / "landmarks.csv"
            landmarks.write_text("aggregate source", encoding="utf-8")
            return {"success": True, "artifacts": {"landmarks": str(landmarks)}}
        with (
            patch.dict(os.environ, {
                "COACHING_ENABLED": "1", "RESULT_VIDEO_ENABLED": "0",
                "NBA_REFERENCE_CATALOG_KEY": "", "WORKER_DIAGNOSTICS_ENABLED": "0",
            }),
            patch.object(inference_worker.job_store, "get_job", return_value=pending_job()),
            patch.object(inference_worker.job_store, "mark_job_processing", return_value=claimed_job()),
            patch.object(inference_worker.job_store, "complete_job") as complete,
            patch.object(inference_worker.s3_service, "download_video", side_effect=fake_download),
            patch.object(inference_worker, "predict_video", side_effect=fake_predict),
            patch.object(inference_worker, "build_landmark_summary", return_value={"schema_version": 1}),
            patch.object(inference_worker.coaching_queue, "enqueue", side_effect=RuntimeError("SQS failed")),
        ):
            outcome = inference_worker.process_upload(upload, worker_token="worker-1")
        self.assertEqual(outcome["outcome"], "completed")
        saved = complete.call_args.args[1]
        self.assertEqual(saved["coaching_status"], "unavailable")
        self.assertEqual(saved["coaching_summary"], {"schema_version": 1})

    def test_enhanced_worker_persists_video_and_reference_before_completion(self):
        upload = inference_worker.parse_s3_event(s3_event())[0]
        events = []

        def fake_download(*, destination, **_kwargs):
            Path(destination).write_bytes(b"input")

        def fake_predict(_video, *, work_dir):
            work_dir.mkdir()
            landmarks = work_dir / "landmarks.csv"
            annotated = work_dir / "annotated.avi"
            landmarks.write_text("landmarks", encoding="utf-8")
            annotated.write_bytes(b"avi")
            return {
                "success": True, "player_name": None, "similarity_percentage": None,
                "artifacts": {"landmarks": str(landmarks), "annotated_video": str(annotated)},
            }

        def fake_convert(_source, output):
            output.write_bytes(b"mp4")
            return output

        def fake_upload(**kwargs):
            events.append("video_uploaded")
            self.assertTrue(Path(kwargs["source"]).is_file())

        def fake_complete(_job_id, result, *, worker_token):
            events.append("completed")
            self.assertEqual(worker_token, "worker-1")
            self.assertNotIn("artifacts", result)
            self.assertEqual(result["player_name"], "Example Player")
            self.assertEqual(result["similarity_percentage"], 87.5)
            self.assertEqual(result["player_video_key"], "references/videos/example-abc.mp4")
            self.assertTrue(re.fullmatch(
                r"results/test-job-id/[0-9a-f]{32}\.mp4", result["processed_video_key"]
            ))

        with (
            patch.dict(os.environ, {
                "RESULT_VIDEO_ENABLED": "1",
                "NBA_REFERENCE_CATALOG_KEY": "references/catalog-" + "a" * 64 + ".json",
                "WORKER_DIAGNOSTICS_ENABLED": "0",
            }),
            patch.object(inference_worker.job_store, "get_job", return_value=pending_job()),
            patch.object(inference_worker.job_store, "mark_job_processing", return_value=claimed_job()),
            patch.object(inference_worker.job_store, "complete_job", side_effect=fake_complete),
            patch.object(inference_worker.s3_service, "download_video", side_effect=fake_download),
            patch.object(inference_worker, "predict_video", side_effect=fake_predict),
            patch.object(inference_worker.video_artifacts, "convert_annotated_video", side_effect=fake_convert),
            patch.object(inference_worker.s3_service, "upload_processed_video", side_effect=fake_upload),
            patch.object(inference_worker.reference_catalog, "load_catalog", return_value=("catalog",)),
            patch.object(inference_worker.reference_catalog, "closest_reference", return_value=(
                SimpleNamespace(player_name="Example Player", video_key="references/videos/example-abc.mp4"),
                87.5,
            )),
        ):
            outcome = inference_worker.process_upload(upload, worker_token="worker-1")
        self.assertEqual(outcome["outcome"], "completed")
        self.assertEqual(events, ["video_uploaded", "completed"])

    def test_worker_diagnostics_report_cache_and_tmp_without_changing_result(self):
        sampler = Mock(
            capacity_bytes=550461440,
            before_bytes=49152,
            peak_bytes=5386240,
            after_bytes=61440,
        )
        output = io.StringIO()
        upload = inference_worker.parse_s3_event(s3_event())[0]
        with (
            patch.dict(os.environ, {"WORKER_DIAGNOSTICS_ENABLED": "1"}),
            patch.object(inference_worker, "_TmpUsageSampler", return_value=sampler),
            patch.object(inference_worker, "_detector_cached", side_effect=[False, True]),
            patch.object(inference_worker.job_store, "get_job", return_value=pending_job()),
            patch.object(
                inference_worker.job_store,
                "mark_job_processing",
                return_value=claimed_job(),
            ),
            patch.object(inference_worker.job_store, "complete_job") as complete,
            patch.object(inference_worker.s3_service, "download_video"),
            patch.object(inference_worker, "predict_video", return_value={"success": True}),
            redirect_stdout(output),
        ):
            outcome = inference_worker.process_upload(
                upload, worker_token="worker-1", invocation_number=2
            )
        self.assertEqual(outcome["outcome"], "completed")
        complete.assert_called_once()
        sampler.start.assert_called_once()
        sampler.stop.assert_called_once()
        line = output.getvalue().strip()
        self.assertTrue(line.startswith("WORKER_DIAGNOSTIC "))
        diagnostic = json.loads(line.removeprefix("WORKER_DIAGNOSTIC "))
        self.assertEqual(diagnostic["invocation_number"], 2)
        self.assertFalse(diagnostic["detector_cached_before"])
        self.assertTrue(diagnostic["detector_cached_after"])
        self.assertEqual(diagnostic["tmp_used_peak_sampled_bytes"], 5386240)

    def test_diagnostics_failure_does_not_block_inference(self):
        sampler = Mock()
        sampler.start.side_effect = RuntimeError("metrics unavailable")
        upload = inference_worker.parse_s3_event(s3_event())[0]
        with (
            patch.dict(os.environ, {"WORKER_DIAGNOSTICS_ENABLED": "1"}),
            patch.object(inference_worker, "_TmpUsageSampler", return_value=sampler),
            patch.object(inference_worker, "_detector_cached", return_value=None),
            patch.object(inference_worker.job_store, "get_job", return_value=pending_job()),
            patch.object(
                inference_worker.job_store,
                "mark_job_processing",
                return_value=claimed_job(),
            ),
            patch.object(inference_worker.job_store, "complete_job") as complete,
            patch.object(inference_worker.s3_service, "download_video"),
            patch.object(inference_worker, "predict_video", return_value={"success": True}),
        ):
            outcome = inference_worker.process_upload(upload, worker_token="worker-1")
        self.assertEqual(outcome["outcome"], "completed")
        complete.assert_called_once()

    def test_s3_event_parsing_decodes_key(self):
        upload = inference_worker.parse_s3_event(
            s3_event("uploads%2Ftest-job-id%2Finput.mp4")
        )[0]
        self.assertEqual(upload.job_id, "test-job-id")
        self.assertEqual(upload.extension, ".mp4")

    def test_sqs_event_parsing_extracts_embedded_s3_notification(self):
        message = inference_worker.parse_sqs_event(sqs_event())[0]
        self.assertEqual(message.message_id, "sqs-message-1")
        self.assertEqual(message.upload.bucket, "test-bucket")
        self.assertEqual(message.upload.job_id, "test-job-id")

    @patch.object(inference_worker, "predict_video")
    def test_s3_notification_configuration_probe_is_acknowledged(self, predict):
        event = {
            "Records": [
                {
                    "eventSource": "aws:sqs",
                    "messageId": "s3-test-message",
                    "body": json.dumps(
                        {
                            "Service": "Amazon S3",
                            "Event": "s3:TestEvent",
                            "Bucket": "test-bucket",
                        }
                    ),
                }
            ]
        }
        self.assertEqual(inference_worker.parse_sqs_event(event), [])
        self.assertEqual(
            inference_worker.lambda_handler(event, SimpleNamespace()),
            {"batchItemFailures": []},
        )
        predict.assert_not_called()

    def test_unknown_s3_probe_is_not_acknowledged(self):
        event = {
            "Records": [
                {
                    "messageId": "unknown-message",
                    "body": json.dumps(
                        {"Service": "Amazon S3", "Event": "s3:OtherEvent", "Bucket": "test-bucket"}
                    ),
                }
            ]
        }
        self.assertEqual(
            inference_worker.lambda_handler(event, SimpleNamespace()),
            {"batchItemFailures": [{"itemIdentifier": "unknown-message"}]},
        )

    def test_invalid_s3_or_sqs_event_is_rejected(self):
        with self.assertRaises(ValueError):
            inference_worker.parse_s3_event(s3_event("other/test.mp4"))
        with self.assertRaises(ValueError):
            inference_worker.parse_sqs_event(
                {"Records": [{"messageId": "bad", "body": "not-json"}]}
            )

    @patch.object(inference_worker.job_store, "complete_job")
    @patch.object(inference_worker.job_store, "mark_job_processing")
    @patch.object(inference_worker.job_store, "get_job", return_value=pending_job())
    @patch.object(inference_worker, "predict_video")
    @patch.object(inference_worker.s3_service, "download_video")
    def test_simulated_sqs_upload_completes_and_acknowledges_message(
        self, download, predict, _get_job, claim, complete
    ):
        downloaded_parents = []
        transitions = []

        def fake_download(*, destination, **_kwargs):
            destination = Path(destination)
            downloaded_parents.append(destination.parent)
            destination.write_bytes(b"test-video")
            return destination

        download.side_effect = fake_download
        predict.return_value = {"success": True, "metrics": {"frames": 3}}
        claim.side_effect = lambda *_args, **_kwargs: (
            transitions.append("processing") or claimed_job()
        )
        complete.side_effect = lambda *_args, **_kwargs: transitions.append("completed")

        response = inference_worker.lambda_handler(
            sqs_event(), SimpleNamespace(aws_request_id="worker-1")
        )

        self.assertEqual(response, {"batchItemFailures": []})
        self.assertEqual(claim.call_args.kwargs["worker_token"], "worker-1")
        complete.assert_called_once_with(
            "test-job-id", predict.return_value, worker_token="worker-1"
        )
        self.assertEqual(transitions, ["processing", "completed"])
        self.assertFalse(downloaded_parents[0].exists())

    @patch.object(inference_worker.job_store, "complete_job")
    @patch.object(inference_worker.job_store, "mark_job_processing")
    @patch.object(inference_worker.job_store, "get_job", return_value=pending_job())
    @patch.object(inference_worker, "predict_video", return_value={"success": True})
    @patch.object(inference_worker.s3_service, "download_video")
    def test_successful_reclaimed_attempt_can_complete(
        self, download, predict, _get_job, claim, complete
    ):
        download.side_effect = lambda *, destination, **_kwargs: Path(
            destination
        ).write_bytes(b"test-video")
        claim.return_value = claimed_job(attempt_count=2, token="retry-worker")

        outcome = inference_worker.process_upload(
            inference_worker.parse_s3_event(s3_event())[0],
            worker_token="retry-worker",
            lease_seconds=60,
            max_attempts=3,
        )

        self.assertEqual(outcome["outcome"], "completed")
        complete.assert_called_once_with(
            "test-job-id", predict.return_value, worker_token="retry-worker"
        )

    @patch.object(inference_worker.job_store, "release_job_for_retry")
    @patch.object(inference_worker.job_store, "fail_job")
    @patch.object(inference_worker.job_store, "mark_job_processing")
    @patch.object(inference_worker.job_store, "get_job", return_value=pending_job())
    @patch.object(
        inference_worker,
        "predict_video",
        side_effect=RuntimeError("secret stack detail"),
    )
    @patch.object(inference_worker.s3_service, "download_video")
    def test_failed_attempt_releases_job_and_requests_sqs_retry(
        self, download, _predict, _get_job, claim, fail, release
    ):
        download.side_effect = lambda *, destination, **_kwargs: Path(
            destination
        ).write_bytes(b"test-video")
        claim.return_value = claimed_job(attempt_count=1)

        response = inference_worker.lambda_handler(
            sqs_event(), SimpleNamespace(aws_request_id="worker-1")
        )

        self.assertEqual(
            response,
            {"batchItemFailures": [{"itemIdentifier": "sqs-message-1"}]},
        )
        release.assert_called_once_with("test-job-id", worker_token="worker-1")
        fail.assert_not_called()

    @patch.object(inference_worker.job_store, "release_job_for_retry")
    @patch.object(inference_worker.job_store, "fail_job")
    @patch.object(inference_worker.job_store, "mark_job_processing")
    @patch.object(inference_worker.job_store, "get_job", return_value=pending_job())
    @patch.object(inference_worker, "predict_video", side_effect=RuntimeError("boom"))
    @patch.object(inference_worker.s3_service, "download_video")
    def test_final_failed_attempt_is_dlq_compatible(
        self, download, _predict, _get_job, claim, fail, release
    ):
        download.side_effect = lambda *, destination, **_kwargs: Path(
            destination
        ).write_bytes(b"test-video")
        claim.return_value = claimed_job(attempt_count=3)

        response = inference_worker.lambda_handler(
            sqs_event(), SimpleNamespace(aws_request_id="worker-1")
        )

        fail.assert_called_once_with("test-job-id", worker_token="worker-1")
        release.assert_not_called()
        self.assertEqual(
            response,
            {"batchItemFailures": [{"itemIdentifier": "sqs-message-1"}]},
        )

    @patch.object(inference_worker, "predict_video")
    @patch.object(inference_worker.job_store, "mark_job_processing")
    @patch.object(
        inference_worker.job_store,
        "get_job",
        return_value={**pending_job(), "status": "completed"},
    )
    def test_duplicate_sqs_message_for_completed_job_is_acknowledged(
        self, _get_job, claim, predict
    ):
        response = inference_worker.lambda_handler(
            sqs_event(), SimpleNamespace(aws_request_id="duplicate-worker")
        )
        self.assertEqual(response, {"batchItemFailures": []})
        claim.assert_not_called()
        predict.assert_not_called()

    @patch.object(inference_worker, "predict_video")
    @patch.object(
        inference_worker.job_store,
        "mark_job_processing",
        side_effect=job_store.JobClaimRejectedError(claimed_job()),
    )
    @patch.object(
        inference_worker.job_store,
        "get_job",
        return_value={**pending_job(), "status": "processing"},
    )
    def test_active_lease_keeps_duplicate_message_for_retry(
        self, _get_job, _claim, predict
    ):
        response = inference_worker.lambda_handler(
            sqs_event(), SimpleNamespace(aws_request_id="duplicate-worker")
        )
        self.assertEqual(
            response,
            {"batchItemFailures": [{"itemIdentifier": "sqs-message-1"}]},
        )
        predict.assert_not_called()

    @patch.object(inference_worker.job_store, "fail_expired_job")
    @patch.object(
        inference_worker.job_store,
        "mark_job_processing",
        side_effect=job_store.JobClaimRejectedError(
            claimed_job(attempt_count=3, token="timed-out-worker")
        ),
    )
    @patch.object(
        inference_worker.job_store,
        "get_job",
        return_value={**pending_job(), "status": "processing"},
    )
    def test_expired_exhausted_lease_is_failed_for_dlq(
        self, _get_job, _claim, fail_expired
    ):
        outcome = inference_worker.process_upload(
            inference_worker.parse_s3_event(s3_event())[0],
            worker_token="recovery-worker",
            lease_seconds=60,
            max_attempts=3,
        )
        self.assertEqual(outcome["outcome"], "attempts_exhausted")
        fail_expired.assert_called_once()
        self.assertEqual(
            fail_expired.call_args.kwargs["worker_token"], "timed-out-worker"
        )

    @patch.object(inference_worker, "predict_video")
    @patch.object(inference_worker.job_store, "mark_job_processing")
    @patch.object(inference_worker.job_store, "get_job", return_value=None)
    def test_missing_job_is_not_silently_discarded(self, _get_job, claim, predict):
        response = inference_worker.lambda_handler(
            sqs_event(), SimpleNamespace(aws_request_id="worker-1")
        )
        self.assertEqual(
            response,
            {"batchItemFailures": [{"itemIdentifier": "sqs-message-1"}]},
        )
        claim.assert_not_called()
        predict.assert_not_called()

    @patch.object(inference_worker.job_store, "complete_job")
    @patch.object(inference_worker.job_store, "mark_job_processing")
    @patch.object(inference_worker.job_store, "get_job", return_value=pending_job())
    @patch.object(inference_worker, "predict_video", return_value={"success": True})
    @patch.object(inference_worker.s3_service, "download_video")
    def test_old_worker_cannot_complete_after_lease_is_reclaimed(
        self, download, _predict, _get_job, claim, complete
    ):
        download.side_effect = lambda *, destination, **_kwargs: Path(
            destination
        ).write_bytes(b"test-video")
        claim.return_value = claimed_job(attempt_count=2, token="new-worker")
        complete.side_effect = job_store.JobOwnershipError("test-job-id")

        outcome = inference_worker.process_upload(
            inference_worker.parse_s3_event(s3_event())[0],
            worker_token="old-worker",
            lease_seconds=60,
            max_attempts=3,
        )

        self.assertEqual(outcome["outcome"], "ownership_lost")


if __name__ == "__main__":
    unittest.main()
