"""Legacy and warm-reusable YOLOv5 basketball video pipelines."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from pipeline_rendering import (
    convert_to_images,
    convert_to_video,
    draw_trajectory,
    render_trajectory_frame,
)
from yolo_detector import detector_is_cached, get_detector


BACKEND_DIR = Path(__file__).resolve().parent
YOLO_DETECT = BACKEND_DIR / "yolov5" / "detect.py"
DEFAULT_WEIGHTS = BACKEND_DIR / "models" / "yolov5s_basketball.pt"
JPEG_QUALITY = 95


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _write_metrics(run_path: Path, metrics: dict) -> None:
    (run_path / "pipeline_metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _jpeg_compatibility_frame(frame: np.ndarray) -> np.ndarray:
    """Apply the same default-quality JPEG round trip as cv2.imwrite/imread."""
    encoded, buffer = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
    )
    if not encoded:
        raise OSError("Unable to encode an in-memory JPEG frame")
    decoded = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if decoded is None:
        raise ValueError("Unable to decode an in-memory JPEG frame")
    return decoded


def process_video_legacy(
    video_path: Path,
    output_path: Path,
    device: str = "cpu",
    fps: float | None = None,
    clean: bool = False,
    weights_path: Path | None = None,
    capture_diagnostics: bool = False,
) -> Path:
    """Run the original subprocess and per-frame JPEG implementation."""
    started = time.perf_counter()
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
    environment["YOLOv5_AUTOINSTALL"] = "false"
    yolo_metrics_path = run_path / "legacy_yolo_metrics.json"
    environment["SHARP_SHOOTER_YOLO_METRICS"] = str(yolo_metrics_path)
    quiet = os.getenv("SHARP_SHOOTER_PIPELINE_QUIET") == "1"
    subprocess.run(
        command,
        check=True,
        cwd=BACKEND_DIR,
        env=environment,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.DEVNULL if quiet else None,
    )

    trajectory = draw_trajectory(
        run_path / "labels",
        images_raw,
        images_draw,
        ball_conf=0.5,
        max_distance=30,
    )
    np.savetxt(
        run_path / "trajectory.txt",
        np.asarray(trajectory, dtype=int).reshape(-1, 3),
        fmt="%d %d %d",
        header="frame x y",
    )
    convert_to_video(
        images_draw,
        run_path / f"output_{video_path.stem}.avi",
        fps=output_fps,
    )

    peak_temp_bytes = _directory_size(run_path)
    yolo_metrics = {}
    if yolo_metrics_path.is_file():
        yolo_metrics = json.loads(yolo_metrics_path.read_text(encoding="utf-8"))

    if clean:
        shutil.rmtree(images_raw, ignore_errors=True)
        shutil.rmtree(images_draw, ignore_errors=True)
        if copied_video != video_path:
            copied_video.unlink(missing_ok=True)
    _write_metrics(
        run_path,
        {
            "implementation": "legacy",
            "jpeg_quality": JPEG_QUALITY,
            "model_load_seconds": yolo_metrics.get("model_load_seconds"),
            "model_warmup_seconds": yolo_metrics.get("model_warmup_seconds"),
            "model_reused": False,
            "peak_temp_bytes": peak_temp_bytes,
            "total_seconds": time.perf_counter() - started,
        },
    )
    return run_path


def process_video_in_memory(
    video_path: Path,
    output_path: Path,
    device: str = "cpu",
    fps: float | None = None,
    clean: bool = False,
    weights_path: Path | None = None,
    capture_diagnostics: bool = False,
) -> Path:
    """Decode, detect, and render sequentially without frame files."""
    del clean  # The optimized path never creates frame directories.
    started = time.perf_counter()
    video_path = Path(video_path).expanduser().resolve()
    output_root = Path(output_path).expanduser().resolve()
    weights_path = Path(weights_path or DEFAULT_WEIGHTS).expanduser().resolve()
    for required_path, description in (
        (video_path, "video"),
        (weights_path, "basketball weights"),
    ):
        if not required_path.is_file():
            raise FileNotFoundError(f"Missing {description}: {required_path}")

    run_path = output_root / video_path.stem
    run_path.mkdir(parents=True, exist_ok=True)
    was_cached = detector_is_cached(weights_path, device)
    detector = get_detector(weights_path, device)

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Unable to open video: {video_path}")
    source_fps = capture.get(cv2.CAP_PROP_FPS)
    output_fps = fps if fps and fps > 0 else (source_fps if source_fps > 0 else 30.0)

    output_video = run_path / f"output_{video_path.stem}.avi"
    writer = None
    frame_index = 0
    points: list[tuple[int, int]] = []
    observations: list[tuple[int, int, int]] = []
    diagnostics: list[dict] = []
    try:
        while capture.isOpened():
            readable, raw_frame = capture.read()
            if not readable:
                break
            frame = _jpeg_compatibility_frame(raw_frame)
            detections = detector.detect(frame)
            if capture_diagnostics:
                diagnostics.append(
                    {"frame_index": frame_index, "detections": detections}
                )

            rendered, points, new_point = render_trajectory_frame(
                frame,
                detections,
                points,
                ball_conf=0.5,
                max_distance=30,
            )
            if new_point is not None:
                observations.append((frame_index, *new_point))

            if writer is None:
                height, width = rendered.shape[:2]
                writer = cv2.VideoWriter(
                    str(output_video),
                    cv2.VideoWriter_fourcc(*"DIVX"),
                    output_fps,
                    (width, height),
                )
                if not writer.isOpened():
                    raise OSError(f"Unable to create video: {output_video}")
            writer.write(rendered)
            frame_index += 1
    finally:
        capture.release()
        if writer is not None:
            writer.release()

    if frame_index == 0:
        raise ValueError(f"Video contains no readable frames: {video_path}")

    np.savetxt(
        run_path / "trajectory.txt",
        np.asarray(observations, dtype=int).reshape(-1, 3),
        fmt="%d %d %d",
        header="frame x y",
    )
    if capture_diagnostics:
        (run_path / "detections.json").write_text(
            json.dumps(diagnostics, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    peak_temp_bytes = _directory_size(run_path)
    _write_metrics(
        run_path,
        {
            "frames": frame_index,
            "implementation": "optimized",
            "jpeg_quality": JPEG_QUALITY,
            "model_load_seconds": 0.0 if was_cached else detector.load_seconds,
            "model_reused": was_cached,
            "peak_temp_bytes": peak_temp_bytes,
            "total_seconds": time.perf_counter() - started,
        },
    )
    return run_path


def process_video(
    video_path: Path,
    output_path: Path,
    device: str = "cpu",
    fps: float | None = None,
    clean: bool = False,
    weights_path: Path | None = None,
    *,
    implementation: str = "optimized",
    capture_diagnostics: bool = False,
) -> Path:
    """Run the selected implementation; optimized is the production default."""
    implementations = {
        "legacy": process_video_legacy,
        "optimized": process_video_in_memory,
    }
    try:
        pipeline = implementations[implementation]
    except KeyError as error:
        raise ValueError(f"Unknown video pipeline: {implementation}") from error
    return pipeline(
        video_path,
        output_path,
        device=device,
        fps=fps,
        clean=clean,
        weights_path=weights_path,
        capture_diagnostics=capture_diagnostics,
    )
