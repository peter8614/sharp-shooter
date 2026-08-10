"""Focused regression tests for video-level feature extraction."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from landmark_classification import LANDMARK_NAMES, extract_landmark_features
from trajectory_classification import SAMPLE_COUNT, extract_trajectory_features


class FeatureExtractionTests(unittest.TestCase):
    def test_landmarks_create_one_finite_video_row(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "landmarks.csv"
            with path.open("w", newline="", encoding="utf-8") as output:
                writer = csv.writer(output)
                writer.writerow(["Frame", *LANDMARK_NAMES])
                writer.writerow([1, "0,0,0", "2,0,0", "0,1,0", "2,1,0", "0,2,0", "2,2,0"])
                writer.writerow([2, "0,0,0", "2,0,0", "0,1.2,0", "2,1.2,0", "0,2.2,0", "2,2.2,0"])
            features = extract_landmark_features(path)
            self.assertEqual(len(features), 1)
            self.assertFalse(features.isna().any().any())

    def test_legacy_and_framed_trajectories_share_a_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy = Path(directory) / "legacy.txt"
            framed = Path(directory) / "framed.txt"
            legacy.write_text("0 10\n2 8\n4 10\n", encoding="utf-8")
            framed.write_text("frame x y\n0 0 10\n2 2 8\n4 4 10\n", encoding="utf-8")
            legacy_features = extract_trajectory_features(legacy)
            framed_features = extract_trajectory_features(framed)
            self.assertEqual(list(legacy_features.columns), list(framed_features.columns))
            self.assertEqual(sum(name.startswith("x_") for name in legacy_features), SAMPLE_COUNT)


if __name__ == "__main__":
    unittest.main()
