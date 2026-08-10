from pathlib import Path

import cv2
from tqdm import tqdm


def convert_to_video(images_path: Path, output_path: Path, fps: float = 30.0) -> None:
    filenames = images_path.glob("*.jpg")
    filenames = sorted(filenames, key=lambda x: int(x.stem))

    if not filenames:
        raise ValueError(f"No JPG frames found in: {images_path}")

    img = cv2.imread(str(filenames[0]))
    if img is None:
        raise ValueError(f"Unable to read image: {filenames[0]}")
    height, width, _ = img.shape
    out = cv2.VideoWriter(
        str(output_path), cv2.VideoWriter_fourcc(*"DIVX"), fps, (width, height)
    )
    if not out.isOpened():
        raise OSError(f"Unable to create video: {output_path}")

    progress_bar = tqdm(filenames)
    for filename in progress_bar:
        progress_bar.set_description("Making a video")
        img = cv2.imread(str(filename))
        if img is None or img.shape[:2] != (height, width):
            out.release()
            raise ValueError(f"Invalid or inconsistent frame: {filename}")
        out.write(img)

    out.release()
