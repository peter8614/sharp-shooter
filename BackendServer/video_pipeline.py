"""Portable YOLOv5 pipeline for rendering basketball trajectories."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

from utils import convert_to_images, convert_to_video, draw_trajectory


BACKEND_DIR = Path(__file__).resolve().parent
YOLO_DETECT = BACKEND_DIR / "yolov5_custom" / "detect.py"
DEFAULT_WEIGHTS = BACKEND_DIR / "models" / "yolov5s_basketball.pt"


def process_video(
    video_path: Path,
    output_path: Path,
    device: str = "cpu",
    fps: float | None = None,
    clean: bool = False,
    weights_path: Path | None = None,
) -> Path:
    """Detect the ball, render every frame, and return the run directory."""
    video_path = Path(video_path).expanduser().resolve()
    output_root = Path(output_path).expanduser().resolve()
    weights_path = Path(weights_path or DEFAULT_WEIGHTS).expanduser().resolve()
    for required_path, description in (
        (video_path, "video"),
        (YOLO_DETECT, "YOLOv5 detector"),
        (weights_path, "basketball weights"),
    ):
        if not required_path.is_file():
            raise FileNotFoundError(f"Missing {description}: {required_path}")

    run_path = output_root / video_path.stem
    images_raw = run_path / "images_raw"
    images_draw = run_path / "images_draw"
    images_raw.mkdir(parents=True, exist_ok=True)
    images_draw.mkdir(parents=True, exist_ok=True)

    capture = cv2.VideoCapture(str(video_path))
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    capture.release()
    output_fps = fps if fps and fps > 0 else (source_fps if source_fps > 0 else 30.0)

    copied_video = run_path / video_path.name
    if copied_video != video_path:
        shutil.copyfile(video_path, copied_video)
    convert_to_images(video_path, images_raw)

    command = [
        sys.executable,
        str(YOLO_DETECT),
        "--weights",
        str(weights_path),
        "--source",
        str(images_raw),
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
    environment = os.environ.copy()
    # Ultralytics checks that its configuration parent exists before startup.
    yolo_config_dir = output_root / ".ultralytics"
    yolo_config_dir.mkdir(parents=True, exist_ok=True)
    environment["YOLO_CONFIG_DIR"] = str(yolo_config_dir)
    # Keep Matplotlib's generated font cache beside the other run artifacts.
    matplotlib_config_dir = output_root / ".matplotlib"
    matplotlib_config_dir.mkdir(parents=True, exist_ok=True)
    environment["MPLCONFIGDIR"] = str(matplotlib_config_dir)
    subprocess.run(command, check=True, cwd=BACKEND_DIR, env=environment)

    trajectory = draw_trajectory(
        run_path / "labels",
        images_raw,
        images_draw,
        ball_conf=0.5,
        max_distance=30,
    )
    np.savetxt(
        run_path / "trajectory.txt",
        np.asarray(trajectory, dtype=int),
        fmt="%d %d %d",
        header="frame x y",
    )
    convert_to_video(
        images_draw,
        run_path / f"output_{video_path.stem}.avi",
        fps=output_fps,
    )

    if clean:
        shutil.rmtree(images_raw, ignore_errors=True)
        shutil.rmtree(images_draw, ignore_errors=True)
        if copied_video != video_path:
            copied_video.unlink(missing_ok=True)
    return run_path
