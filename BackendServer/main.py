"""Pose extraction and basketball-video analysis entry points."""

from __future__ import annotations

import argparse
import csv
import math
import shutil
from pathlib import Path

import cv2
import mediapipe as mp
import pandas as pd

from video_pipeline import process_video


BACKEND_DIR = Path(__file__).resolve().parent
LANDMARK_COLUMNS = [
    "Left Shoulder",
    "Right Shoulder",
    "Left Elbow",
    "Right Elbow",
    "Left Wrist",
    "Right Wrist",
]


def _joint_angle(shoulder, elbow, wrist) -> float:
    """Return the shoulder-elbow-wrist angle in radians."""
    upper = (shoulder.x - elbow.x, shoulder.y - elbow.y)
    lower = (wrist.x - elbow.x, wrist.y - elbow.y)
    upper_length = math.hypot(*upper)
    lower_length = math.hypot(*lower)
    if upper_length == 0 or lower_length == 0:
        raise ValueError("Cannot calculate an angle from coincident landmarks")
    cosine = (upper[0] * lower[0] + upper[1] * lower[1]) / (
        upper_length * lower_length
    )
    # Floating-point rounding can otherwise move the value outside acos' domain.
    return math.acos(max(-1.0, min(1.0, cosine)))


def detect_shooting_motion(
    pose_landmarks,
    shooting_arm: str,
    previous_arm_angle: float | None,
    threshold: float = 0.1,
):
    """Detect a raised and extending shooting arm in one pose frame."""
    if not pose_landmarks:
        return False, previous_arm_angle, False

    arm = shooting_arm.upper()
    if arm not in {"R", "L"}:
        raise ValueError("shooting_arm must be 'R' or 'L'")

    # MediaPipe Pose uses 11/12 for shoulders, 13/14 for elbows, and 15/16 for wrists.
    shoulder_index, elbow_index, wrist_index = (
        (12, 14, 16) if arm == "R" else (11, 13, 15)
    )
    landmarks = pose_landmarks.landmark
    shoulder = landmarks[shoulder_index]
    elbow = landmarks[elbow_index]
    wrist = landmarks[wrist_index]
    if min(shoulder.visibility, elbow.visibility, wrist.visibility) < 0.5:
        return False, previous_arm_angle, False

    angle = _joint_angle(shoulder, elbow, wrist)
    # Normalized image y grows downward, so a smaller wrist y means a raised wrist.
    wrist_is_raised = wrist.y < shoulder.y
    change = abs(angle - previous_arm_angle) if previous_arm_angle is not None else 0.0
    is_shooting = wrist_is_raised and change >= threshold
    is_released = (
        wrist_is_raised
        and previous_arm_angle is not None
        and angle >= math.radians(150)
        and angle > previous_arm_angle
    )
    return is_shooting, angle, is_released


def save_landmark_data(csv_writer, frame_index: int, pose_landmarks) -> None:
    """Write correctly indexed upper-body landmarks for one frame."""
    points = [pose_landmarks.landmark[index] for index in (11, 12, 13, 14, 15, 16)]
    csv_writer.writerow(
        [frame_index] + [f"{point.x:.8f},{point.y:.8f},{point.z:.8f}" for point in points]
    )


def extract_landmarks(video_path: Path, csv_path: Path, shooting_arm: str = "R") -> dict:
    """Extract likely shot frames into a per-video CSV file."""
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Unable to open video: {video_path}")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    previous_angle = None
    frame_count = shot_frame_count = release_frame_count = 0

    # A fresh Pose instance prevents tracking state from leaking across jobs.
    with mp.solutions.pose.Pose(static_image_mode=False) as pose, csv_path.open(
        "w", newline="", encoding="utf-8"
    ) as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Frame", *LANDMARK_COLUMNS])
        try:
            while capture.isOpened():
                success, frame = capture.read()
                if not success:
                    break
                result = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                if result.pose_landmarks:
                    shooting, previous_angle, released = detect_shooting_motion(
                        result.pose_landmarks, shooting_arm, previous_angle
                    )
                    if shooting or released:
                        save_landmark_data(writer, frame_count, result.pose_landmarks)
                        shot_frame_count += 1
                    if released:
                        release_frame_count += 1
                frame_count += 1
        finally:
            capture.release()

    return {
        "frames": frame_count,
        "shot_frames": shot_frame_count,
        "release_frames": release_frame_count,
        "landmarks": csv_path,
    }


def break_down_video(
    video_path,
    landmark_dir,
    trajectory_dir,
    shooting_arm="R",
    device="cpu",
    clean=True,
):
    """Generate isolated landmark, trajectory, and annotated-video artifacts."""
    video_path = Path(video_path).expanduser().resolve()
    landmark_dir = Path(landmark_dir).expanduser().resolve()
    trajectory_dir = Path(trajectory_dir).expanduser().resolve()
    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")

    pose_result = extract_landmarks(
        video_path,
        landmark_dir / "landmark_data.csv",
        shooting_arm,
    )
    run_path = process_video(
        video_path,
        trajectory_dir,
        device=device,
        clean=clean,
    )
    return {
        **pose_result,
        "run_path": run_path,
        "trajectory": run_path / "trajectory.txt",
        "annotated_video": run_path / f"output_{video_path.stem}.avi",
    }


def _append_dataset_entry(index_path: Path, data_path: Path, classification: int) -> None:
    """Add one labeled artifact to a portable dataset index."""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    entries = (
        pd.read_csv(index_path)
        if index_path.exists()
        else pd.DataFrame(columns=["file_path", "classification"])
    )
    relative_path = data_path.resolve().relative_to(BACKEND_DIR)
    new_entry = pd.DataFrame(
        [{"file_path": relative_path.as_posix(), "classification": int(classification)}]
    )
    entries = pd.concat([entries, new_entry], ignore_index=True).drop_duplicates(
        subset=["file_path"], keep="last"
    )
    entries.to_csv(index_path, index=False)


def organize_landmark_data(file_name, classification, source_path):
    """Copy one generated landmark CSV into the labeled form dataset."""
    destination = BACKEND_DIR / "data" / "landmark_data" / "landmarks" / f"{file_name}_landmarks.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    _append_dataset_entry(
        BACKEND_DIR / "data" / "landmark_data" / "landmarks_list.csv",
        destination,
        classification,
    )
    return destination


def organize_trajectory_data(file_name, classification, source_path):
    """Copy one generated trajectory into the labeled arc dataset."""
    destination = BACKEND_DIR / "data" / "trajectory_data" / "trajectories" / f"{file_name}_trajectories.txt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    _append_dataset_entry(
        BACKEND_DIR / "data" / "trajectory_data" / "trajectories_list.csv",
        destination,
        classification,
    )
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze one basketball shot video")
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, default=BACKEND_DIR / "output")
    parser.add_argument("--arm", choices=["R", "L"], default="R")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--clean", action="store_true")
    arguments = parser.parse_args()
    print(
        break_down_video(
            arguments.video,
            arguments.output / arguments.video.stem,
            arguments.output,
            arguments.arm,
            arguments.device,
            arguments.clean,
        )
    )
