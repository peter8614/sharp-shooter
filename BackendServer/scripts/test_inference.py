"""Run the framework-independent inference pipeline for one local video."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.inference import predict_video  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Basketball video to analyze")
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Keep generated artifacts in this job-specific directory",
    )
    parser.add_argument("--device", default="cpu", help="YOLO inference device")
    parser.add_argument(
        "--pipeline",
        choices=("optimized", "legacy"),
        default="optimized",
        help="Video pipeline implementation (default: optimized)",
    )
    arguments = parser.parse_args()

    try:
        result = predict_video(
            arguments.video,
            work_dir=arguments.work_dir,
            device=arguments.device,
            pipeline=arguments.pipeline,
        )
    except Exception as error:
        print(json.dumps({"success": False, "error": str(error)}), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
