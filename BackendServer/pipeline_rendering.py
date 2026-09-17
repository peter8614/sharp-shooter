"""Trajectory rendering helpers shared by disk and in-memory pipelines."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.signal import savgol_filter
from tqdm import tqdm


def smooth_trajectory(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Smooth nearby fragments without connecting large detection jumps."""
    if not points:
        return []
    split_trajectory = [[points[0]]]
    current_split = 0
    for index in range(1, len(points)):
        distance = np.linalg.norm(
            np.array(points[index - 1]) - np.array(points[index])
        )
        if distance < 15:
            split_trajectory[current_split].append(points[index])
        else:
            split_trajectory.append([points[index]])
            current_split += 1

    smoothed_x: list[int] = []
    smoothed_y: list[int] = []
    for fragment in split_trajectory:
        x_values = np.array([point[0] for point in fragment])
        y_values = np.array([point[1] for point in fragment])
        if len(y_values) > 20:
            y_values = [int(round(value)) for value in savgol_filter(y_values, 15, 3)]
        smoothed_x.extend(x_values)
        smoothed_y.extend(y_values)
    return list(zip(smoothed_x, smoothed_y))


def get_pixel_coords(
    detection: dict[str, Any], image_height: int, image_width: int
) -> tuple[int, int, int, int]:
    coordinates = detection["relative_coordinates"]
    return (
        int(image_width * coordinates["center_x"]),
        int(image_height * coordinates["center_y"]),
        int(image_width * coordinates["width"]),
        int(image_height * coordinates["height"]),
    )


def draw_circle(image, x: int, y: int, width: int, height: int) -> None:
    radius = max(int(width / 2), int(height / 2))
    cv2.circle(image, (x, y), radius, (0, 255, 0), 2)
    cv2.circle(image, (x, y), 2, (0, 255, 0), -2)


def draw_line_fragment(
    image,
    points: list[tuple[int, int]],
    color: tuple[int, int, int] = (135, 0, 190),
    thickness: int = 2,
    max_distance: int = 30,
):
    for index in range(1, len(points)):
        distance = np.linalg.norm(
            np.array(points[index - 1]) - np.array(points[index])
        )
        if distance < max_distance:
            image = cv2.line(
                image, points[index - 1], points[index], color, thickness
            )
    return image


def draw_glowing_line(image, points: list[tuple[int, int]], max_distance: int):
    line_image = np.zeros_like(image)
    line_image = draw_line_fragment(
        line_image,
        points,
        color=(135, 0, 190),
        thickness=2,
        max_distance=max_distance,
    )
    line_image = draw_line_fragment(
        line_image,
        points,
        color=(0, 0, 255),
        thickness=1,
        max_distance=max_distance,
    )
    blurred_line = cv2.GaussianBlur(line_image, (5, 5), 0)
    grayscale = cv2.cvtColor(blurred_line, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(grayscale, 5, 255, cv2.THRESH_BINARY)
    mask = np.stack([mask, mask, mask], axis=2)
    mask = np.where(mask > 0, 0.6, 1)
    image = image * mask
    return cv2.addWeighted(image.astype("uint8"), 1, blurred_line, 1.6, 0)


def load_labels(path: Path) -> list[dict[str, Any]]:
    objects = []
    with path.open(encoding="utf-8") as label_file:
        for line in label_file:
            class_id, center_x, center_y, width, height, confidence = line.split()
            objects.append(
                {
                    "class_id": int(class_id),
                    "relative_coordinates": {
                        "center_x": float(center_x),
                        "center_y": float(center_y),
                        "width": float(width),
                        "height": float(height),
                    },
                    "confidence": float(confidence),
                }
            )
    return objects


def render_trajectory_frame(
    image,
    detections: list[dict[str, Any]],
    points: list[tuple[int, int]],
    *,
    ball_conf: float,
    max_distance: int,
):
    """Render one frame using the legacy trajectory selection rules."""
    selected = None
    maximum_confidence = 0.0
    for detection in detections:
        confidence = detection["confidence"]
        if (
            detection["class_id"] == 0
            and confidence >= ball_conf
            and confidence > maximum_confidence
        ):
            selected = detection
            maximum_confidence = confidence

    new_point = None
    if selected:
        height, width = image.shape[:2]
        ball_x, ball_y, object_width, object_height = get_pixel_coords(
            selected, height, width
        )
        new_point = ball_x, ball_y
        points.append(new_point)
        draw_circle(image, ball_x, ball_y, object_width, object_height)

    points = [point for point in points if point is not None]
    if len(points) > 30:
        points = smooth_trajectory(points)
    return draw_glowing_line(image, points, max_distance), points, new_point


def process_image(
    image_filename: Path,
    label_filename: Path | None,
    points: list[tuple[int, int]],
    images_path: Path,
    ball_conf: float,
    max_distance: int,
):
    detections = (
        load_labels(label_filename)
        if label_filename and label_filename.is_file()
        else []
    )
    image = cv2.imread(str(images_path / image_filename.name), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Unable to read image: {images_path / image_filename.name}")
    return render_trajectory_frame(
        image,
        detections,
        points,
        ball_conf=ball_conf,
        max_distance=max_distance,
    )


def draw_trajectory(
    labels_dir: Path,
    images_path: Path,
    output_path: Path,
    ball_conf: float = 0.3,
    max_distance: int = 30,
) -> list[tuple[int, int, int]]:
    image_files = sorted(images_path.glob("*.jpg"), key=lambda path: int(path.stem))
    if not image_files:
        raise ValueError(f"No source frames found in: {images_path}")

    points: list[tuple[int, int]] = []
    observations: list[tuple[int, int, int]] = []
    progress_bar = tqdm(
        image_files,
        disable=os.getenv("SHARP_SHOOTER_PIPELINE_QUIET") == "1",
    )
    for image_filename in progress_bar:
        progress_bar.set_description("Drawing trajectories")
        label_filename = labels_dir / f"{image_filename.stem}.txt"
        image, points, new_point = process_image(
            image_filename,
            label_filename,
            points,
            images_path,
            ball_conf,
            max_distance,
        )
        if new_point is not None:
            observations.append((int(image_filename.stem), *new_point))
        if not cv2.imwrite(str(output_path / image_filename.name), image):
            raise OSError(f"Unable to write rendered frame: {output_path}")
    return observations


def convert_to_images(
    video_path: Path, output_path: Path, video_stride: int = 1
) -> None:
    if video_stride < 1:
        raise ValueError("Video stride must be positive.")
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Unable to open video: {video_path}")
    current_frame = 0
    try:
        while capture.isOpened():
            readable, image = capture.read()
            if not readable:
                break
            if current_frame % video_stride == 0:
                if not cv2.imwrite(
                    str(output_path / f"{current_frame:05d}.jpg"), image
                ):
                    raise OSError(f"Unable to write a frame to: {output_path}")
            current_frame += 1
    finally:
        capture.release()
    if current_frame == 0:
        raise ValueError(f"Video contains no readable frames: {video_path}")


def convert_to_video(
    images_path: Path, output_path: Path, fps: float = 30.0
) -> None:
    filenames = sorted(images_path.glob("*.jpg"), key=lambda path: int(path.stem))
    if not filenames:
        raise ValueError(f"No JPG frames found in: {images_path}")
    first_image = cv2.imread(str(filenames[0]))
    if first_image is None:
        raise ValueError(f"Unable to read image: {filenames[0]}")
    height, width = first_image.shape[:2]
    writer = cv2.VideoWriter(
        str(output_path), cv2.VideoWriter_fourcc(*"DIVX"), fps, (width, height)
    )
    if not writer.isOpened():
        raise OSError(f"Unable to create video: {output_path}")
    try:
        progress_bar = tqdm(
            filenames,
            disable=os.getenv("SHARP_SHOOTER_PIPELINE_QUIET") == "1",
        )
        for filename in progress_bar:
            progress_bar.set_description("Making a video")
            image = cv2.imread(str(filename))
            if image is None or image.shape[:2] != (height, width):
                raise ValueError(f"Invalid or inconsistent frame: {filename}")
            writer.write(image)
    finally:
        writer.release()
