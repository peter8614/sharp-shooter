"""Tests for the Lambda-compatible create/read job APIs."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from aws_backend import s3_service
from job_api import create_job, get_job, get_video


class JobApiTests(unittest.TestCase):
    def test_dev_get_function_receives_upload_bucket_for_video_links(self):
        template = (
            Path(__file__).resolve().parents[2] / "infra" / "phase8" / "dev.yaml"
        ).read_text(encoding="utf-8")
        get_function = template.split("\n  GetFunction:\n", 1)[1].split(
            "\n  CoachingFunction:\n", 1
        )[0]
        self.assertIn("UPLOAD_BUCKET: !Ref UploadBucket", get_function)

    @patch.object(create_job.uuid, "uuid4", return_value="fixed-job-id")
    @patch.object(create_job.s3_service, "generate_upload_url", return_value="https://upload")
    @patch.object(create_job.job_store, "create_job")
    def test_create_job_ignores_filename_for_object_key(
        self, create_item, generate_url, _uuid
    ):
        response = create_job.create_job(
            {"filename": "../../untrusted.exe", "content_type": "video/mp4"},
            bucket="test-bucket",
        )

        self.assertEqual(
            response,
            {
                "job_id": "fixed-job-id",
                "upload_url": "https://upload",
                "status": "pending",
            },
        )
        create_item.assert_called_once_with(
            job_id="fixed-job-id",
            s3_bucket="test-bucket",
            s3_key="uploads/fixed-job-id/input.mp4",
        )
        generate_url.assert_called_once_with(
            bucket="test-bucket",
            key="uploads/fixed-job-id/input.mp4",
            content_type="video/mp4",
        )

    def test_create_handler_rejects_unsupported_mime_type(self):
        response = create_job.lambda_handler(
            {
                "body": json.dumps(
                    {"filename": "shot.webm", "content_type": "video/webm"}
                )
            },
            None,
        )
        self.assertEqual(response["statusCode"], 415)
        self.assertNotIn("trace", response["body"].lower())

    @patch.object(create_job.uuid, "uuid4", return_value="app-job")
    @patch.object(create_job.s3_service, "generate_upload_url", return_value="https://upload")
    @patch.object(create_job, "upload_bucket", return_value="test-bucket")
    @patch.object(create_job.job_store, "create_job")
    def test_app_create_stores_jwt_subject(self, create_item, _bucket, _url, _uuid):
        response = create_job.lambda_handler(
            {
                "routeKey": "POST /app/jobs",
                "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "user-a"}}}},
                "body": json.dumps({"filename": "shot.mp4", "content_type": "video/mp4"}),
            },
            None,
        )
        self.assertEqual(response["statusCode"], 201)
        self.assertEqual(create_item.call_args.kwargs["owner_sub"], "user-a")

    def test_app_create_rejects_missing_subject(self):
        response = create_job.lambda_handler(
            {"routeKey": "POST /app/jobs", "body": "{}"}, None
        )
        self.assertEqual(response["statusCode"], 401)

    @patch.object(get_job.job_store, "get_job")
    def test_get_pending_job_has_stable_public_contract(self, read_job):
        read_job.return_value = {
            "job_id": "job-1",
            "status": "pending",
            "created_at": "private",
            "s3_bucket": "private",
            "s3_key": "private",
        }
        self.assertEqual(
            get_job.get_job("job-1"), {"job_id": "job-1", "status": "pending"}
        )

    @patch.object(get_job.job_store, "get_job")
    def test_get_completed_job_includes_existing_result(self, read_job):
        result = {"success": True, "form_confidence": 0.9}
        read_job.return_value = {
            "job_id": "job-1",
            "status": "completed",
            "result": result,
        }
        self.assertEqual(get_job.get_job("job-1")["result"], result)

    @patch.object(get_job.job_store, "get_job")
    def test_get_job_exposes_availability_not_private_s3_keys(self, read_job):
        read_job.return_value = {
            "job_id": "job-1", "status": "completed", "owner_sub": "user-a",
            "result": {
                "processed_video_key": "results/job-1/" + "a" * 32 + ".mp4",
                "player_video_key": "references/videos/player-abc.mp4",
                "player_name": "Example Player",
                "coaching_status": "queued",
                "coaching_summary": {"private": "aggregate"},
            },
        }
        result = get_job.get_job("job-1", owner_sub="user-a")["result"]
        self.assertTrue(result["processed_video_available"])
        self.assertTrue(result["reference_video_available"])
        self.assertNotIn("processed_video_key", result)
        self.assertNotIn("player_video_key", result)
        self.assertNotIn("coaching_summary", result)
        self.assertEqual(result["coaching_status"], "queued")

    @patch.object(get_video.s3_service, "generate_download_url", return_value="https://signed")
    @patch.object(get_video, "upload_bucket", return_value="test-bucket")
    @patch.object(get_video.job_store, "get_job")
    def test_video_link_requires_owner_and_valid_key(self, read_job, _bucket, sign):
        key = "results/job-1/" + "a" * 32 + ".mp4"
        read_job.return_value = {
            "job_id": "job-1", "status": "completed", "owner_sub": "user-a",
            "result": {"processed_video_key": key},
        }
        self.assertIsNone(get_video.video_link("job-1", "processed", "user-b"))
        sign.assert_not_called()
        self.assertEqual(get_video.video_link("job-1", "processed", "user-a"), "https://signed")
        sign.assert_called_once_with(bucket="test-bucket", key=key)
        read_job.return_value["result"]["processed_video_key"] = "uploads/other/input.mp4"
        with self.assertRaises(ValueError):
            get_video.video_link("job-1", "processed", "user-a")

    @patch.object(get_video.s3_service, "generate_download_url", return_value="https://signed")
    @patch.object(get_video, "upload_bucket", return_value="test-bucket")
    @patch.object(get_video.job_store, "get_job")
    def test_jwt_video_route_rejects_other_user_and_signs_reference(self, read_job, _bucket, sign):
        read_job.return_value = {
            "job_id": "job-1", "status": "completed", "owner_sub": "user-a",
            "result": {"player_video_key": "references/videos/example-a1.mp4"},
        }
        event = {
            "routeKey": "GET /app/jobs/{job_id}/videos/{video_kind}",
            "pathParameters": {"job_id": "job-1", "video_kind": "reference"},
            "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "user-b"}}}},
        }
        self.assertEqual(get_job.lambda_handler(event, None)["statusCode"], 404)
        event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"] = "user-a"
        response = get_job.lambda_handler(event, None)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(json.loads(response["body"])["expires_in"], 300)
        sign.assert_called_once_with(bucket="test-bucket", key="references/videos/example-a1.mp4")

    @patch.object(get_job.job_store, "get_job")
    def test_get_processing_job_has_no_internal_fields(self, read_job):
        read_job.return_value = {
            "job_id": "job-1",
            "status": "processing",
            "updated_at": "private",
        }
        self.assertEqual(
            get_job.get_job("job-1"),
            {"job_id": "job-1", "status": "processing"},
        )

    @patch.object(get_job.job_store, "get_job")
    def test_get_failed_job_exposes_only_safe_error(self, read_job):
        read_job.return_value = {
            "job_id": "job-1",
            "status": "failed",
            "error": "Video processing failed.",
        }
        self.assertEqual(
            get_job.get_job("job-1"),
            {
                "job_id": "job-1",
                "status": "failed",
                "error": "Video processing failed.",
            },
        )

    @patch.object(get_job.job_store, "get_job", return_value=None)
    def test_get_handler_returns_404_for_missing_job(self, _read_job):
        response = get_job.lambda_handler(
            {"pathParameters": {"job_id": "missing"}}, None
        )
        self.assertEqual(response["statusCode"], 404)
        self.assertEqual(json.loads(response["body"]), {"error": "Job not found."})

    @patch.object(get_job.job_store, "get_job")
    def test_app_get_only_returns_own_job(self, read_job):
        read_job.return_value = {
            "job_id": "job-1", "status": "completed", "owner_sub": "user-a",
            "result": {"success": True},
        }
        event = {
            "routeKey": "GET /app/jobs/{job_id}",
            "pathParameters": {"job_id": "job-1"},
            "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "user-b"}}}},
        }
        self.assertEqual(get_job.lambda_handler(event, None)["statusCode"], 404)
        event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"] = "user-a"
        own_response = get_job.lambda_handler(event, None)
        self.assertEqual(own_response["statusCode"], 200)
        self.assertEqual(json.loads(own_response["body"])["result"], {"success": True})

    @patch.object(get_job.job_store, "get_job")
    def test_app_cannot_read_legacy_iam_job(self, read_job):
        read_job.return_value = {"job_id": "legacy", "status": "completed", "result": {}}
        event = {
            "routeKey": "GET /app/jobs/{job_id}",
            "pathParameters": {"job_id": "legacy"},
            "requestContext": {"authorizer": {"jwt": {"claims": {"sub": "user-a"}}}},
        }
        self.assertEqual(get_job.lambda_handler(event, None)["statusCode"], 404)

    def test_presigned_url_interface_includes_required_put_headers(self):
        client = Mock()
        client.generate_presigned_url.return_value = "https://signed"
        result = s3_service.generate_upload_url(
            bucket="videos",
            key="uploads/job-1/input.mov",
            content_type="video/quicktime",
            expires_in=300,
            client=client,
        )
        self.assertEqual(result, "https://signed")
        client.generate_presigned_url.assert_called_once_with(
            "put_object",
            Params={
                "Bucket": "videos",
                "Key": "uploads/job-1/input.mov",
                "ContentType": "video/quicktime",
            },
            ExpiresIn=300,
        )

    def test_private_video_upload_and_short_download_url(self):
        client = Mock()
        s3_service.upload_processed_video(
            bucket="videos", key="results/job-1/shot.mp4", source="shot.mp4", client=client
        )
        client.upload_file.assert_called_once_with(
            "shot.mp4", "videos", "results/job-1/shot.mp4",
            ExtraArgs={"ContentType": "video/mp4", "ServerSideEncryption": "AES256"},
        )
        s3_service.generate_download_url(
            bucket="videos", key="results/job-1/shot.mp4", client=client
        )
        client.generate_presigned_url.assert_called_once_with(
            "get_object", Params={"Bucket": "videos", "Key": "results/job-1/shot.mp4"},
            ExpiresIn=300,
        )


if __name__ == "__main__":
    unittest.main()
