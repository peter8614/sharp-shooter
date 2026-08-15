"""Video-level shooting-form feature extraction and classification.

Each video is represented by one feature vector. This prevents frames from the
same recording being split across training and validation sets, which would
otherwise make the reported accuracy unrealistically high.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier

from model_evaluation import evaluate_repeated_stratified_cv, write_evaluation_report


BACKEND_DIR = Path(__file__).resolve().parent
LANDMARK_NAMES = (
    "Left Shoulder",
    "Right Shoulder",
    "Left Elbow",
    "Right Elbow",
    "Left Wrist",
    "Right Wrist",
)
MODEL_VERSION = 2
REPORT_PREFIX = BACKEND_DIR / "reports/landmark-evaluation"


def _parse_point(value: object) -> np.ndarray:
    """Parse a MediaPipe point stored as a comma-separated x,y,z value."""
    parts = np.asarray(str(value).split(","), dtype=float)
    if parts.shape != (3,) or not np.isfinite(parts).all():
        raise ValueError(f"Invalid landmark point: {value!r}")
    return parts


def _joint_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Return the angle ABC in degrees, or NaN for a degenerate joint."""
    first = a - b
    second = c - b
    denominator = np.linalg.norm(first) * np.linalg.norm(second)
    if denominator <= 1e-9:
        return float("nan")
    cosine = np.clip(np.dot(first, second) / denominator, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


def extract_landmark_features(file_path: str | Path) -> pd.DataFrame:
    """Convert all valid frames in one recording into one normalized row."""
    data = pd.read_csv(file_path)
    missing = [column for column in LANDMARK_NAMES if column not in data.columns]
    if missing:
        raise ValueError(f"Landmark file is missing columns: {', '.join(missing)}")
    if data.empty:
        raise ValueError("Landmark file does not contain any frames")

    normalized_frames: list[np.ndarray] = []
    elbow_angles: list[list[float]] = []
    for _, row in data.iterrows():
        points = np.vstack([_parse_point(row[name]) for name in LANDMARK_NAMES])
        shoulder_center = (points[0] + points[1]) / 2.0
        shoulder_width = np.linalg.norm(points[0, :2] - points[1, :2])
        if shoulder_width <= 1e-6:
            continue

        # Centering and scaling reduce camera-position and subject-size effects.
        normalized_frames.append(((points - shoulder_center) / shoulder_width).reshape(-1))
        elbow_angles.append(
            [
                _joint_angle(points[0], points[2], points[4]),
                _joint_angle(points[1], points[3], points[5]),
            ]
        )

    if not normalized_frames:
        raise ValueError("No frame has a usable shoulder scale")

    frame_matrix = np.vstack(normalized_frames)
    angle_matrix = np.asarray(elbow_angles, dtype=float)
    feature_values: dict[str, float] = {}
    coordinate_names = [f"{name}_{axis}" for name in LANDMARK_NAMES for axis in "xyz"]
    for index, name in enumerate(coordinate_names):
        values = frame_matrix[:, index]
        feature_values.update(
            {
                f"{name}_mean": float(np.mean(values)),
                f"{name}_std": float(np.std(values)),
                f"{name}_min": float(np.min(values)),
                f"{name}_max": float(np.max(values)),
                f"{name}_delta": float(values[-1] - values[0]),
            }
        )

    for index, side in enumerate(("left", "right")):
        valid_angles = angle_matrix[:, index]
        valid_angles = valid_angles[np.isfinite(valid_angles)]
        if valid_angles.size == 0:
            raise ValueError(f"No valid {side} elbow angles were found")
        feature_values[f"{side}_elbow_angle_mean"] = float(np.mean(valid_angles))
        feature_values[f"{side}_elbow_angle_std"] = float(np.std(valid_angles))
        feature_values[f"{side}_elbow_angle_range"] = float(np.ptp(valid_angles))

    feature_values["frame_count"] = float(len(frame_matrix))
    return pd.DataFrame([feature_values])


def load_single_landmark_file(file_path: str | Path, label: int | None = None) -> pd.DataFrame:
    """Compatibility wrapper that optionally appends a recording label."""
    features = extract_landmark_features(file_path)
    if label is not None:
        features["Label"] = int(label)
    return features


def _resolve_data_path(value: str | Path, list_path: Path) -> Path:
    """Resolve list entries against this or the index file's backend tree."""
    path = Path(value)
    if path.is_absolute():
        return path
    # Searching index ancestors permits privacy-safe code copies to evaluate a
    # local dataset without copying raw recordings into the Git repository.
    for base in (BACKEND_DIR, *list_path.parents):
        candidate = base / path
        if candidate.exists():
            return candidate
    return list_path.parent / path


def load_training_data(list_path: str | Path) -> tuple[pd.DataFrame, pd.Series]:
    """Load one feature row and one label for every listed video."""
    resolved_list = Path(list_path).resolve()
    rows = pd.read_csv(resolved_list)
    required = {"file_path", "classification"}
    if not required.issubset(rows.columns):
        raise ValueError("Training list must contain file_path and classification columns")

    features: list[pd.DataFrame] = []
    labels: list[int] = []
    for _, row in rows.iterrows():
        features.append(extract_landmark_features(_resolve_data_path(row["file_path"], resolved_list)))
        labels.append(int(row["classification"]))
    return pd.concat(features, ignore_index=True), pd.Series(labels, name="Label")


def create_model() -> ExtraTreesClassifier:
    """Create a reproducible classifier for the small, imbalanced dataset."""
    return ExtraTreesClassifier(
        n_estimators=500,
        class_weight="balanced",
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )


def save_landmark_model(model, model_path: str | Path, feature_names: list[str]) -> None:
    """Save the estimator together with the exact feature contract."""
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"version": MODEL_VERSION, "model": model, "features": feature_names},
        model_path,
    )


def load_landmark_model(model_path: str | Path) -> dict:
    """Load only the current bundle format so stale models cannot be used."""
    bundle = joblib.load(model_path)
    if not isinstance(bundle, dict) or bundle.get("version") != MODEL_VERSION:
        raise ValueError("Landmark model is obsolete; retrain it with this version")
    return bundle


def landmark_predict(bundle: dict, features: pd.DataFrame) -> np.ndarray:
    """Predict after enforcing the feature order recorded during training."""
    missing = set(bundle["features"]) - set(features.columns)
    if missing:
        raise ValueError(f"Prediction features are missing: {sorted(missing)}")
    return bundle["model"].predict(features[bundle["features"]])


def train_and_save(list_path: str | Path, model_path: str | Path) -> None:
    """Evaluate at video level, then fit the deployable model on all data."""
    features, labels = load_training_data(list_path)
    report = evaluate_repeated_stratified_cv(
        create_model,
        features,
        labels,
        {0: "bad_form", 1: "good_form"},
        # Bad-form recall is the safety-focused metric: missing a bad form
        # produces an overly reassuring result for the user.
        priority_label=0,
        n_splits=5,
        n_repeats=10,
        confidence_level=0.95,
        random_state=42,
    )
    report_paths = write_evaluation_report(report, REPORT_PREFIX)
    print(report_paths["markdown"].read_text(encoding="utf-8"))

    # Refit on every labeled recording only after all out-of-fold predictions
    # have been collected, so evaluation never sees its own training rows.
    final_model = create_model().fit(features, labels)
    save_landmark_model(final_model, model_path, list(features.columns))


if __name__ == "__main__":
    train_and_save(
        BACKEND_DIR / "data/landmark_data/landmarks_list.csv",
        BACKEND_DIR / "data/landmark_data/basketball_shot_model.pkl",
    )
