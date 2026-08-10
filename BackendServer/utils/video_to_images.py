from pathlib import Path

import cv2


def convert_to_images(
    video_path: Path, output_path: Path, video_stride: int = 1
) -> None:
    """
    Converts a video file to a sequence of images.

    Args:
        video_path: Path to the video file.
        output_path: Path to the directory where the images will be saved.
        video_stride: The stride of the video frames to be saved as images.
    """
    if video_stride < 1:
        raise ValueError("Video stride must be positive.")

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Unable to open video: {video_path}")

    current_frame = 0
    while capture.isOpened():
        ret, image = capture.read()
        if not ret:
            break

        if current_frame % video_stride == 0:
            if not cv2.imwrite(str(output_path / f"{current_frame:05d}.jpg"), image):
                capture.release()
                raise OSError(f"Unable to write a frame to: {output_path}")

        current_frame += 1

    capture.release()
    if current_frame == 0:
        raise ValueError(f"Video contains no readable frames: {video_path}")
