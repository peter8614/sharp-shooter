"""Tests for deterministic, training-backed coaching labels."""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from coaching_labels import (
    build_good_form_reference_profile,
    generate_prediction_labels,
    prediction_confidence,
    sanitize_coaching_context,
)


class FakeProbabilityModel:
    """Small estimator double that exposes a known class probability."""

    classes_ = np.asarray([0, 1])

    def predict_proba(self, features):
        return np.asarray([[0.82, 0.18]])


class CoachingLabelTests(unittest.TestCase):
    def test_reference_profile_uses_only_good_form_rows(self):
        features = pd.DataFrame(
            {
                "left_elbow_angle_mean": [80, 100, 102, 104, 106, 108],
                "right_elbow_angle_mean": [70, 90, 92, 94, 96, 98],
                "Left Wrist_y_mean": [1.0, -0.5, -0.4, -0.3, -0.2, -0.1],
                "Right Wrist_y_mean": [1.0, -0.4, -0.3, -0.2, -0.1, 0.0],
            }
        )
        labels = pd.Series([0, 1, 1, 1, 1, 1])

        profile = build_good_form_reference_profile(features, labels)

        self.assertEqual(profile["left_elbow_angle_mean"]["sample_count"], 5)
        self.assertGreater(profile["left_elbow_angle_mean"]["low"], 90)

    def test_bad_form_prediction_creates_specific_ranked_label(self):
        features = pd.DataFrame(
            [{
                "left_elbow_angle_mean": 60.0,
                "right_elbow_angle_mean": 94.0,
                "Left Wrist_y_mean": -0.3,
                "Right Wrist_y_mean": -0.2,
            }]
        )
        profile = {
            "left_elbow_angle_mean": {
                "median": 104.0,
                "low": 100.0,
                "high": 108.0,
                "sample_count": 12,
            }
        }

        labels = generate_prediction_labels(
            "form", "bad", 0.82, features, profile
        )

        self.assertEqual(labels[0]["code"], "form_model_flagged")
        self.assertEqual(labels[1]["code"], "left_elbow_angle_below_good_reference")
        self.assertEqual(labels[1]["evidence"]["observed"], 60.0)
        self.assertEqual(labels[1]["evidence"]["reference_low"], 100.0)
        self.assertLessEqual(labels[1]["confidence"], 0.82)

    def test_old_bundle_without_reference_does_not_invent_specific_issue(self):
        labels = generate_prediction_labels(
            "form", "bad", 0.75, pd.DataFrame([{"left_elbow_angle_mean": 50.0}])
        )

        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0]["code"], "form_model_flagged")
        self.assertIn("Retrain", labels[0]["coaching_goal"])

    def test_probability_matches_the_predicted_class(self):
        confidence = prediction_confidence(
            FakeProbabilityModel(), pd.DataFrame([[1.0]]), 0
        )
        self.assertEqual(confidence, 0.82)

    def test_context_sanitizer_drops_unknown_fields(self):
        safe = sanitize_coaching_context(
            {
                "form_classification": "bad",
                "form_confidence": 1.2,
                "private_path": "C:/private/video.mp4",
                "coaching_labels": [{
                    "code": "form_model_flagged",
                    "status": "needs_attention",
                    "area": "form",
                    "confidence": 0.7,
                    "severity": "medium",
                    "evidence": {"classification": "bad"},
                    "coaching_goal": "Review the supported evidence.",
                    "practice": "Record from the same camera position.",
                    "private_path": "C:/private/video.mp4",
                }],
            }
        )

        self.assertEqual(safe["form_confidence"], 1.0)
        self.assertNotIn("private_path", safe)
        self.assertNotIn("private_path", safe["coaching_labels"][0])


if __name__ == "__main__":
    unittest.main()
