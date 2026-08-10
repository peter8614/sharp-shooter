"""Command-line workflow for extracting and classifying basketball shot data."""

import argparse
import csv
import math
import shutil
from pathlib import Path
from typing import Optional

import cv2
import joblib
import mediapipe as mp
import pandas as pd

from landmark_classification import load_single_landmark_file
from trajectory_classification import load_trajectory
from video_pipeline import process_video


BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = BACKEND_DIR / "output"
# Keep the CSV schema in MediaPipe's left-to-right anatomical order.
LANDMARK_COLUMNS = [
    "Left Shoulder",
    "Right Shoulder",
    "Left Elbow",
    "Right Elbow",
    "Left Wrist",
    "Right Wrist",
]


def _joint_angle(shoulder, elbow, wrist) -> float:
    """Return the shoulder-elbow-wrist angle in radians.

    The vectors start at the elbow, so a fully extended arm is close to pi radians.
    """
    upper = (shoulder.x - elbow.x, shoulder.y - elbow.y)
    lower = (wrist.x - elbow.x, wrist.y - elbow.y)
    upper_length = math.hypot(*upper)
    lower_length = math.hypot(*lower)
    if upper_length == 0 or lower_length == 0:
        raise ValueError("Cannot calculate an angle from coincident landmarks")
    cosine = (upper[0] * lower[0] + upper[1] * lower[1]) / (
        upper_length * lower_length
    )
    # Floating-point rounding can otherwise put the cosine just outside acos' domain.
    return math.acos(max(-1.0, min(1.0, cosine)))


def detect_shooting_motion(
    pose_landmarks,
    shooting_arm: str,
    previous_arm_angle: Optional[float],
    threshold: float = 0.1,
):
    """Detect an elevated, extending shooting arm in one pose frame.

    Returns whether the arm is moving through a shot, the current elbow angle, and
    whether the arm has crossed the configured release posture.
    """
    if not pose_landmarks:
        return False, previous_arm_angle, False

    arm = shooting_arm.upper()
    if arm not in {"R", "L"}:
        raise ValueError("shooting_arm must be 'R' or 'L'")

    # MediaPipe Pose: shoulders 11/12, elbows 13/14, wrists 15/16.
    shoulder_idx, elbow_idx, wrist_idx = (12, 14, 16) if arm == "R" else (11, 13, 15)
    landmarks = pose_landmarks.landmark
    shoulder, elbow, wrist = (
        landmarks[shoulder_idx],
        landmarks[elbow_idx],
        landmarks[wrist_idx],
    )

    if min(shoulder.visibility, elbow.visibility, wrist.visibility) < 0.5:
        return False, previous_arm_angle, False

    arm_angle = _joint_angle(shoulder, elbow, wrist)
    # MediaPipe's normalized y coordinate increases toward the bottom of the image.
    wrist_is_raised = wrist.y < shoulder.y
    angle_change = (
        abs(arm_angle - previous_arm_angle) if previous_arm_angle is not None else 0.0
    )
    is_shooting = wrist_is_raised and angle_change >= threshold
    # A release is approximated by a raised arm extending beyond 150 degrees.
    is_released = (
        wrist_is_raised
        and previous_arm_angle is not None
        and arm_angle >= math.radians(150)
        and arm_angle > previous_arm_angle
    )
    return is_shooting, arm_angle, is_released


def save_landmark_data(csv_writer, frame_idx: int, pose_landmarks) -> None:
    """Write the upper-body landmarks for one detected shot frame to CSV."""
    if not pose_landmarks:
        return
    landmarks = [pose_landmarks.landmark[index] for index in (11, 12, 13, 14, 15, 16)]
    csv_writer.writerow(
        [frame_idx] + [f"{lm.x:.8f},{lm.y:.8f},{lm.z:.8f}" for lm in landmarks]
    )


def extract_landmarks(
    video_path: Path,
    csv_path: Path,
    shooting_arm: str = "R",
) -> dict:
    """Extract visible shooting-motion landmarks from a video.

    Only frames that are part of a likely shooting motion are stored. This prevents
    unrelated movement before and after the shot from dominating classifier input.
    """
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Unable to open video: {video_path}")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    previous_angle: Optional[float] = None
    frame_count = shot_frame_count = release_count = 0

    # A separate Pose instance per video prevents tracking state leaking between clips.
    pose_module = mp.solutions.pose
    with pose_module.Pose(static_image_mode=False) as pose, csv_path.open(
        "w", newline="", encoding="utf-8"
    ) as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Frame", *LANDMARK_COLUMNS])

        try:
            while capture.isOpened():
                success, frame = capture.read()
                if not success:
                    break
                # OpenCV supplies BGR pixels while MediaPipe expects RGB pixels.
                result = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                if result.pose_landmarks:
                    is_shooting, previous_angle, is_released = detect_shooting_motion(
                        result.pose_landmarks, shooting_arm, previous_angle
                    )
                    if is_shooting or is_released:
                        save_landmark_data(writer, frame_count, result.pose_landmarks)
                        shot_frame_count += 1
                    if is_released:
                        release_count += 1
                frame_count += 1
        finally:
            capture.release()

    return {
        "frames": frame_count,
        "shot_frames": shot_frame_count,
        "release_frames": release_count,
        "landmarks": csv_path,
    }


def _append_dataset_entry(list_path: Path, file_path: Path, classification: int) -> None:
    """Add or update one labeled file in a dataset index."""
    list_path.parent.mkdir(parents=True, exist_ok=True)
    if list_path.exists():
        entries = pd.read_csv(list_path)
    else:
        entries = pd.DataFrame(columns=["file_path", "classification"])
    entry = pd.DataFrame(
        [{"file_path": str(file_path.resolve()), "classification": int(classification)}]
    )
    # Re-labeling a video updates its existing row instead of creating duplicates.
    entries = pd.concat([entries, entry], ignore_index=True).drop_duplicates(
        subset=["file_path"], keep="last"
    )
    entries.to_csv(list_path, index=False)


def organize_trajectory_data(
    file_name: str,
    classification: int,
    source_path: Path,
) -> Path:
    """Copy a generated trajectory into the labeled trajectory dataset."""
    destination = (
        BACKEND_DIR / "data" / "trajectory_data" / "trajectories" / f"{file_name}_trajectories.txt"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    _append_dataset_entry(
        BACKEND_DIR / "data" / "trajectory_data" / "trajectories_list.csv",
        destination,
        classification,
    )
    return destination


def organize_landmark_data(
    file_name: str,
    classification: int,
    source_path: Path,
) -> Path:
    """Copy generated pose landmarks into the labeled form dataset."""
    destination = (
        BACKEND_DIR / "data" / "landmark_data" / "landmarks" / f"{file_name}_landmarks.csv"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    _append_dataset_entry(
        BACKEND_DIR / "data" / "landmark_data" / "landmarks_list.csv",
        destination,
        classification,
    )
    return destination


def _predict_from_bundle(model_path: Path, sample: pd.DataFrame) -> Optional[dict]:
    """Run a saved classifier bundle, or return None when it has not been trained."""
    if not model_path.is_file():
        return None
    bundle = joblib.load(model_path)
    if not isinstance(bundle, dict) or not {"model", "features"}.issubset(bundle):
        raise ValueError(f"Invalid classifier bundle: {model_path}")
    # Reapply the training column order before passing data to scikit-learn.
    features = sample.drop(columns=["Label"], errors="ignore").reindex(
        columns=bundle["features"]
    )
    if features.isnull().any().any():
        raise ValueError(f"Classifier feature mismatch: {model_path}")
    model = bundle["model"]
    label = int(model.predict(features)[0])
    confidence = None
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(features)[0]
        confidence = float(max(probabilities))
    return {"label": label, "confidence": confidence}


def analyze_video(
    video_path: Path,
    output_root: Path = DEFAULT_OUTPUT,
    shooting_arm: str = "R",
    device: str = "cpu",
    clean: bool = False,
) -> dict:
    """Run pose extraction, ball tracking, and any available classifiers."""
    video_path = Path(video_path).expanduser().resolve()
    output_root = Path(output_root).expanduser().resolve()
    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")

    run_path = output_root / video_path.stem
    pose_result = extract_landmarks(
        video_path, run_path / "landmark_data.csv", shooting_arm
    )
    process_video(video_path, output_root, device=device, clean=clean)
    form_model_path = BACKEND_DIR / "models" / "landmark_classifier.joblib"
    arc_model_path = BACKEND_DIR / "models" / "trajectory_classifier.joblib"
    form_prediction = None
    arc_prediction = None
    # Classifiers are optional until the user has collected enough labeled videos.
    if form_model_path.is_file():
        form_prediction = _predict_from_bundle(
            form_model_path,
            load_single_landmark_file(run_path / "landmark_data.csv", 0),
        )
    if arc_model_path.is_file():
        arc_prediction = _predict_from_bundle(
            arc_model_path, load_trajectory(run_path / "trajectory.txt", 0)
        )
    return {
        **pose_result,
        "output_dir": run_path,
        "trajectory": run_path / "trajectory.txt",
        "annotated_video": run_path / f"output_{video_path.stem}.avi",
        "form_prediction": form_prediction,
        "arc_prediction": arc_prediction,
    }


def main(
    video_path: str | Path,
    form_classification: Optional[int] = None,
    arc_classification: Optional[int] = None,
    **kwargs,
) -> dict:
    """Analyze one video and optionally register it as labeled training data."""
    result = analyze_video(Path(video_path), **kwargs)
    video_name = Path(video_path).stem
    if form_classification is not None:
        organize_landmark_data(
            video_name, form_classification, Path(result["landmarks"])
        )
    if arc_classification is not None:
        organize_trajectory_data(
            video_name, arc_classification, Path(result["trajectory"])
        )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze a basketball shooting video.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--arm", choices=["R", "L"], default="R")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--form-label", type=int, choices=[0, 1])
    parser.add_argument("--arc-label", type=int, choices=[0, 1])
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    analysis = main(
        args.video,
        form_classification=args.form_label,
        arc_classification=args.arc_label,
        output_root=args.output,
        shooting_arm=args.arm,
        device=args.device,
        clean=args.clean,
    )
    for key, value in analysis.items():
        print(f"{key}: {value}")
