"""Deterministic, evidence-backed coaching labels for model predictions.

The language model should explain findings rather than invent them. This module
therefore converts classifier outputs and good-form training statistics into a
small, privacy-safe contract containing issue codes, confidence, evidence, and
bounded practice suggestions.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


GOOD_CLASS = 1
MIN_REFERENCE_SAMPLES = 5
MAX_SPECIFIC_LABELS = 2

# Only features with a camera-independent-enough interpretation are exposed as
# specific coaching labels. Coordinate features whose meaning changes with the
# camera side are deliberately excluded.
FORM_FEATURE_SPECS: dict[str, dict[str, str]] = {
    "left_elbow_angle_mean": {
        "area": "left_elbow",
        "metric": "left elbow angle mean",
        "below_code": "left_elbow_angle_below_good_reference",
        "above_code": "left_elbow_angle_above_good_reference",
        "below_goal": "Explore a slightly more open left elbow position without forcing a fixed angle.",
        "above_goal": "Explore a slightly more flexed left elbow position without forcing a fixed angle.",
        "drill": "Record several comfortable close-range shots from the same view and compare the left elbow mean with the reference band.",
    },
    "right_elbow_angle_mean": {
        "area": "right_elbow",
        "metric": "right elbow angle mean",
        "below_code": "right_elbow_angle_below_good_reference",
        "above_code": "right_elbow_angle_above_good_reference",
        "below_goal": "Explore a slightly more open right elbow position without forcing a fixed angle.",
        "above_goal": "Explore a slightly more flexed right elbow position without forcing a fixed angle.",
        "drill": "Record several comfortable close-range shots from the same view and compare the right elbow mean with the reference band.",
    },
    "Left Wrist_y_mean": {
        "area": "left_wrist",
        "metric": "left wrist vertical position",
        "below_code": "left_wrist_higher_than_good_reference",
        "above_code": "left_wrist_lower_than_good_reference",
        "below_goal": "Experiment with a slightly lower left-wrist position while keeping the motion comfortable.",
        "above_goal": "Experiment with a slightly higher left-wrist position while keeping the motion comfortable.",
        "drill": "Use a fixed camera and slow close-range repetitions to compare the left-wrist position with the reference band.",
    },
    "Right Wrist_y_mean": {
        "area": "right_wrist",
        "metric": "right wrist vertical position",
        "below_code": "right_wrist_higher_than_good_reference",
        "above_code": "right_wrist_lower_than_good_reference",
        "below_goal": "Experiment with a slightly lower right-wrist position while keeping the motion comfortable.",
        "above_goal": "Experiment with a slightly higher right-wrist position while keeping the motion comfortable.",
        "drill": "Use a fixed camera and slow close-range repetitions to compare the right-wrist position with the reference band.",
    },
}


def build_good_form_reference_profile(
    features: pd.DataFrame,
    labels: pd.Series,
) -> dict[str, dict[str, float | int]]:
    """Summarize interpretable features from good-form training recordings.

    Quantile bands describe this project's labeled examples; they are not
    universal biomechanical ideals. At least five good recordings are required
    so a single example cannot become an apparent coaching standard.
    """
    label_values = np.asarray(labels)
    if label_values.ndim != 1 or len(label_values) != len(features):
        raise ValueError("Features and labels must contain the same number of rows")
    # Use positional indexing because a caller may provide features and labels
    # with different index labels even though their row order is aligned.
    good_rows = features.iloc[np.flatnonzero(label_values == GOOD_CLASS)]
    if len(good_rows) < MIN_REFERENCE_SAMPLES:
        return {}

    profile: dict[str, dict[str, float | int]] = {}
    for feature_name in FORM_FEATURE_SPECS:
        if feature_name not in good_rows:
            continue
        values = pd.to_numeric(good_rows[feature_name], errors="coerce")
        values = values[np.isfinite(values)]
        if len(values) < MIN_REFERENCE_SAMPLES:
            continue
        profile[feature_name] = {
            "median": round(float(values.median()), 4),
            "low": round(float(values.quantile(0.10)), 4),
            "high": round(float(values.quantile(0.90)), 4),
            "sample_count": int(len(values)),
        }
    return profile


def prediction_confidence(model: Any, ordered_features: pd.DataFrame, label: int) -> float | None:
    """Return the predicted-class probability when the estimator exposes it."""
    if not hasattr(model, "predict_proba") or not hasattr(model, "classes_"):
        return None
    probabilities = np.asarray(model.predict_proba(ordered_features), dtype=float)
    classes = list(np.asarray(model.classes_).astype(int))
    if probabilities.shape[0] != 1 or label not in classes:
        return None
    value = float(probabilities[0, classes.index(label)])
    if not np.isfinite(value):
        return None
    return round(min(max(value, 0.0), 1.0), 3)


def _severity(confidence: float | None) -> str:
    """Map calibrated-looking probabilities to broad, non-clinical severity."""
    if confidence is None or confidence < 0.70:
        return "low"
    if confidence < 0.85:
        return "medium"
    return "high"


def _specific_form_labels(
    features: pd.DataFrame,
    reference_profile: dict[str, Any],
    classifier_confidence: float | None,
) -> list[dict[str, Any]]:
    """Return the largest interpretable deviations from the good-form profile."""
    if features.empty:
        return []
    candidates: list[tuple[float, dict[str, Any]]] = []
    for feature_name, specification in FORM_FEATURE_SPECS.items():
        reference = reference_profile.get(feature_name)
        if not isinstance(reference, dict) or feature_name not in features:
            continue
        try:
            observed = float(features.iloc[0][feature_name])
            low = float(reference["low"])
            high = float(reference["high"])
            sample_count = int(reference["sample_count"])
        except (KeyError, TypeError, ValueError):
            continue
        if not all(np.isfinite([observed, low, high])) or low > high:
            continue
        if low <= observed <= high:
            continue

        direction = "below" if observed < low else "above"
        excess = low - observed if direction == "below" else observed - high
        band_width = max(
            high - low,
            abs(float(reference.get("median", 0.0))) * 0.05,
            1e-6,
        )
        normalized_distance = excess / band_width
        # Deviation confidence expresses distance from this dataset's reference
        # band and is capped by the classifier's predicted-class confidence.
        deviation_confidence = min(0.99, 0.55 + min(normalized_distance, 1.76) * 0.25)
        confidence = (
            min(deviation_confidence, classifier_confidence)
            if classifier_confidence is not None
            else deviation_confidence
        )
        label = {
            "code": specification[f"{direction}_code"],
            "status": "needs_attention",
            "area": specification["area"],
            "confidence": round(float(confidence), 3),
            "severity": _severity(float(confidence)),
            "evidence": {
                "metric": specification["metric"],
                "observed": round(observed, 4),
                "reference_low": round(low, 4),
                "reference_high": round(high, 4),
                "reference_source": "good-form training recordings",
                "reference_sample_count": sample_count,
            },
            "coaching_goal": specification[f"{direction}_goal"],
            "practice": specification["drill"],
        }
        candidates.append((normalized_distance, label))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [label for _, label in candidates[:MAX_SPECIFIC_LABELS]]


def generate_prediction_labels(
    domain: str,
    predicted_label: str,
    confidence: float | None,
    features: pd.DataFrame,
    reference_profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate bounded labels for one form or trajectory classification."""
    if predicted_label == "unavailable":
        return [{
            "code": f"{domain}_model_unavailable",
            "status": "insufficient_evidence",
            "area": domain,
            "confidence": None,
            "severity": "low",
            "evidence": {"classification": "unavailable"},
            "coaching_goal": "Collect a valid recording and run the trained classifier before drawing conclusions.",
            "practice": "Use a steady camera and keep the complete shot visible.",
        }]

    if predicted_label == "good":
        return [{
            "code": f"{domain}_model_no_issue_detected",
            "status": "strength",
            "area": domain,
            "confidence": confidence,
            "severity": "low",
            "evidence": {"classification": "good"},
            "coaching_goal": "Preserve the currently observed overall pattern.",
            "practice": "Repeat the same recording setup to check whether the result remains reproducible.",
        }]

    generic_goal = (
        "Review this area using the specific evidence labels below."
        if domain == "form"
        else (
            "Treat this as an overall trajectory flag; the current model does "
            "not identify a specific cause."
        )
    )
    labels = [{
        "code": f"{domain}_model_flagged",
        "status": "needs_attention",
        "area": domain,
        "confidence": confidence,
        "severity": _severity(confidence),
        "evidence": {"classification": "bad"},
        "coaching_goal": generic_goal,
        "practice": "Use controlled close-range repetitions and record from the same camera position.",
    }]
    if domain == "form":
        labels.extend(
            _specific_form_labels(features, reference_profile or {}, confidence)
        )
        if len(labels) == 1:
            # An old model bundle may classify correctly but lack the profile
            # needed to explain which interpretable feature drove the concern.
            labels[0]["coaching_goal"] = (
                "Retrain the current model to add good-form reference bands before giving a specific correction."
            )
    return labels


def sanitize_coaching_context(context: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only the bounded server-generated fields sent to the LLM provider."""
    if not isinstance(context, dict):
        return {}
    result: dict[str, Any] = {}
    for name in ("form_classification", "trajectory_classification"):
        value = context.get(name)
        if value in {"good", "bad", "unavailable"}:
            result[name] = value
    for name in ("form_confidence", "trajectory_confidence"):
        value = context.get(name)
        if (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and np.isfinite(value)
        ):
            result[name] = round(min(max(float(value), 0.0), 1.0), 3)

    safe_labels: list[dict[str, Any]] = []
    for label in context.get("coaching_labels", [])[:6]:
        if not isinstance(label, dict):
            continue
        safe_label: dict[str, Any] = {}
        for name in ("code", "status", "area", "severity", "coaching_goal", "practice"):
            value = label.get(name)
            if isinstance(value, str) and 0 < len(value) <= 300:
                safe_label[name] = value
        confidence = label.get("confidence")
        if (
            not isinstance(confidence, bool)
            and isinstance(confidence, (int, float))
            and np.isfinite(confidence)
        ):
            safe_label["confidence"] = round(min(max(float(confidence), 0.0), 1.0), 3)
        evidence = label.get("evidence")
        if isinstance(evidence, dict):
            safe_label["evidence"] = {
                key: value
                for key, value in evidence.items()
                if isinstance(key, str)
                and len(key) <= 60
                and (
                    (isinstance(value, str) and len(value) <= 120)
                    or (isinstance(value, (int, float)) and np.isfinite(value))
                )
            }
        if safe_label.get("code") and safe_label.get("status"):
            safe_labels.append(safe_label)
    if safe_labels:
        result["coaching_labels"] = safe_labels
    return result
