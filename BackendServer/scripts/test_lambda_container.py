"""Run real videos through a local Lambda image and verify Phase 5.5 parity."""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from core.inference import predict_video  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _invoke(endpoint: str, video_path: str, timeout: int, pipeline: str = "optimized") -> dict:
    request = Request(
        endpoint,
        data=json.dumps({"video_path": video_path, "pipeline": pipeline}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(20):
        try:
            started = time.perf_counter()
            with urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            runtime = payload.get("runtime")
            if isinstance(runtime, dict):
                runtime["client_roundtrip_seconds"] = round(
                    time.perf_counter() - started, 6
                )
            return payload
        except (URLError, ConnectionError, socket.timeout) as error:
            last_error = error
            if attempt == 19:
                break
            time.sleep(1)
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Lambda invocation failed ({error.code}): {body}") from error
    raise RuntimeError(f"Lambda Runtime Interface Emulator is unavailable: {last_error}")


def _public_result(result: dict) -> dict:
    clean = dict(result)
    clean.pop("artifacts", None)
    return clean


def _semantic_result(result: dict) -> dict:
    """Compare user-facing decisions while retaining numeric drift in the report."""
    clean = json.loads(json.dumps(result))
    clean.pop("form_confidence", None)
    clean.pop("trajectory_confidence", None)
    for label in clean.get("coaching_labels", []):
        label.pop("confidence", None)
    metrics = clean.get("metrics", {})
    metrics.pop("shot_frames", None)
    metrics.pop("release_frames", None)
    return clean


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--endpoint",
        default="http://localhost:9000/2015-03-31/functions/function/invocations",
    )
    parser.add_argument(
        "--host-video-root",
        type=Path,
        default=REPOSITORY_ROOT / "docs" / "demos",
    )
    parser.add_argument("--container-video-root", default="/tmp/videos")
    parser.add_argument(
        "--report",
        type=Path,
        default=BACKEND_ROOT / "reports" / "phase-7-container-validation.json",
    )
    parser.add_argument(
        "--markdown-report",
        type=Path,
        default=BACKEND_ROOT / "reports" / "phase-7-container-validation.md",
    )
    parser.add_argument("--image-size-bytes", type=int, required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--image-platform", required=True)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--video", action="append", help="Limit a diagnostic run to selected filenames")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    videos = sorted(args.host_video_root.resolve().glob("*.mp4"))
    if args.video:
        videos = [video for video in videos if video.name in set(args.video)]
    if not videos:
        raise SystemExit("No demo videos were found")

    failures: list[str] = []
    compatibility_notes: list[str] = []
    invocations: list[dict] = []
    baselines: dict[str, dict] = {}
    for video in videos:
        baseline = _public_result(predict_video(video, pipeline="optimized"))
        baselines[video.name] = baseline
        container_path = f"{args.container_video_root.rstrip('/')}/{video.name}"
        response = _invoke(args.endpoint, container_path, args.timeout)
        matches = response.get("result") == baseline
        semantic_match = _semantic_result(response.get("result", {})) == _semantic_result(baseline)
        if not matches:
            compatibility_notes.append(f"Windows/Linux numeric difference: {video.name}")
        if not semantic_match:
            failures.append(f"Cross-platform prediction decisions differ: {video.name}")
        legacy_response = _invoke(args.endpoint, container_path, args.timeout, "legacy")
        linux_parity = legacy_response.get("result") == response.get("result")
        if not linux_parity:
            failures.append(f"Linux Phase 5.5 legacy/optimized mismatch: {video.name}")
        record = {
                "video": video.name,
                "video_sha256": _sha256(video),
                "prediction_matches_windows_phase_5_5_exactly": matches,
                "cross_platform_semantic_match": semantic_match,
                "linux_legacy_matches_optimized_exactly": linux_parity,
                "runtime": response.get("runtime"),
                "legacy_runtime": legacy_response.get("runtime"),
            }
        if not matches:
            record["expected_result"] = baseline
            record["actual_result"] = response.get("result")
        if not linux_parity:
            record["linux_legacy_result"] = legacy_response.get("result")
        invocations.append(record)

    warm_video = videos[0]
    warm_response = _invoke(
        args.endpoint,
        f"{args.container_video_root.rstrip('/')}/{warm_video.name}",
        args.timeout,
    )
    warm_runtime = warm_response.get("runtime", {})
    warm_reused = warm_runtime.get("model_reused") is True
    if not warm_reused:
        failures.append("YOLO detector was not reused by a warm invocation")
    if warm_runtime.get("cold_start") is not False:
        failures.append("Repeated invocation was incorrectly marked as cold")
    warm_matches = warm_response.get("result") == baselines[warm_video.name]
    if not warm_matches:
        compatibility_notes.append(f"Windows/Linux numeric difference on warm run: {warm_video.name}")
    warm_semantic_match = _semantic_result(warm_response.get("result", {})) == _semantic_result(baselines[warm_video.name])
    if not warm_semantic_match:
        failures.append(f"Warm prediction decisions differ: {warm_video.name}")
    cold_result = invocations[0].get("actual_result")
    if cold_result is None:
        cold_result = baselines[warm_video.name]
    warm_repeat_matches = warm_response.get("result") == cold_result
    if not warm_repeat_matches:
        failures.append(f"Linux cold/warm result mismatch: {warm_video.name}")
    warm_record = {
            "video": warm_video.name,
            "purpose": "warm-runtime-reuse",
            "prediction_matches_windows_phase_5_5_exactly": warm_matches,
            "cross_platform_semantic_match": warm_semantic_match,
            "linux_cold_warm_result_match": warm_repeat_matches,
            "runtime": warm_runtime,
        }
    if not warm_matches:
        warm_record["expected_result"] = baselines[warm_video.name]
        warm_record["actual_result"] = warm_response.get("result")
    invocations.append(warm_record)

    report = {
        "phase": 7,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "image": {
            "id": args.image_id,
            "platform": args.image_platform,
            "size_bytes": args.image_size_bytes,
            "size_mib": round(args.image_size_bytes / (1024 * 1024), 2),
        },
        "videos": len(videos),
        "warm_model_reuse_verified": warm_reused,
        "cross_platform_exact_matches": sum(
            item["prediction_matches_windows_phase_5_5_exactly"]
            for item in invocations
        ),
        "invocations": invocations,
        "compatibility_notes": compatibility_notes,
        "failures": failures,
        "passed": not failures,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    rows = []
    for invocation in invocations:
        runtime = invocation.get("runtime") or {}
        rows.append(
            "| {video} | {purpose} | {elapsed} | {rss} | {temporary} | {reused} | {linux_parity} | {semantic} | {exact} |".format(
                video=invocation["video"],
                purpose=invocation.get("purpose", "parity"),
                elapsed=runtime.get("elapsed_seconds", "n/a"),
                rss=(
                    round(runtime["peak_rss_bytes"] / (1024 * 1024), 2)
                    if runtime.get("peak_rss_bytes") is not None
                    else "n/a"
                ),
                temporary=round(
                    runtime.get("temporary_job_bytes", 0) / (1024 * 1024), 2
                ),
                reused=runtime.get("model_reused", False),
                linux_parity=invocation.get("linux_legacy_matches_optimized_exactly", invocation.get("linux_cold_warm_result_match", "n/a")),
                semantic=invocation["cross_platform_semantic_match"],
                exact=invocation["prediction_matches_windows_phase_5_5_exactly"],
            )
        )
    markdown = "\n".join(
        [
            "# Phase 7 Lambda container validation",
            "",
            f"Generated: {report['generated_at']}",
            "",
            f"- Result: {'PASS' if report['passed'] else 'FAIL'}",
            f"- Image: `{report['image']['id']}`",
            f"- Platform: `{report['image']['platform']}`",
            f"- Image size: {report['image']['size_mib']} MiB",
            f"- Warm YOLO reuse: {report['warm_model_reuse_verified']}",
            "",
            "| Video | Purpose | Inference seconds | Peak RSS MiB | Job /tmp MiB | YOLO reused | Linux exact parity | Cross-platform decisions | Windows exact parity |",
            "| --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |",
            *rows,
            "",
            "## Cross-platform compatibility notes",
            "",
            *(compatibility_notes or ["None."]),
            "",
            "## Failures",
            "",
            *(failures or ["None."]),
            "",
        ]
    )
    args.markdown_report.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_report.write_text(markdown, encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": report["passed"],
                "image": report["image"],
                "videos": report["videos"],
                "warm_model_reuse_verified": report["warm_model_reuse_verified"],
                "cross_platform_exact_matches": report["cross_platform_exact_matches"],
                "compatibility_notes": compatibility_notes,
                "failures": failures,
                "report": str(args.report),
            },
            indent=2,
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
