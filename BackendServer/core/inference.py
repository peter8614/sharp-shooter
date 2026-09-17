"""Framework-independent basketball video inference."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Callable

import pandas as pd

from coaching_labels import generate_prediction_labels, prediction_confidence
from landmark_classification import landmark_predict, load_single_landmark_file
from main import break_down_video
from NBA_compare import compare_user_to_player
from trajectory_classification import load_trajectory, trajectory_predict

from .config import (
    LANDMARK_MODEL_PATH,
    NBA_DATA_DIR,
    NBA_VIDEO_DIR,
    TRAJECTORY_MODEL_PATH,
)
from .models import get_landmark_model, get_trajectory_model


logger = logging.getLogger(__name__)


def _unavailable_result(domain: str) -> dict:
    label = "unavailable"
    return {
        "label": label,
        "confidence": None,
        "coaching_labels": generate_prediction_labels(
            domain, label, None, pd.DataFrame()
        ),
    }


def _classify(
    *,
    model_path: Path,
    model_provider: Callable[[], dict],
    feature_loader: Callable[[Path], pd.DataFrame],
    predictor: Callable[[dict, pd.DataFrame], object],
    data_path: Path,
    domain: str,
) -> dict:
    """Classify one generated artifact using a warm-cached model bundle."""
    if not model_path.is_file():
        return _unavailable_result(domain)

    try:
        bundle = model_provider()
        features = feature_loader(data_path)
        prediction = predictor(bundle, features)
        numeric_label = int(prediction[0])
        label = "good" if numeric_label == 1 else "bad"
        ordered_features = features[bundle["features"]]
        confidence = prediction_confidence(
            bundle["model"], ordered_features, numeric_label
        )
        return {
            "label": label,
            "confidence": confidence,
            "coaching_labels": generate_prediction_labels(
                domain,
                label,
                confidence,
                features,
                bundle.get("good_form_reference", {}),
            ),
        }
    except (KeyError, ValueError, OSError) as error:
        logger.warning("%s model unavailable: %s", domain, error)
        return _unavailable_result(domain)


def _predict_in_workspace(
    video_path: Path,
    work_dir: Path,
    *,
    device: str,
    include_artifact_paths: bool,
    pipeline: str,
    capture_diagnostics: bool,
) -> dict:
    work_dir.mkdir(parents=True, exist_ok=True)
    artifacts = break_down_video(
        video_path,
        work_dir,
        work_dir,
        device=device,
        clean=True,
        pipeline=pipeline,
        capture_diagnostics=capture_diagnostics,
    )

    landmark_path = Path(artifacts["landmarks"])
    trajectory_path = Path(artifacts["trajectory"])
    annotated_video = Path(artifacts["annotated_video"])
    for required_path in (landmark_path, trajectory_path, annotated_video):
        if not required_path.is_file():
            raise RuntimeError(
                "The analysis pipeline did not produce all required artifacts"
            )

    form_result = _classify(
        model_path=LANDMARK_MODEL_PATH,
        model_provider=get_landmark_model,
        feature_loader=load_single_landmark_file,
        predictor=landmark_predict,
        data_path=landmark_path,
        domain="form",
    )
    trajectory_result = _classify(
        model_path=TRAJECTORY_MODEL_PATH,
        model_provider=get_trajectory_model,
        feature_loader=load_trajectory,
        predictor=trajectory_predict,
        data_path=trajectory_path,
        domain="trajectory",
    )
    player_name, similarity, player_path = compare_user_to_player(
        landmark_path, NBA_DATA_DIR, NBA_VIDEO_DIR
    )

    result = {
        "success": True,
        "form_classification": form_result["label"],
        "trajectory_classification": trajectory_result["label"],
        "form_confidence": form_result["confidence"],
        "trajectory_confidence": trajectory_result["confidence"],
        "coaching_labels": (
            form_result["coaching_labels"] + trajectory_result["coaching_labels"]
        ),
        "player_name": player_name,
        "similarity_percentage": similarity,
        "metrics": {
            "frames": int(artifacts["frames"]),
            "shot_frames": int(artifacts["shot_frames"]),
            "release_frames": int(artifacts["release_frames"]),
        },
    }
    if include_artifact_paths:
        run_path = Path(artifacts["run_path"])
        result["artifacts"] = {
            "landmarks": str(landmark_path),
            "trajectory": str(trajectory_path),
            "annotated_video": str(annotated_video),
            "player_recording": player_path,
        }
        metrics_path = run_path / "pipeline_metrics.json"
        if metrics_path.is_file():
            result["artifacts"]["pipeline_metrics"] = str(metrics_path)
        diagnostics_path = run_path / "detections.json"
        if diagnostics_path.is_file():
            result["artifacts"]["detections"] = str(diagnostics_path)

    # Fail immediately if a future change adds a non-JSON result value.
    json.dumps(result)
    return result


def predict_video(
    video_path: str | Path,
    work_dir: str | Path | None = None,
    *,
    device: str = "cpu",
    pipeline: str = "optimized",
    capture_diagnostics: bool = False,
) -> dict:
    """Analyze one basketball shooting video without Flask or HTTP objects.

    When ``work_dir`` is omitted, a job-specific directory is created below
    the operating system's temporary root and removed before this function
    returns. AWS Lambda maps that root to ``/tmp``. Callers that need the
    generated artifact files (the legacy server and future Lambda worker)
    provide their own job directory and remain responsible for cleanup.
    """
    resolved_video = Path(video_path).expanduser().resolve()
    if not resolved_video.is_file():
        raise FileNotFoundError(f"Video not found: {resolved_video}")

    if work_dir is not None:
        resolved_work_dir = Path(work_dir).expanduser().resolve()
        return _predict_in_workspace(
            resolved_video,
            resolved_work_dir,
            device=device,
            include_artifact_paths=True,
            pipeline=pipeline,
            capture_diagnostics=capture_diagnostics,
        )

    with tempfile.TemporaryDirectory(prefix="sharp-shooter-") as temporary_dir:
        return _predict_in_workspace(
            resolved_video,
            Path(temporary_dir),
            device=device,
            include_artifact_paths=False,
            pipeline=pipeline,
            capture_diagnostics=capture_diagnostics,
        )
