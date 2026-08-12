"""Video-level basketball trajectory feature extraction and classification."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split


BACKEND_DIR = Path(__file__).resolve().parent
MODEL_VERSION = 2
SAMPLE_COUNT = 25


def _read_trajectory(file_path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Read legacy x/y rows and current frame/x/y rows safely."""
    rows: list[list[float]] = []
    for line in Path(file_path).read_text(encoding="utf-8").splitlines():
        try:
            values = [float(value) for value in line.split()]
        except ValueError:
            # Header rows are intentionally skipped.
            continue
        if len(values) in (2, 3) and np.isfinite(values).all():
            rows.append(values)
    if len(rows) < 3:
        raise ValueError("Trajectory must contain at least three valid observations")

    matrix = np.asarray(rows, dtype=float)
    if matrix.shape[1] == 2:
        frames = np.arange(len(matrix), dtype=float)
        x_values, y_values = matrix[:, 0], matrix[:, 1]
    else:
        frames, x_values, y_values = matrix[:, 0], matrix[:, 1], matrix[:, 2]

    order = np.argsort(frames)
    frames, x_values, y_values = frames[order], x_values[order], y_values[order]
    unique_frames, unique_indices = np.unique(frames, return_index=True)
    return unique_frames, x_values[unique_indices], y_values[unique_indices]


def extract_trajectory_features(file_path: str | Path) -> pd.DataFrame:
    """Normalize and time-interpolate one complete shot into one feature row."""
    frames, x_values, y_values = _read_trajectory(file_path)
    duration = frames[-1] - frames[0]
    if duration <= 0:
        raise ValueError("Trajectory frame indices must span a positive duration")

    # One shared scale preserves the curve's aspect ratio while removing pixels.
    centered_x = x_values - x_values[0]
    centered_y = y_values - y_values[0]
    scale = max(float(np.ptp(centered_x)), float(np.ptp(centered_y)), 1.0)
    normalized_time = (frames - frames[0]) / duration
    sample_time = np.linspace(0.0, 1.0, SAMPLE_COUNT)
    sampled_x = np.interp(sample_time, normalized_time, centered_x / scale)
    sampled_y = np.interp(sample_time, normalized_time, centered_y / scale)

    features: dict[str, float] = {}
    for index, (x_value, y_value) in enumerate(zip(sampled_x, sampled_y)):
        features[f"x_{index:02d}"] = float(x_value)
        features[f"y_{index:02d}"] = float(y_value)
    features["duration_frames"] = float(duration)
    features["observation_count"] = float(len(frames))
    features["horizontal_direction"] = float(np.sign(centered_x[-1]))
    return pd.DataFrame([features])


def load_trajectory(file_path: str | Path, label: int | None = None) -> pd.DataFrame:
    """Compatibility wrapper that optionally appends a recording label."""
    features = extract_trajectory_features(file_path)
    if label is not None:
        features["Label"] = int(label)
    return features


def _resolve_data_path(value: str | Path, list_path: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    backend_candidate = BACKEND_DIR / path
    return backend_candidate if backend_candidate.exists() else list_path.parent / path


def load_training_data(list_path: str | Path) -> tuple[pd.DataFrame, pd.Series]:
    """Load one feature row and one label for every listed recording."""
    resolved_list = Path(list_path).resolve()
    rows = pd.read_csv(resolved_list)
    if not {"file_path", "classification"}.issubset(rows.columns):
        raise ValueError("Training list must contain file_path and classification columns")
    features = [
        extract_trajectory_features(_resolve_data_path(row["file_path"], resolved_list))
        for _, row in rows.iterrows()
    ]
    labels = pd.Series(rows["classification"].astype(int).to_list(), name="Label")
    return pd.concat(features, ignore_index=True), labels


def create_model() -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )


def save_trajectory_model(model, model_path: str | Path, feature_names: list[str]) -> None:
    """Save the model and its feature schema as one versioned bundle."""
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {"version": MODEL_VERSION, "model": model, "features": feature_names},
        model_path,
    )


def load_trajectory_model(model_path: str | Path) -> dict:
    bundle = joblib.load(model_path)
    if not isinstance(bundle, dict) or bundle.get("version") != MODEL_VERSION:
        raise ValueError("Trajectory model is obsolete; retrain it with this version")
    return bundle


def trajectory_predict(bundle: dict, features: pd.DataFrame) -> np.ndarray:
    missing = set(bundle["features"]) - set(features.columns)
    if missing:
        raise ValueError(f"Prediction features are missing: {sorted(missing)}")
    return bundle["model"].predict(features[bundle["features"]])


def train_and_save(list_path: str | Path, model_path: str | Path) -> None:
    """Train and evaluate without allowing observations from one video to leak."""
    features, labels = load_training_data(list_path)
    if labels.nunique() < 2 or labels.value_counts().min() < 2:
        raise ValueError("At least two recordings per class are required")
    train_x, test_x, train_y, test_y = train_test_split(
        features,
        labels,
        test_size=0.2,
        random_state=42,
        stratify=labels,
    )
    model = create_model().fit(train_x, train_y)
    print(classification_report(test_y, model.predict(test_x), zero_division=0))

    # Once evaluation is complete, train the deployable model on all available
    # recordings instead of throwing away the holdout subset.
    final_model = create_model().fit(features, labels)
    save_trajectory_model(final_model, model_path, list(features.columns))


if __name__ == "__main__":
    train_and_save(
        BACKEND_DIR / "data/trajectory_data/trajectories_list.csv",
        BACKEND_DIR / "data/trajectory_data/trajectory_model.pkl",
    )
