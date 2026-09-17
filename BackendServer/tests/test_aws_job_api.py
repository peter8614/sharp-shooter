"""Tests for the Lambda-compatible create/read job APIs."""

from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

from aws_backend import s3_service
from job_api import create_job, get_job


class JobApiTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
