"""Train a video-level classifier for good and bad basketball shot arcs."""

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split


RESAMPLED_POINTS = 25


def _resample_trajectory(points: np.ndarray, count: int = RESAMPLED_POINTS) -> np.ndarray:
    """Normalize and interpolate a trajectory to a fixed number of points."""
    if len(points) < 2:
        raise ValueError("A trajectory requires at least two detected ball positions")

    # Translation and scale normalization makes videos at different resolutions comparable.
    normalized = points.astype(float) - points[0]
    scale = np.ptp(normalized, axis=0)
    scale[scale == 0] = 1.0
    normalized /= scale

    # Interpolation makes clips with different durations comparable to one model.
    source = np.linspace(0.0, 1.0, len(normalized))
    target = np.linspace(0.0, 1.0, count)
    x = np.interp(target, source, normalized[:, 0])
    y = np.interp(target, source, normalized[:, 1])
    return np.column_stack((x, y))


def load_trajectory(file_path: str | Path, label: int) -> pd.DataFrame:
    """Load one trajectory without modifying it and return one training row."""
    file_path = Path(file_path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Trajectory file not found: {file_path}")
    try:
        points = np.loadtxt(file_path, dtype=float, ndmin=2)
    except ValueError as exc:
        raise ValueError(f"Invalid trajectory file: {file_path}") from exc
    if points.shape[1] != 2:
        raise ValueError(f"Trajectory must contain exactly two columns: {file_path}")

    sampled = _resample_trajectory(points)
    features = {}
    # Flatten the ordered points into stable x_00, y_00, ... feature columns.
    for index, (x, y) in enumerate(sampled):
        features[f"x_{index:02d}"] = x
        features[f"y_{index:02d}"] = y
    features["original_point_count"] = len(points)
    features["Label"] = int(label)
    return pd.DataFrame([features])


def load_from_list(trajectories_list_csv: str | Path) -> pd.DataFrame:
    """Load trajectory samples referenced by a dataset index CSV."""
    list_path = Path(trajectories_list_csv)
    entries = pd.read_csv(list_path)
    required = {"file_path", "classification"}
    if not required.issubset(entries.columns):
        raise ValueError(f"Dataset list must contain columns: {sorted(required)}")

    samples = []
    for row in entries.itertuples(index=False):
        path = Path(row.file_path)
        if not path.is_absolute():
            path = list_path.parent / path
        samples.append(load_trajectory(path, row.classification))
    if not samples:
        raise ValueError("No trajectory training files were provided")
    return pd.concat(samples, ignore_index=True)


def create_model() -> RandomForestClassifier:
    """Create a reproducible arc classifier with balanced class weights."""
    return RandomForestClassifier(
        n_estimators=300, random_state=42, class_weight="balanced"
    )


def train_model(model, x_train, y_train):
    """Fit and return a trajectory classifier."""
    model.fit(x_train, y_train)
    return model


def trajectory_predict(model, x_input):
    """Predict arc labels for normalized trajectory samples."""
    return model.predict(x_input)


def main(dataset_list: str | Path, model_output: str | Path | None = None):
    """Train, evaluate, and optionally persist the trajectory classifier."""
    data = load_from_list(dataset_list)
    if data["Label"].nunique() < 2:
        raise ValueError("Training requires at least two trajectory classes")
    if len(data) < 6 or data["Label"].value_counts().min() < 2:
        raise ValueError("Training requires at least 6 videos and 2 videos per class")

    features = data.drop(columns=["Label"])
    labels = data["Label"]
    # Stratification keeps both labels represented in the evaluation split.
    x_train, x_test, y_train, y_test = train_test_split(
        features,
        labels,
        test_size=0.25,
        random_state=42,
        stratify=labels,
    )
    model = train_model(create_model(), x_train, y_train)
    predictions = trajectory_predict(model, x_test)
    print("Model Accuracy:", accuracy_score(y_test, predictions))
    print(classification_report(y_test, predictions, zero_division=0))

    if model_output:
        model_output = Path(model_output)
        model_output.parent.mkdir(parents=True, exist_ok=True)
        # Persist the feature schema with the estimator for safe inference later.
        joblib.dump({"model": model, "features": list(features.columns)}, model_output)
        print(f"Model written to {model_output}")
    return model


if __name__ == "__main__":
    backend_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Train the ball-trajectory classifier.")
    parser.add_argument(
        "dataset_list",
        type=Path,
        nargs="?",
        default=backend_dir / "data" / "trajectory_data" / "trajectories_list.csv",
    )
    parser.add_argument(
        "--model-output",
        type=Path,
        default=backend_dir / "models" / "trajectory_classifier.joblib",
    )
    args = parser.parse_args()
    main(args.dataset_list, args.model_output)
