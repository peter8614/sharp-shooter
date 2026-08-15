"""Regression tests for reproducible model metrics and report artifacts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier

from model_evaluation import evaluate_repeated_stratified_cv, write_evaluation_report


class ModelEvaluationTests(unittest.TestCase):
    def setUp(self):
        # A deliberately uninformative classifier makes the safety failure easy
        # to verify: every bad-form recording is incorrectly reported as good.
        self.features = pd.DataFrame(
            {"feature": np.arange(20, dtype=float), "secondary": np.arange(20) % 3}
        )
        self.labels = pd.Series([0] * 10 + [1] * 10)

    def _evaluate(self) -> dict:
        return evaluate_repeated_stratified_cv(
            lambda: DummyClassifier(strategy="constant", constant=1),
            self.features,
            self.labels,
            {0: "bad_form", 1: "good_form"},
            priority_label=0,
            n_splits=2,
            n_repeats=3,
            bootstrap_samples=100,
            random_state=7,
        )

    def test_fixed_metrics_expose_false_good_predictions(self):
        report = self._evaluate()

        expected_metrics = {
            "accuracy",
            "balanced_accuracy",
            "macro_precision",
            "macro_recall",
            "macro_f1",
            "recall_class_0",
            "recall_class_1",
        }
        self.assertEqual(set(report["metrics"]), expected_metrics)
        self.assertEqual(report["metrics"]["recall_class_0"]["value"], 0.0)
        self.assertEqual(report["priority_class"]["false_good_rate"]["value"], 1.0)
        self.assertEqual(report["confusion_matrix"]["values"], [[0, 30], [0, 30]])

        # Every published estimate must carry a bounded 95% interval.
        for metric in report["metrics"].values():
            self.assertLessEqual(0.0, metric["ci_lower"])
            self.assertLessEqual(metric["ci_lower"], metric["value"])
            self.assertLessEqual(metric["value"], metric["ci_upper"])
            self.assertLessEqual(metric["ci_upper"], 1.0)

    def test_report_writer_creates_machine_and_human_readable_outputs(self):
        report = self._evaluate()
        with tempfile.TemporaryDirectory() as directory:
            paths = write_evaluation_report(report, Path(directory) / "pose-evaluation")

            self.assertEqual(json.loads(paths["json"].read_text(encoding="utf-8")), report)
            markdown = paths["markdown"].read_text(encoding="utf-8")
            self.assertIn("Macro F1", markdown)
            self.assertIn("False-good rate", markdown)
            self.assertIn("Confusion matrix", markdown)
            self.assertIn("bad_form,0,30", paths["confusion_matrix"].read_text(encoding="utf-8"))

    def test_five_fold_evaluation_requires_five_recordings_per_class(self):
        with self.assertRaisesRegex(ValueError, "At least 5 recordings per class"):
            evaluate_repeated_stratified_cv(
                lambda: DummyClassifier(strategy="most_frequent"),
                self.features.iloc[:12],
                pd.Series([0] * 3 + [1] * 9),
                {0: "bad_form", 1: "good_form"},
                n_splits=5,
                bootstrap_samples=10,
            )


if __name__ == "__main__":
    unittest.main()
