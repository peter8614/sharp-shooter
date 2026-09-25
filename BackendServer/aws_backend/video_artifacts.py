"""Convert the pipeline's annotated AVI into a phone-playable MP4."""

from __future__ import annotations

import subprocess
from pathlib import Path


def convert_annotated_video(input_path: str | Path, output_path: str | Path) -> Path:
    source = Path(input_path)
    output = Path(output_path)
    if not source.is_file():
        raise FileNotFoundError("Annotated video was not produced")
    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise RuntimeError("The Lambda image lacks an FFmpeg encoder") from error
    completed = subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-nostdin", "-y", "-loglevel", "error", "-i", str(source),
            "-map", "0:v:0", "-an", "-c:v", "libx264",
            "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(output),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("Annotated video MP4 conversion failed")
    return output
