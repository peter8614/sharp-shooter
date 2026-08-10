"""Compare one user's motion variability with the local NBA reference set."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

LANDMARK_NAMES = ("Left Shoulder", "Right Shoulder", "Left Elbow", "Right Elbow", "Left Wrist", "Right Wrist")


def _parse_column(column: pd.Series) -> np.ndarray:
    """Parse a landmark column and reject malformed or non-finite values."""
    points = np.vstack([np.asarray(str(value).split(","), dtype=float) for value in column])
    if points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError("Landmark data must contain finite x,y,z values")
    return points


def find_landmark_variances(csv_file: str | Path) -> dict[str, list[float]]:
    """Calculate a three-axis population variance for every tracked joint."""
    landmarks = pd.read_csv(csv_file)
    if landmarks.empty:
        raise ValueError("Landmark file does not contain any observations")
    missing = set(LANDMARK_NAMES) - set(landmarks.columns)
    if missing:
        raise ValueError(f"Landmark file is missing columns: {sorted(missing)}")
    return {name: np.var(_parse_column(landmarks[name]), axis=0).astype(float).tolist() for name in LANDMARK_NAMES}


def _variance_vector(variances: dict[str, list[float]]) -> np.ndarray:
    """Flatten and validate a stored reference-variance document."""
    vector = np.asarray([value for name in LANDMARK_NAMES for value in variances[name]], dtype=float)
    if vector.shape != (18,) or not np.isfinite(vector).all():
        raise ValueError("Reference variance data has an invalid shape")
    return vector


def compare_user_to_player(user_landmark_csv: str | Path, player_landmark_dir: str | Path, player_video_dir: str | Path | None = None) -> tuple[str | None, float | None, str | None]:
    """Return the closest reference using normalized absolute distance.

    The score is a bounded similarity, not a population-level probability.
    Missing or malformed reference files are skipped safely.
    """
    reference_dir = Path(player_landmark_dir)
    video_dir = Path(player_video_dir) if player_video_dir else reference_dir.parent / "NBA Players"
    user_vector = _variance_vector(find_landmark_variances(user_landmark_csv))
    candidates: list[tuple[float, Path]] = []
    for variance_path in sorted(reference_dir.glob("*_variance.txt")):
        try:
            reference_vector = _variance_vector(json.loads(variance_path.read_text(encoding="utf-8")))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        # A shared magnitude scale avoids signed-error cancellation and limits
        # domination by a single high-variance coordinate.
        scale = np.maximum(np.abs(user_vector) + np.abs(reference_vector), 1e-9)
        candidates.append((float(np.mean(np.abs(user_vector - reference_vector) / scale)), variance_path))

    if not candidates:
        return None, None, None
    distance, closest_path = min(candidates, key=lambda item: item[0])
    recording_stem = closest_path.stem.removesuffix("_variance")
    video_path = video_dir / f"{recording_stem}.mp4"
    player_name = recording_stem.rsplit("_", 1)[0]
    similarity = round(max(0.0, min(100.0, (1.0 - distance) * 100.0)), 2)
    return player_name, similarity, str(video_path) if video_path.is_file() else None


if __name__ == "__main__":
    raise SystemExit("Import compare_user_to_player from the server or a maintenance script.")
