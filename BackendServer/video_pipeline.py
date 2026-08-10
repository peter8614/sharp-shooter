"""Portable YOLOv5 video pipeline for detecting and drawing ball trajectories."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

from utils import convert_to_images, convert_to_video, draw_trajectory


BACKEND_DIR = Path(__file__).resolve().parent
# Resolve bundled scripts and weights relative to this file, not the caller's machine.
DEFAULT_WEIGHTS = BACKEND_DIR / "models" / "yolov5s_basketball.pt"
YOLO_DETECT = BACKEND_DIR / "yolov5" / "detect.py"


def process_video(
    video_path: Path,
    output_path: Path,
    device: str = "cpu",
    fps: float | None = None,
    clean: bool = False,
    weights_path: Path | None = None,
) -> Path:
    """Detect the basketball, draw its trajectory, and return the output folder.

    Intermediate source and rendered frames can be retained for debugging or removed
    with ``clean=True`` after the final trajectory and video have been produced.
    """
    video_path = Path(video_path).expanduser().resolve()
    output_root = Path(output_path).expanduser().resolve()
    weights_path = Path(weights_path or DEFAULT_WEIGHTS).expanduser().resolve()

    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not YOLO_DETECT.is_file():
        raise FileNotFoundError(f"YOLOv5 detector not found: {YOLO_DETECT}")
    if not weights_path.is_file():
        raise FileNotFoundError(f"Basketball weights not found: {weights_path}")

    run_path = output_root / video_path.stem
    images_raw_path = run_path / "images_raw"
    images_draw_path = run_path / "images_draw"
    images_raw_path.mkdir(parents=True, exist_ok=True)
    images_draw_path.mkdir(parents=True, exist_ok=True)

    # Keep a local copy beside the run artifacts unless the source is already there.
    copied_video = run_path / video_path.name
    if copied_video != video_path:
        shutil.copyfile(video_path, copied_video)

    # Preserve the source frame rate unless the caller explicitly overrides it.
    capture = cv2.VideoCapture(str(video_path))
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    capture.release()
    output_fps = fps if fps and fps > 0 else (source_fps if source_fps > 0 else 30.0)

    print("Converting the video to images...")
    convert_to_images(video_path, images_raw_path, video_stride=1)

    # Use the active interpreter so the detector shares this process' environment.
    detect_cmd = [
        sys.executable,
        str(YOLO_DETECT),
        "--weights",
        str(weights_path),
        "--source",
        str(images_raw_path),
        "--save-txt",
        "--save-conf",
        "--nosave",
        "--project",
        str(output_root),
        "--name",
        video_path.stem,
        "--exist-ok",
        "--device",
        device,
    ]
    # Keep Ultralytics settings inside the output tree instead of the user's profile.
    process_env = os.environ.copy()
    process_env["YOLO_CONFIG_DIR"] = str(output_root / ".ultralytics")
    subprocess.run(
        detect_cmd, check=True, cwd=BACKEND_DIR, env=process_env
    )

    # Drawing iterates over every source frame, including frames without detections.
    trajectory = draw_trajectory(
        run_path / "labels",
        images_raw_path,
        images_draw_path,
        ball_conf=0.5,
        max_distance=30,
    )
    np.savetxt(run_path / "trajectory.txt", np.asarray(trajectory, dtype=int), fmt="%d %d")

    convert_to_video(
        images_draw_path,
        run_path / f"output_{video_path.stem}.avi",
        fps=output_fps,
    )

    # Detection labels, the trajectory, and the final video remain after cleanup.
    if clean:
        shutil.rmtree(images_raw_path, ignore_errors=True)
        shutil.rmtree(images_draw_path, ignore_errors=True)
        if copied_video != video_path:
            copied_video.unlink(missing_ok=True)

    return run_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path, help="Path to the video file.")
    parser.add_argument("-o", "--output", type=Path, default=Path("output"))
    parser.add_argument("-d", "--device", default="cpu")
    parser.add_argument("--fps", type=float, default=None)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument("-c", "--clean", action="store_true")
    args = parser.parse_args()

    result = process_video(
        args.video, args.output, args.device, args.fps, args.clean, args.weights
    )
    print(f"Output written to {result}")
