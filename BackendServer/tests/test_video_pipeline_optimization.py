"""Regression guards for the in-process, disk-light video pipeline."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

import video_pipeline
import yolo_detector


class _EmptyDetector:
    load_seconds = 0.25

    def detect(self, _frame):
        return []


class VideoPipelineOptimizationTests(unittest.TestCase):
    def test_in_memory_jpeg_matches_default_disk_round_trip(self):
        generator = np.random.default_rng(42)
        frame = generator.integers(0, 256, size=(48, 64, 3), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "frame.jpg"
            self.assertTrue(cv2.imwrite(str(image_path), frame))
            disk_frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        memory_frame = video_pipeline._jpeg_compatibility_frame(frame)
        np.testing.assert_array_equal(memory_frame, disk_frame)

    def test_optimized_pipeline_creates_no_frame_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video_path = root / "input.avi"
            writer = cv2.VideoWriter(
                str(video_path),
                cv2.VideoWriter_fourcc(*"MJPG"),
                10.0,
                (64, 48),
            )
            self.assertTrue(writer.isOpened())
            for value in (0, 64, 128):
                writer.write(np.full((48, 64, 3), value, dtype=np.uint8))
            writer.release()

            with (
                patch.object(video_pipeline, "detector_is_cached", return_value=False),
                patch.object(
                    video_pipeline, "get_detector", return_value=_EmptyDetector()
                ),
            ):
                run_path = video_pipeline.process_video_in_memory(
                    video_path,
                    root / "output",
                    capture_diagnostics=True,
                )

            self.assertFalse((run_path / "images_raw").exists())
            self.assertFalse((run_path / "images_draw").exists())
            self.assertFalse((run_path / "labels").exists())
            self.assertTrue((run_path / "output_input.avi").is_file())
            self.assertTrue((run_path / "trajectory.txt").is_file())
            diagnostics = json.loads(
                (run_path / "detections.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(diagnostics), 3)
            metrics = json.loads(
                (run_path / "pipeline_metrics.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metrics["frames"], 3)
            self.assertFalse(metrics["model_reused"])

    def test_detector_singleton_loads_once_per_weights_and_device(self):
        sentinel = object()
        yolo_detector.clear_detector_cache()
        with patch.object(
            yolo_detector, "YoloDetector", return_value=sentinel
        ) as constructor:
            first = yolo_detector.get_detector(device="cpu")
            second = yolo_detector.get_detector(device="cpu")
        self.assertIs(first, sentinel)
        self.assertIs(second, sentinel)
        constructor.assert_called_once()
        yolo_detector.clear_detector_cache()

    def test_detector_settings_match_legacy_detect_defaults(self):
        detector = yolo_detector.YoloDetector
        self.assertEqual(detector.image_size, (640, 640))
        self.assertEqual(detector.confidence_threshold, 0.25)
        self.assertEqual(detector.iou_threshold, 0.45)
        self.assertEqual(detector.maximum_detections, 1000)
        self.assertIsNone(detector.classes)
        self.assertFalse(detector.agnostic_nms)
        self.assertFalse(detector.half)
        self.assertFalse(detector.dnn)


if __name__ == "__main__":
    unittest.main()
