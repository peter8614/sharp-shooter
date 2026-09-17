"""Warm-runtime caches for the small sklearn inference bundles."""

from __future__ import annotations

from functools import lru_cache

from landmark_classification import load_landmark_model
from trajectory_classification import load_trajectory_model

from .config import LANDMARK_MODEL_PATH, TRAJECTORY_MODEL_PATH


@lru_cache(maxsize=1)
def get_landmark_model() -> dict:
    """Load the form classifier once per Python runtime."""
    return load_landmark_model(LANDMARK_MODEL_PATH)


@lru_cache(maxsize=1)
def get_trajectory_model() -> dict:
    """Load the trajectory classifier once per Python runtime."""
    return load_trajectory_model(TRAJECTORY_MODEL_PATH)


def clear_model_caches() -> None:
    """Clear cached bundles for tests or an explicit local model refresh."""
    get_landmark_model.cache_clear()
    get_trajectory_model.cache_clear()
