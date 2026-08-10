"""Train a video-level classifier for good and bad basketball shooting form."""

import argparse
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split


LANDMARK_COLUMNS = [
    "Left Shoulder",
    "Right Shoulder",
    "Left Elbow",
    "Right Elbow",
    "Left Wrist",
    "Right Wrist",
]


def parse_landmark_data(df: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """Expand one CSV x,y,z landmark field into three numeric columns."""
    if column_name not in df:
        raise ValueError(f"Missing landmark column: {column_name}")
    parsed = df[column_name].astype(str).str.split(",", expand=True)
    if parsed.shape[1] != 3:
        raise ValueError(f"Invalid x,y,z data in column: {column_name}")
    parsed = parsed.apply(pd.to_numeric, errors="raise")
    parsed.columns = [f"{column_name}_{axis}" for axis in "xyz"]
    return parsed


def _summarize_landmarks(parsed: pd.DataFrame) -> pd.DataFrame:
    """Convert a variable-length pose sequence into one fixed-size video sample."""
    if parsed.empty:
        raise ValueError("Landmark file contains no detected shooting frames")
    features = {}
    # Distribution statistics retain posture range without requiring equal clip length.
    for column in parsed.columns:
        series = parsed[column]
        features[f"{column}_mean"] = series.mean()
        features[f"{column}_std"] = series.std(ddof=0)
        features[f"{column}_min"] = series.min()
        features[f"{column}_max"] = series.max()
    features["frame_count"] = len(parsed)
    return pd.DataFrame([features])


def load_single_landmark_file(file_path: str | Path, label: int) -> pd.DataFrame:
    """Load and summarize one labeled landmark CSV as one training row."""
    file_path = Path(file_path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Landmark file not found: {file_path}")
    raw = pd.read_csv(file_path)
    parsed = pd.concat(
        [parse_landmark_data(raw, column) for column in LANDMARK_COLUMNS], axis=1
    )
    sample = _summarize_landmarks(parsed)
    sample["Label"] = int(label)
    return sample


def load_multiple_landmark_files(file_label_pairs) -> pd.DataFrame:
    """Combine multiple labeled videos into a classifier-ready table."""
    samples = [
        load_single_landmark_file(file_path, label)
        for file_path, label in file_label_pairs
    ]
    if not samples:
        raise ValueError("No landmark training files were provided")
    return pd.concat(samples, ignore_index=True)


def load_from_list(list_path: str | Path) -> pd.DataFrame:
    """Load landmark samples referenced by a dataset index CSV."""
    list_path = Path(list_path)
    entries = pd.read_csv(list_path)
    required = {"file_path", "classification"}
    if not required.issubset(entries.columns):
        raise ValueError(f"Dataset list must contain columns: {sorted(required)}")
    base = list_path.parent
    pairs = []
    for row in entries.itertuples(index=False):
        path = Path(row.file_path)
        # Relative dataset paths are interpreted relative to the index file.
        if not path.is_absolute():
            path = base / path
        pairs.append((path, row.classification))
    return load_multiple_landmark_files(pairs)


def create_model() -> RandomForestClassifier:
    """Create a reproducible classifier with compensation for class imbalance."""
    return RandomForestClassifier(
        n_estimators=300, random_state=42, class_weight="balanced"
    )


def train_model(model, x_train, y_train):
    """Fit and return a form classifier."""
    model.fit(x_train, y_train)
    return model


def landmark_predict(model, x_input):
    """Predict form labels for summarized landmark samples."""
    return model.predict(x_input)


def main(dataset_list: str | Path, model_output: str | Path | None = None):
    """Train, evaluate, and optionally persist the form classifier."""
    data = load_from_list(dataset_list)
    if data["Label"].nunique() < 2:
        raise ValueError("Training requires at least two form classes")
    if len(data) < 6 or data["Label"].value_counts().min() < 2:
        raise ValueError("Training requires at least 6 videos and 2 videos per class")

    features = data.drop(columns=["Label"])
    labels = data["Label"]
    # Stratification keeps both labels represented in the small evaluation split.
    x_train, x_test, y_train, y_test = train_test_split(
        features,
        labels,
        test_size=0.25,
        random_state=42,
        stratify=labels,
    )
    model = train_model(create_model(), x_train, y_train)
    predictions = landmark_predict(model, x_test)
    print("Model Accuracy:", accuracy_score(y_test, predictions))
    print(classification_report(y_test, predictions, zero_division=0))

    if model_output:
        model_output = Path(model_output)
        model_output.parent.mkdir(parents=True, exist_ok=True)
        # Store feature order with the model so inference cannot silently reorder data.
        joblib.dump({"model": model, "features": list(features.columns)}, model_output)
        print(f"Model written to {model_output}")
    return model


if __name__ == "__main__":
    backend_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Train the shooting-form classifier.")
    parser.add_argument(
        "dataset_list",
        type=Path,
        nargs="?",
        default=backend_dir / "data" / "landmark_data" / "landmarks_list.csv",
    )
    parser.add_argument(
        "--model-output",
        type=Path,
        default=backend_dir / "models" / "landmark_classifier.joblib",
    )
    args = parser.parse_args()
    main(args.dataset_list, args.model_output)
