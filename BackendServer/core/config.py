"""Filesystem configuration shared by local and serverless inference."""

from __future__ import annotations

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
LANDMARK_MODEL_PATH = (
    BACKEND_DIR / "data" / "landmark_data" / "basketball_shot_model.pkl"
)
TRAJECTORY_MODEL_PATH = (
    BACKEND_DIR / "data" / "trajectory_data" / "trajectory_model.pkl"
)
NBA_DATA_DIR = BACKEND_DIR / "NBA Data"
NBA_VIDEO_DIR = BACKEND_DIR / "NBA Players"
