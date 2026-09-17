"""Compare legacy disk/subprocess inference with the optimized warm pipeline."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from core.inference import predict_video  # noqa: E402
from yolo_detector import clear_detector_cache  # noqa: E402


DETECTION_TOLERANCE = 2e-6


def _read_json(path: str | Path) -> dict | list:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_trajectory(path: str | Path) -> list[tuple[int, int, int]]:
    observations = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            observations.append(tuple(int(value) for value in line.split()))
    return observations


def _read_legacy_detections(labels_dir: Path) -> dict[int, list[dict]]:
    frames: dict[int, list[dict]] = {}
    for label_path in sorted(labels_dir.glob("*.txt"), key=lambda path: int(path.stem)):
        detections = []
        for line in label_path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            class_id, center_x, center_y, width, height, confidence = line.split()
            detections.append(
                {
                    "class_id": int(float(class_id)),
                    "confidence": float(confidence),
                    "relative_coordinates": {
                        "center_x": float(center_x),
                        "center_y": float(center_y),
                        "width": float(width),
                        "height": float(height),
                    },
                }
            )
        frames[int(label_path.stem)] = detections
    return frames


def _read_optimized_detections(path: str | Path) -> dict[int, list[dict]]:
    return {
        int(frame["frame_index"]): frame["detections"]
        for frame in _read_json(path)
        if frame["detections"]
    }


def _compare_detections(
    legacy: dict[int, list[dict]], optimized: dict[int, list[dict]]
) -> dict:
    all_frames = sorted(set(legacy) | set(optimized))
    mismatched_frames = []
    maximum_coordinate_delta = 0.0
    maximum_confidence_delta = 0.0
    for frame_index in all_frames:
        legacy_items = legacy.get(frame_index, [])
        optimized_items = optimized.get(frame_index, [])
        if len(legacy_items) != len(optimized_items):
            mismatched_frames.append(frame_index)
            continue
        frame_matches = True
        for legacy_item, optimized_item in zip(legacy_items, optimized_items):
            if legacy_item["class_id"] != optimized_item["class_id"]:
                frame_matches = False
            confidence_delta = abs(
                legacy_item["confidence"] - optimized_item["confidence"]
            )
            maximum_confidence_delta = max(
                maximum_confidence_delta, confidence_delta
            )
            if confidence_delta > DETECTION_TOLERANCE:
                frame_matches = False
            for coordinate in ("center_x", "center_y", "width", "height"):
                coordinate_delta = abs(
                    legacy_item["relative_coordinates"][coordinate]
                    - optimized_item["relative_coordinates"][coordinate]
                )
                maximum_coordinate_delta = max(
                    maximum_coordinate_delta, coordinate_delta
                )
                if coordinate_delta > DETECTION_TOLERANCE:
                    frame_matches = False
        if not frame_matches:
            mismatched_frames.append(frame_index)
    return {
        "match": not mismatched_frames,
        "legacy_detection_frames": len(legacy),
        "optimized_detection_frames": len(optimized),
        "legacy_detection_count": sum(map(len, legacy.values())),
        "optimized_detection_count": sum(map(len, optimized.values())),
        "maximum_confidence_delta": maximum_confidence_delta,
        "maximum_normalized_box_delta": maximum_coordinate_delta,
        "mismatched_frames": mismatched_frames,
    }


def _public_result(result: dict) -> dict:
    return {key: value for key, value in result.items() if key != "artifacts"}


def _run(video: Path, work_dir: Path, pipeline: str) -> tuple[dict, float]:
    started = time.perf_counter()
    result = predict_video(
        video,
        work_dir=work_dir,
        pipeline=pipeline,
        capture_diagnostics=pipeline == "optimized",
    )
    return result, time.perf_counter() - started


def compare_video(video: Path, root: Path) -> dict:
    legacy_result, legacy_total = _run(video, root / "legacy", "legacy")
    optimized_result, optimized_total = _run(
        video, root / "optimized", "optimized"
    )

    legacy_artifacts = legacy_result["artifacts"]
    optimized_artifacts = optimized_result["artifacts"]
    legacy_detections = _read_legacy_detections(
        Path(legacy_artifacts["annotated_video"]).parent / "labels"
    )
    optimized_detections = _read_optimized_detections(
        optimized_artifacts["detections"]
    )
    detection_comparison = _compare_detections(
        legacy_detections, optimized_detections
    )
    legacy_trajectory = _read_trajectory(legacy_artifacts["trajectory"])
    optimized_trajectory = _read_trajectory(optimized_artifacts["trajectory"])
    legacy_metrics = _read_json(legacy_artifacts["pipeline_metrics"])
    optimized_metrics = _read_json(optimized_artifacts["pipeline_metrics"])

    visible_legacy = _public_result(legacy_result)
    visible_optimized = _public_result(optimized_result)
    return {
        "video": str(video),
        "detections": detection_comparison,
        "trajectory_match": legacy_trajectory == optimized_trajectory,
        "trajectory_observations": len(legacy_trajectory),
        "pose_classification_match": (
            legacy_result["form_classification"]
            == optimized_result["form_classification"]
            and legacy_result["form_confidence"]
            == optimized_result["form_confidence"]
        ),
        "trajectory_classification_match": (
            legacy_result["trajectory_classification"]
            == optimized_result["trajectory_classification"]
            and legacy_result["trajectory_confidence"]
            == optimized_result["trajectory_confidence"]
        ),
        "final_result_match": visible_legacy == visible_optimized,
        "optimized_result": visible_optimized,
        "legacy_total_seconds": legacy_total,
        "optimized_total_seconds": optimized_total,
        "legacy_metrics": legacy_metrics,
        "optimized_metrics": optimized_metrics,
    }


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("videos", nargs="*", type=Path)
    parser.add_argument("--report", type=Path, help="Optional JSON report path")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show legacy detector and frame-rendering progress",
    )
    arguments = parser.parse_args()
    if not arguments.verbose:
        os.environ["SHARP_SHOOTER_PIPELINE_QUIET"] = "1"
    videos = [path.resolve() for path in arguments.videos]
    if not videos:
        videos = sorted((REPOSITORY_ROOT / "docs" / "demos").glob("*.mp4"))
    if not videos:
        parser.error("No sample videos were found")

    clear_detector_cache()
    comparisons = []
    warm_probe = None
    with tempfile.TemporaryDirectory(prefix="sharp-shooter-comparison-") as directory:
        root = Path(directory)
        for index, video in enumerate(videos):
            comparison = compare_video(video, root / f"video-{index}")
            comparisons.append(comparison)
            print(
                f"[{index + 1}/{len(videos)}] {video.name}: "
                f"final={comparison['final_result_match']} "
                f"detections={comparison['detections']['match']} "
                f"trajectory={comparison['trajectory_match']}",
                flush=True,
            )
            if index == 0:
                warm_result, warm_total = _run(
                    video, root / "warm-probe", "optimized"
                )
                warm_metrics = _read_json(
                    warm_result["artifacts"]["pipeline_metrics"]
                )
                warm_probe = {
                    "video": str(video),
                    "final_result_match": (
                        _public_result(warm_result)
                        == comparison["optimized_result"]
                    ),
                    "total_seconds": warm_total,
                    "metrics": warm_metrics,
                }

    final_matches = sum(item["final_result_match"] for item in comparisons)
    pose_matches = sum(item["pose_classification_match"] for item in comparisons)
    trajectory_class_matches = sum(
        item["trajectory_classification_match"] for item in comparisons
    )
    detection_matches = sum(item["detections"]["match"] for item in comparisons)
    trajectory_matches = sum(item["trajectory_match"] for item in comparisons)
    legacy_loads = [
        item["legacy_metrics"]["model_load_seconds"]
        for item in comparisons
        if item["legacy_metrics"]["model_load_seconds"] is not None
    ]
    initial_optimized = comparisons[0]["optimized_metrics"]
    report = {
        "summary": {
            "videos_tested": len(comparisons),
            "final_prediction_matches": final_matches,
            "pose_classification_matches": pose_matches,
            "trajectory_classification_matches": trajectory_class_matches,
            "detection_matches": detection_matches,
            "trajectory_matches": trajectory_matches,
        },
        "performance": {
            "legacy_average_model_load_seconds": _average(legacy_loads),
            "optimized_initial_model_load_seconds": initial_optimized[
                "model_load_seconds"
            ],
            "optimized_second_run_model_load_seconds": warm_probe["metrics"][
                "model_load_seconds"
            ],
            "legacy_average_total_seconds": _average(
                [item["legacy_total_seconds"] for item in comparisons]
            ),
            "optimized_first_total_seconds": comparisons[0][
                "optimized_total_seconds"
            ],
            "optimized_warm_total_seconds": warm_probe["total_seconds"],
            "legacy_average_peak_temp_bytes": _average(
                [item["legacy_metrics"]["peak_temp_bytes"] for item in comparisons]
            ),
            "optimized_average_peak_temp_bytes": _average(
                [
                    item["optimized_metrics"]["peak_temp_bytes"]
                    for item in comparisons
                ]
            ),
        },
        "warm_probe": warm_probe,
        "videos": comparisons,
    }
    output = json.dumps(report, indent=2, sort_keys=True)
    if arguments.report:
        arguments.report.parent.mkdir(parents=True, exist_ok=True)
        arguments.report.write_text(output + "\n", encoding="utf-8")
    print(output)

    summary = report["summary"]
    all_matched = all(
        summary[key] == summary["videos_tested"]
        for key in (
            "final_prediction_matches",
            "pose_classification_matches",
            "trajectory_classification_matches",
            "detection_matches",
            "trajectory_matches",
        )
    )
    return 0 if all_matched else 1


if __name__ == "__main__":
    raise SystemExit(main())
