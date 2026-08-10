import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

import landmark_classification
import trajectory_classification
from main import detect_shooting_motion
from utils.draw import draw_trajectory


def landmark(x, y, visibility=1.0):
    return SimpleNamespace(x=x, y=y, z=0.0, visibility=visibility)


class CoreTests(unittest.TestCase):
    def test_right_arm_release_uses_correct_landmarks(self):
        points = [landmark(0, 0, 0) for _ in range(33)]
        points[12] = landmark(0.5, 0.5)
        points[14] = landmark(0.5, 0.3)
        points[16] = landmark(0.5, 0.1)
        pose = SimpleNamespace(landmark=points)

        shooting, angle, released = detect_shooting_motion(
            pose, "R", previous_arm_angle=2.0
        )
        self.assertTrue(shooting)
        self.assertTrue(released)
        self.assertAlmostEqual(angle, np.pi)

    def test_trajectory_loader_reads_without_modifying_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trajectory.txt"
            original = "0 0\n10 20\n20 30\n"
            path.write_text(original, encoding="utf-8")
            sample = trajectory_classification.load_trajectory(path, 1)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual(sample.loc[0, "Label"], 1)
            self.assertEqual(len(sample), 1)

    def test_landmark_loader_creates_one_video_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "landmarks.csv"
            columns = [
                "Frame",
                "Left Shoulder",
                "Right Shoulder",
                "Left Elbow",
                "Right Elbow",
                "Left Wrist",
                "Right Wrist",
            ]
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(columns)
                writer.writerow([0, *(["0.1,0.2,0.3"] * 6)])
                writer.writerow([1, *(["0.2,0.3,0.4"] * 6)])
            sample = landmark_classification.load_single_landmark_file(path, 0)
            self.assertEqual(len(sample), 1)
            self.assertEqual(sample.loc[0, "frame_count"], 2)

    def test_trajectory_drawing_preserves_frames_without_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images = root / "images"
            labels = root / "labels"
            output = root / "output"
            images.mkdir()
            labels.mkdir()
            output.mkdir()
            for index in range(3):
                cv2.imwrite(
                    str(images / f"{index:05d}.jpg"),
                    np.zeros((20, 20, 3), dtype=np.uint8),
                )
            points = draw_trajectory(labels, images, output)
            self.assertEqual(points, [])
            self.assertEqual(len(list(output.glob("*.jpg"))), 3)


if __name__ == "__main__":
    unittest.main()
