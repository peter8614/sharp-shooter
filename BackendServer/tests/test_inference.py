"""Tests for the framework-independent inference boundary."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import inference
from core import models


class InferenceTests(unittest.TestCase):
    def setUp(self):
        models.clear_model_caches()

    def tearDown(self):
        models.clear_model_caches()

    @staticmethod
    def _fake_pipeline(video_path, landmark_dir, trajectory_dir, **_kwargs):
        work_dir = Path(landmark_dir)
        run_dir = Path(trajectory_dir) / Path(video_path).stem
        run_dir.mkdir(parents=True, exist_ok=True)
        landmarks = work_dir / "landmark_data.csv"
        trajectory = run_dir / "trajectory.txt"
        annotated = run_dir / f"output_{Path(video_path).stem}.avi"
        landmarks.write_text("Frame,Left Shoulder\n", encoding="utf-8")
        trajectory.write_text("# frame x y\n", encoding="utf-8")
        annotated.write_bytes(b"avi")
        return {
            "frames": 10,
            "shot_frames": 3,
            "release_frames": 1,
            "landmarks": landmarks,
            "trajectory": trajectory,
            "annotated_video": annotated,
            "run_path": run_dir,
        }

    @staticmethod
    def _fake_classification(**kwargs):
        domain = kwargs["domain"]
        return {
            "label": "good" if domain == "form" else "bad",
            "confidence": 0.75,
            "coaching_labels": [f"{domain}_label"],
        }

    def test_explicit_workspace_retains_json_serializable_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            video = root / "shot.mp4"
            video.write_bytes(b"video")
            work_dir = root / "job-123"

            with (
                patch.object(inference, "break_down_video", self._fake_pipeline),
                patch.object(inference, "_classify", self._fake_classification),
                patch.object(
                    inference,
                    "compare_user_to_player",
                    return_value=("Reference Player", 91.5, None),
                ),
            ):
                result = inference.predict_video(video, work_dir=work_dir)

            self.assertTrue(result["success"])
            self.assertEqual(result["form_classification"], "good")
            self.assertEqual(result["trajectory_classification"], "bad")
            self.assertEqual(result["metrics"]["frames"], 10)
            self.assertTrue(Path(result["artifacts"]["landmarks"]).is_file())
            self.assertEqual(json.loads(json.dumps(result)), result)

    def test_default_workspace_is_temporary_and_not_exposed(self):
        observed_work_dirs = []

        def capture_pipeline(video_path, landmark_dir, trajectory_dir, **kwargs):
            observed_work_dirs.append(Path(landmark_dir))
            return self._fake_pipeline(
                video_path, landmark_dir, trajectory_dir, **kwargs
            )

        with tempfile.TemporaryDirectory() as temporary_dir:
            video = Path(temporary_dir) / "shot.mp4"
            video.write_bytes(b"video")
            with (
                patch.object(inference, "break_down_video", capture_pipeline),
                patch.object(inference, "_classify", self._fake_classification),
                patch.object(
                    inference,
                    "compare_user_to_player",
                    return_value=(None, None, None),
                ),
            ):
                result = inference.predict_video(video)

        self.assertNotIn("artifacts", result)
        self.assertEqual(len(observed_work_dirs), 1)
        self.assertFalse(observed_work_dirs[0].exists())

    def test_missing_video_fails_before_pipeline_runs(self):
        with patch.object(inference, "break_down_video") as pipeline:
            with self.assertRaises(FileNotFoundError):
                inference.predict_video("missing-video.mp4")
        pipeline.assert_not_called()

    def test_model_bundles_are_cached_for_warm_invocations(self):
        sentinel = {"model": object()}
        with patch.object(models, "load_landmark_model", return_value=sentinel) as loader:
            first = models.get_landmark_model()
            second = models.get_landmark_model()
        self.assertIs(first, sentinel)
        self.assertIs(second, sentinel)
        loader.assert_called_once_with(models.LANDMARK_MODEL_PATH)


if __name__ == "__main__":
    unittest.main()
