"""Local-only Lambda container probe for real-video Phase 7 validation.

The production image continues to start ``inference_worker.lambda_handler``.
The validation script overrides the image command with this handler and mounts
demo videos read-only below ``/tmp/videos``.
"""

from __future__ import annotations

import time

_module_import_started = time.perf_counter()

import json
from importlib.metadata import PackageNotFoundError, version
import os
import platform
import shutil
import tempfile
import threading
from pathlib import Path

import psutil

from core.inference import predict_video
from aws_backend import reference_catalog, video_artifacts
from yolo_detector import detector_is_cached


_module_import_seconds = time.perf_counter() - _module_import_started
_invocation_count = 0
_invocation_lock = threading.Lock()


def _directory_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _peak_rss_bytes() -> int | None:
    try:
        import resource

        # Linux reports ru_maxrss in KiB. The Lambda image is always Linux.
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    except (ImportError, OSError):
        return None


def _package_version(distribution: str) -> str | None:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def _safe_video_path(raw_path: object, allowed_root: Path) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("video_path must be a non-empty string")
    video_path = Path(raw_path).expanduser().resolve()
    try:
        video_path.relative_to(allowed_root)
    except ValueError as error:
        raise ValueError("video_path must be below the read-only video root") from error
    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")
    return video_path


def lambda_handler(event, _context):
    """Run one local video and return result plus container diagnostics."""
    if os.environ.get("SHARP_SHOOTER_LOCAL_SMOKE") != "1":
        raise RuntimeError("The local smoke handler is disabled")
    if not isinstance(event, dict):
        raise ValueError("The invocation event must be an object")
    pipeline = event.get("pipeline", "optimized")
    if pipeline not in ("optimized", "legacy"):
        raise ValueError("pipeline must be 'optimized' or 'legacy'")

    video_root = Path(os.environ.get("LOCAL_VIDEO_ROOT", "/tmp/videos")).resolve()
    work_root = Path(
        os.environ.get("LOCAL_WORK_ROOT", "/tmp/sharp-shooter-smoke")
    ).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    video_path = _safe_video_path(event.get("video_path"), video_root)

    global _invocation_count
    with _invocation_lock:
        _invocation_count += 1
        invocation_number = _invocation_count

    cached_before = detector_is_cached(device="cpu")
    rss_before = psutil.Process().memory_info().rss
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(
        prefix="phase7-", dir=work_root
    ) as temporary_dir:
        invocation_root = Path(temporary_dir)
        local_video = invocation_root / f"input{video_path.suffix.lower()}"
        shutil.copy2(video_path, local_video)
        result = predict_video(
            local_video,
            work_dir=invocation_root / "analysis",
            device="cpu",
            pipeline=pipeline,
        )
        media_probe = None
        if event.get("verify_media") is True:
            converted = video_artifacts.convert_annotated_video(
                result["artifacts"]["annotated_video"], invocation_root / "processed.mp4"
            )
            media_probe = {"processed_video_bytes": converted.stat().st_size}
            catalog_path = os.environ.get("LOCAL_REFERENCE_CATALOG_FILE")
            if catalog_path:
                catalog = reference_catalog.parse_catalog(Path(catalog_path).read_bytes())
                reference, score = reference_catalog.closest_reference(
                    result["artifacts"]["landmarks"], catalog
                )
                media_probe["reference_player"] = reference.player_name if reference else None
                media_probe["reference_similarity_percentage"] = score
        temporary_job_bytes = _directory_size(invocation_root)
    elapsed_seconds = time.perf_counter() - started
    cached_after = detector_is_cached(device="cpu")
    rss_after = psutil.Process().memory_info().rss
    peak_rss = max(rss_before, rss_after, _peak_rss_bytes() or 0)
    _, _, tmp_free = shutil.disk_usage(work_root)

    # Artifact paths point at a cleaned temporary directory and are not part of
    # the production result schema, so remove them before parity comparison.
    public_result = dict(result)
    public_result.pop("artifacts", None)
    response = {
        "result": public_result,
        "runtime": {
            "architecture": platform.machine(),
            "pipeline": pipeline,
            "python": platform.python_version(),
            "torch": _package_version("torch"),
            "torchvision": _package_version("torchvision"),
            "mediapipe": _package_version("mediapipe"),
            "opencv": _package_version("opencv-python-headless"),
            "scikit_learn": _package_version("scikit-learn"),
            "invocation_number": invocation_number,
            "cold_start": invocation_number == 1,
            "detector_cached_before": cached_before,
            "detector_cached_after": cached_after,
            "model_reused": cached_before and cached_after,
            "elapsed_seconds": round(elapsed_seconds, 6),
            "module_import_seconds": round(_module_import_seconds, 6),
            "rss_before_bytes": rss_before,
            "rss_after_bytes": rss_after,
            "peak_rss_bytes": peak_rss,
            "temporary_job_bytes": temporary_job_bytes,
            "tmp_free_bytes_after_cleanup": tmp_free,
        },
    }
    if media_probe is not None:
        response["media_probe"] = media_probe
    json.dumps(response)
    return response
