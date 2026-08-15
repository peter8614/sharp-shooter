"""Reusable evaluation and reporting for the two video classifiers.

The evaluator keeps every recording intact, produces one out-of-fold prediction
per repeat, and bootstraps whole recordings when estimating uncertainty. This
avoids treating repeated predictions for the same video as independent samples.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Callable, Mapping

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import RepeatedStratifiedKFold


MetricValues = dict[str, float]


def _validate_inputs(
    features: pd.DataFrame,
    labels: pd.Series,
    label_names: Mapping[int, str],
    n_splits: int,
) -> list[int]:
    """Validate the class contract required by repeated stratified folds."""
    if len(features) != len(labels) or len(labels) == 0:
        raise ValueError("Features and labels must contain the same non-zero number of rows")
    if features.isna().any().any():
        raise ValueError("Evaluation features must not contain missing values")

    observed_labels = sorted(int(value) for value in labels.unique())
    configured_labels = sorted(int(value) for value in label_names)
    if observed_labels != configured_labels:
        raise ValueError(
            f"Configured labels {configured_labels} do not match observed labels {observed_labels}"
        )
    if labels.value_counts().min() < n_splits:
        raise ValueError(f"At least {n_splits} recordings per class are required for evaluation")
    return configured_labels


def _metric_values(
    truth: np.ndarray,
    predictions: np.ndarray,
    class_labels: list[int],
) -> MetricValues:
    """Calculate fixed aggregate metrics with all configured classes present."""
    recalls = recall_score(
        truth,
        predictions,
        labels=class_labels,
        average=None,
        zero_division=0,
    )
    return {
        "accuracy": float(accuracy_score(truth, predictions)),
        # Balanced accuracy is the unweighted mean of the class recalls. Using
        # the explicit recall array keeps bootstrap samples with a missing class
        # well-defined instead of allowing sklearn to silently drop that class.
        "balanced_accuracy": float(np.mean(recalls)),
        "macro_precision": float(
            precision_score(
                truth,
                predictions,
                labels=class_labels,
                average="macro",
                zero_division=0,
            )
        ),
        "macro_recall": float(np.mean(recalls)),
        "macro_f1": float(
            f1_score(
                truth,
                predictions,
                labels=class_labels,
                average="macro",
                zero_division=0,
            )
        ),
        **{
            f"recall_class_{label}": float(value)
            for label, value in zip(class_labels, recalls)
        },
    }


def _bootstrap_confidence_intervals(
    labels: np.ndarray,
    predictions_by_repeat: np.ndarray,
    class_labels: list[int],
    confidence_level: float,
    bootstrap_samples: int,
    random_state: int,
) -> dict[str, dict[str, float]]:
    """Estimate percentile intervals by resampling recordings within classes."""
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must be between zero and one")
    if bootstrap_samples < 1:
        raise ValueError("bootstrap_samples must be positive")

    rng = np.random.default_rng(random_state)
    sampled_metrics: dict[str, list[float]] = {}
    for _ in range(bootstrap_samples):
        # Stratified resampling retains every class in small bootstrap samples.
        # Each selected recording contributes all repeated predictions, thereby
        # preserving the dependency within that recording.
        indices = np.concatenate(
            [
                rng.choice(
                    np.flatnonzero(labels == label),
                    size=int(np.sum(labels == label)),
                    replace=True,
                )
                for label in class_labels
            ]
        )
        rng.shuffle(indices)
        sampled_truth = np.tile(labels[indices], predictions_by_repeat.shape[0])
        sampled_predictions = predictions_by_repeat[:, indices].reshape(-1)
        values = _metric_values(sampled_truth, sampled_predictions, class_labels)
        for name, value in values.items():
            sampled_metrics.setdefault(name, []).append(value)

    tail = (1.0 - confidence_level) / 2.0
    return {
        name: {
            "lower": float(np.quantile(values, tail)),
            "upper": float(np.quantile(values, 1.0 - tail)),
        }
        for name, values in sampled_metrics.items()
    }


def evaluate_repeated_stratified_cv(
    model_factory: Callable[[], BaseEstimator],
    features: pd.DataFrame,
    labels: pd.Series,
    label_names: Mapping[int, str],
    *,
    priority_label: int | None = None,
    n_splits: int = 5,
    n_repeats: int = 10,
    confidence_level: float = 0.95,
    bootstrap_samples: int = 2_000,
    random_state: int = 42,
) -> dict:
    """Run repeated stratified CV and return a serialization-safe report."""
    class_labels = _validate_inputs(features, labels, label_names, n_splits)
    if priority_label is not None and priority_label not in class_labels:
        raise ValueError("priority_label must be one of the configured labels")
    if n_repeats < 1:
        raise ValueError("n_repeats must be positive")

    label_values = labels.to_numpy(dtype=int)
    predictions_by_repeat = np.empty((n_repeats, len(labels)), dtype=int)
    prediction_counts = np.zeros((n_repeats, len(labels)), dtype=int)
    splitter = RepeatedStratifiedKFold(
        n_splits=n_splits,
        n_repeats=n_repeats,
        random_state=random_state,
    )

    for split_index, (train_indices, test_indices) in enumerate(
        splitter.split(features, label_values)
    ):
        repeat_index = split_index // n_splits
        model = model_factory()
        model.fit(features.iloc[train_indices], label_values[train_indices])
        predictions_by_repeat[repeat_index, test_indices] = model.predict(
            features.iloc[test_indices]
        )
        prediction_counts[repeat_index, test_indices] += 1

    if not np.all(prediction_counts == 1):
        raise RuntimeError("Every recording must receive exactly one prediction per repeat")

    repeated_truth = np.tile(label_values, n_repeats)
    repeated_predictions = predictions_by_repeat.reshape(-1)
    metrics = _metric_values(repeated_truth, repeated_predictions, class_labels)
    intervals = _bootstrap_confidence_intervals(
        label_values,
        predictions_by_repeat,
        class_labels,
        confidence_level,
        bootstrap_samples,
        random_state + 1,
    )
    matrix = confusion_matrix(
        repeated_truth, repeated_predictions, labels=class_labels
    )

    report = {
        "evaluation": {
            "method": "repeated_stratified_k_fold",
            "folds": n_splits,
            "repeats": n_repeats,
            "recordings": len(labels),
            "confidence_level": confidence_level,
            "confidence_interval_method": "stratified_recording_level_percentile_bootstrap",
            "bootstrap_samples": bootstrap_samples,
            "random_state": random_state,
        },
        "classes": [
            {
                "label": label,
                "name": str(label_names[label]),
                "recordings": int(np.sum(label_values == label)),
            }
            for label in class_labels
        ],
        "metrics": {
            name: {
                "value": value,
                "ci_lower": intervals[name]["lower"],
                "ci_upper": intervals[name]["upper"],
            }
            for name, value in metrics.items()
        },
        "confusion_matrix": {
            "labels": class_labels,
            "values": matrix.astype(int).tolist(),
            "note": "Counts aggregate one out-of-fold prediction per recording per repeat.",
        },
    }

    if priority_label is not None:
        recall_key = f"recall_class_{priority_label}"
        priority_recall = report["metrics"][recall_key]
        report["priority_class"] = {
            "label": priority_label,
            "name": str(label_names[priority_label]),
            "recall": priority_recall,
            "false_good_rate": {
                "value": 1.0 - priority_recall["value"],
                # The interval is reversed when transforming 1 - recall.
                "ci_lower": 1.0 - priority_recall["ci_upper"],
                "ci_upper": 1.0 - priority_recall["ci_lower"],
            },
        }
    return report


def _percentage(metric: Mapping[str, float]) -> str:
    """Format a point estimate and confidence interval for Markdown."""
    return (
        f"{metric['value']:.1%} "
        f"({metric['ci_lower']:.1%}–{metric['ci_upper']:.1%})"
    )


def write_evaluation_report(report: dict, output_prefix: str | Path) -> dict[str, Path]:
    """Write JSON, Markdown, and CSV confusion-matrix evaluation artifacts."""
    prefix = Path(output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    markdown_path = prefix.with_suffix(".md")
    matrix_path = prefix.parent / f"{prefix.name}-confusion-matrix.csv"

    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    class_names = {item["label"]: item["name"] for item in report["classes"]}
    matrix_labels = report["confusion_matrix"]["labels"]
    with matrix_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["actual\\predicted", *[class_names[label] for label in matrix_labels]])
        for label, row in zip(matrix_labels, report["confusion_matrix"]["values"]):
            writer.writerow([class_names[label], *row])

    evaluation = report["evaluation"]
    metrics = report["metrics"]
    lines = [
        "# Model evaluation report",
        "",
        (
            f"Repeated stratified {evaluation['folds']}-fold cross-validation with "
            f"{evaluation['repeats']} repeats on {evaluation['recordings']} recordings."
        ),
        "Confidence intervals use stratified recording-level percentile bootstrap resampling.",
        "",
        "## Aggregate metrics",
        "",
        "| Metric | Value (95% CI) |",
        "| --- | ---: |",
    ]
    display_names = {
        "accuracy": "Accuracy",
        "balanced_accuracy": "Balanced accuracy",
        "macro_precision": "Macro precision",
        "macro_recall": "Macro recall",
        "macro_f1": "Macro F1",
    }
    for key, name in display_names.items():
        lines.append(f"| {name} | {_percentage(metrics[key])} |")

    lines.extend(["", "## Per-class recall", "", "| Class | Recall (95% CI) |", "| --- | ---: |"])
    for label in matrix_labels:
        lines.append(
            f"| {class_names[label]} | {_percentage(metrics[f'recall_class_{label}'])} |"
        )

    if "priority_class" in report:
        priority = report["priority_class"]
        lines.extend(
            [
                "",
                "## Safety-focused class",
                "",
                f"Priority class: **{priority['name']}**.",
                f"Recall: **{_percentage(priority['recall'])}**.",
                (
                    "False-good rate (priority examples predicted as non-priority): "
                    f"**{_percentage(priority['false_good_rate'])}**."
                ),
            ]
        )

    lines.extend(["", "## Confusion matrix", ""])
    lines.append("Rows are actual classes and columns are predicted classes.")
    lines.append("")
    lines.append("| Actual \\ Predicted | " + " | ".join(class_names[label] for label in matrix_labels) + " |")
    lines.append("| --- | " + " | ".join("---:" for _ in matrix_labels) + " |")
    for label, row in zip(matrix_labels, report["confusion_matrix"]["values"]):
        lines.append(f"| {class_names[label]} | " + " | ".join(str(value) for value in row) + " |")
    lines.extend(
        [
            "",
            "> Repeated-fold predictions and bootstrap intervals describe uncertainty inside this dataset;",
            "> they do not replace an independent shooter/session test set.",
            "",
        ]
    )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path, "confusion_matrix": matrix_path}
