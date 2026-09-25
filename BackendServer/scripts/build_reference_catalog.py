"""Build a validated, content-addressed catalog from locally supplied NBA clips.

This writes a manifest and upload plan only. Publishing requires a separate,
explicitly authorized operation; neither videos nor pose data enter Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from NBA_compare import _variance_vector


def transcode_reference_video(source: Path, destination: Path, ffmpeg_exe: str) -> Path:
    """Make reference clips consistently playable on Android/iOS decoders."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            ffmpeg_exe, "-nostdin", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(source), "-map", "0:v:0", "-an",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-profile:v", "baseline", "-level:v", "4.0",
            "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(destination),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0 or not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"Could not convert reference video: {source.name}")
    return destination


def build_catalog(
    data_dir: Path, video_dir: Path, output_dir: Path, ffmpeg_exe: str
) -> tuple[dict, list[dict], list[str]]:
    entries = []
    uploads = []
    skipped = []
    used_ids = set()
    for variance_path in sorted(data_dir.glob("*_variance.txt")):
        sample_name = variance_path.name.removesuffix("_variance.txt")
        video_path = video_dir / f"{sample_name}.mp4"
        if not video_path.is_file():
            skipped.append(sample_name)
            continue
        if "_" not in sample_name:
            raise ValueError(f"Reference filename lacks a sample number: {sample_name}")
        player_name = sample_name.rsplit("_", 1)[0]
        reference_id = re.sub(r"[^a-z0-9]+", "-", sample_name.lower()).strip("-")
        if not reference_id or len(reference_id) > 63 or reference_id in used_ids:
            raise ValueError(f"Invalid or duplicate reference ID: {sample_name}")
        variance = json.loads(variance_path.read_text(encoding="utf-8"))
        _variance_vector(variance)
        playback_path = transcode_reference_video(
            video_path, output_dir / "videos" / f"{reference_id}.mp4", ffmpeg_exe
        )
        video_hash = hashlib.sha256(playback_path.read_bytes()).hexdigest()
        video_key = f"references/videos/{reference_id}-{video_hash[:16]}.mp4"
        entries.append(
            {
                "id": reference_id,
                "player_name": player_name,
                "variance": variance,
                "video_key": video_key,
            }
        )
        uploads.append(
            {"id": reference_id, "source": str(playback_path.resolve()), "key": video_key}
        )
        used_ids.add(reference_id)
    if not entries:
        raise ValueError("No reference videos match valid variance files")
    return {"version": 1, "entries": entries}, uploads, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--video-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise RuntimeError("Install imageio-ffmpeg before publishing reference clips") from error
    catalog, uploads, skipped = build_catalog(
        args.data_dir, args.video_dir, args.output_dir, imageio_ffmpeg.get_ffmpeg_exe()
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    catalog_name = f"catalog-{digest}.json"
    (args.output_dir / catalog_name).write_bytes(raw)
    plan = {
        "catalog_file": str((args.output_dir / catalog_name).resolve()),
        "catalog_key": f"references/{catalog_name}",
        "uploads": uploads,
        "skipped_without_video": skipped,
    }
    (args.output_dir / "upload-plan.json").write_text(
        json.dumps(plan, indent=2), encoding="utf-8"
    )
    print(json.dumps({"catalog_key": plan["catalog_key"], "matched": len(uploads), "skipped_without_video": skipped}))


if __name__ == "__main__":
    main()
