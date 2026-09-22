"""Tests for the local Lambda image validation boundary."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lambda_container_smoke
from scripts.verify_lambda_assets import AssetVerificationError, verify_assets


BACKEND_ROOT = Path(__file__).resolve().parents[1]


class LambdaAssetTests(unittest.TestCase):
    def _manifest(self, root: Path, content: bytes) -> Path:
        manifest = root / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "assets": [
                        {
                            "path": "models/example.bin",
                            "size_bytes": len(content),
                            "sha256": hashlib.sha256(content).hexdigest(),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def test_model_manifest_accepts_exact_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "models" / "example.bin"
            model.parent.mkdir()
            model.write_bytes(b"trusted-model")
            verified = verify_assets(root, self._manifest(root, b"trusted-model"))
        self.assertEqual(verified[0]["path"], "models/example.bin")

    def test_model_manifest_rejects_altered_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "models" / "example.bin"
            model.parent.mkdir()
            model.write_bytes(b"altered")
            manifest = self._manifest(root, b"trusted")
            with self.assertRaises(AssetVerificationError):
                verify_assets(root, manifest)

    def test_lambda_dockerfile_preserves_production_worker_contract(self):
        dockerfile = (BACKEND_ROOT / "Dockerfile.lambda-worker").read_text(
            encoding="utf-8"
        )
        self.assertIn("public.ecr.aws/lambda/python:3.12", dockerfile)
        self.assertIn("torch==2.4.1+cpu", dockerfile)
        self.assertIn("verify_lambda_assets.py", dockerfile)
        self.assertIn('CMD ["inference_worker.lambda_handler"]', dockerfile)
        self.assertNotIn("gunicorn", dockerfile)


class LambdaContainerSmokeTests(unittest.TestCase):
    def setUp(self):
        lambda_container_smoke._invocation_count = 0

    def test_handler_reports_cold_then_warm_and_removes_artifact_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            videos = root / "videos"
            work = root / "work"
            videos.mkdir()
            video = videos / "shot.mp4"
            video.write_bytes(b"video")

            def fake_predict(_video, *, work_dir, **_kwargs):
                artifact = Path(work_dir) / "output.avi"
                artifact.parent.mkdir(parents=True, exist_ok=True)
                artifact.write_bytes(b"artifact")
                return {
                    "success": True,
                    "form_classification": "good",
                    "artifacts": {"annotated_video": str(artifact)},
                }

            environment = {
                "SHARP_SHOOTER_LOCAL_SMOKE": "1",
                "LOCAL_VIDEO_ROOT": str(videos),
                "LOCAL_WORK_ROOT": str(work),
            }
            with (
                patch.dict(os.environ, environment, clear=False),
                patch.object(
                    lambda_container_smoke,
                    "predict_video",
                    side_effect=fake_predict,
                ),
                patch.object(
                    lambda_container_smoke,
                    "detector_is_cached",
                    side_effect=[False, True, True, True],
                ),
            ):
                first = lambda_container_smoke.lambda_handler(
                    {"video_path": str(video)}, None
                )
                second = lambda_container_smoke.lambda_handler(
                    {"video_path": str(video)}, None
                )

        self.assertTrue(first["runtime"]["cold_start"])
        self.assertFalse(first["runtime"]["model_reused"])
        self.assertFalse(second["runtime"]["cold_start"])
        self.assertTrue(second["runtime"]["model_reused"])
        self.assertNotIn("artifacts", first["result"])
        self.assertGreater(first["runtime"]["temporary_job_bytes"], 0)
        self.assertEqual(list(work.glob("phase7-*")), [])

    def test_handler_rejects_video_outside_mount(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            videos = root / "videos"
            videos.mkdir()
            outside = root / "outside.mp4"
            outside.write_bytes(b"video")
            with patch.dict(
                os.environ,
                {
                    "SHARP_SHOOTER_LOCAL_SMOKE": "1",
                    "LOCAL_VIDEO_ROOT": str(videos),
                    "LOCAL_WORK_ROOT": str(root / "work"),
                },
                clear=False,
            ):
                with self.assertRaises(ValueError):
                    lambda_container_smoke.lambda_handler(
                        {"video_path": str(outside)}, None
                    )

    def test_handler_rejects_unknown_pipeline(self):
        with patch.dict(os.environ, {"SHARP_SHOOTER_LOCAL_SMOKE": "1"}):
            with self.assertRaises(ValueError):
                lambda_container_smoke.lambda_handler(
                    {"pipeline": "unknown"}, None
                )

    def test_handler_is_disabled_without_explicit_local_flag(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                lambda_container_smoke.lambda_handler({}, None)


if __name__ == "__main__":
    unittest.main()
