"""Controlled Dev-only failure, lease, and DLQ integration exercises.

The script temporarily disables the SQS event mapping so direct Lambda invokes
can test retries without waiting for the 30-minute production visibility timeout.
It restores the mapping and Lambda timeout in a finally block. Do not run it
against a queue that carries real user traffic.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from run_phase9_e2e import aws_json, signed_api_request


def aws(*arguments: str) -> dict:
    result = subprocess.run(
        ["aws", *arguments, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else {}


def mapping_state(mapping_uuid: str, region: str) -> str:
    return aws(
        "lambda", "get-event-source-mapping", "--uuid", mapping_uuid,
        "--region", region,
    )["State"]


def set_mapping(mapping_uuid: str, region: str, enabled: bool) -> None:
    aws(
        "lambda", "update-event-source-mapping", "--uuid", mapping_uuid,
        "--enabled" if enabled else "--no-enabled", "--region", region,
    )
    expected = "Enabled" if enabled else "Disabled"
    for _ in range(60):
        if mapping_state(mapping_uuid, region) == expected:
            return
        time.sleep(2)
    raise TimeoutError(f"Event mapping did not become {expected}")


def set_timeout(worker: str, region: str, timeout: int) -> None:
    aws(
        "lambda", "update-function-configuration", "--function-name", worker,
        "--timeout", str(timeout), "--region", region,
    )
    subprocess.run(
        ["aws", "lambda", "wait", "function-updated", "--function-name", worker,
         "--region", region],
        check=True,
        capture_output=True,
    )


def create_job(args: argparse.Namespace, credentials: dict, video: bytes) -> str:
    code, created = signed_api_request(
        method="POST", url=f"{args.api_base}/jobs",
        payload={"filename": "phase9-test.mp4", "content_type": "video/mp4"},
        region=args.region, credentials=credentials,
    )
    if code != 201:
        raise RuntimeError(f"POST /jobs returned {code}: {created}")
    job_id = created["job_id"]
    print(f"created {args.scenario} job {job_id}", flush=True)
    uploaded = subprocess.run(
        [
            "curl.exe", "--fail", "--silent", "--show-error", "--request", "PUT",
            "--header", "Content-Type: video/mp4", "--data-binary", "@-",
            "--write-out", "%{http_code}", "--output", os.devnull,
            created["upload_url"],
        ],
        input=video,
        capture_output=True,
        timeout=60,
    )
    if uploaded.returncode or uploaded.stdout != b"200":
        raise RuntimeError(f"S3 upload failed with status {uploaded.stdout!r}")
    return job_id


def job_item(args: argparse.Namespace, job_id: str) -> dict:
    raw = aws(
        "dynamodb", "get-item", "--table-name", args.table,
        "--key", json.dumps({"job_id": {"S": job_id}}),
        "--consistent-read", "--region", args.region,
    )["Item"]
    return {key: next(iter(value.values())) for key, value in raw.items()}


def sqs_event(args: argparse.Namespace, job_id: str, message_id: str) -> dict:
    body = {
        "Records": [{
            "eventName": "ObjectCreated:Put",
            "s3": {
                "bucket": {"name": args.bucket},
                "object": {"key": f"uploads/{job_id}/input.mp4"},
            },
        }]
    }
    return {"Records": [{"messageId": message_id, "body": json.dumps(body)}]}


def invoke_worker(args: argparse.Namespace, event: dict) -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory(prefix="phase9-invoke-") as directory:
        output = Path(directory) / "response.json"
        result = aws(
            "lambda", "invoke", "--function-name", args.worker,
            "--cli-binary-format", "raw-in-base64-out",
            "--payload", json.dumps(event, separators=(",", ":")),
            "--region", args.region, str(output),
        )
        return result, json.loads(output.read_text(encoding="utf-8"))


def public_job(args: argparse.Namespace, credentials: dict, job_id: str) -> dict:
    code, job = signed_api_request(
        method="GET", url=f"{args.api_base}/jobs/{job_id}", payload=None,
        region=args.region, credentials=credentials,
    )
    if code != 200:
        raise RuntimeError(f"GET /jobs returned {code}: {job}")
    return job


def invalid_video(args: argparse.Namespace, credentials: dict) -> dict:
    job_id = args.existing_job_id or create_job(
        args, credentials, b"This is deliberately not an MP4.\n"
    )
    initial = job_item(args, job_id)
    initial_count = int(initial["attempt_count"])
    if initial["status"] != "pending" or initial_count >= 3:
        raise AssertionError("Invalid-video job is not retryable")
    event = sqs_event(args, job_id, "phase9-invalid-video")
    attempts = []
    for number in range(initial_count + 1, 4):
        metadata, response = invoke_worker(args, event)
        item = job_item(args, job_id)
        attempts.append({
            "invocation": number,
            "function_error": metadata.get("FunctionError"),
            "batch_failures": response.get("batchItemFailures"),
            "status": item["status"],
            "attempt_count": int(item["attempt_count"]),
        })
        print(
            f"invalid attempt {number}: {item['status']}, count={item['attempt_count']}",
            flush=True,
        )
        if int(item["attempt_count"]) != number:
            raise AssertionError("Attempt count did not increment")
        if item["status"] != ("failed" if number == 3 else "pending"):
            raise AssertionError("Unexpected invalid-video job state")
    visible = public_job(args, credentials, job_id)
    if visible["status"] != "failed" or "error" not in visible:
        raise AssertionError("GET /jobs did not return a safe failure")

    # The upload did not enqueue a notification while S3 notifications were
    # paused. Enqueue it now, after the mapping pollers have fully stopped.
    aws(
        "sqs", "send-message", "--queue-url", args.queue,
        "--message-body", event["Records"][0]["body"], "--region", args.region,
    )
    # Accelerate receipt counts manually while the event mapping is disabled.
    # This tests the *deployed queue's* redrive policy without waiting 2 hours.
    receives = []
    for _ in range(10):
        messages = aws(
            "sqs", "receive-message", "--queue-url", args.queue,
            "--max-number-of-messages", "1", "--visibility-timeout", "0",
            "--wait-time-seconds", "2", "--attribute-names", "ApproximateReceiveCount",
            "--region", args.region,
        ).get("Messages", [])
        if messages:
            body = messages[0]["Body"]
            if job_id not in body:
                raise AssertionError("Unexpected message in Dev source queue")
            receives.append(int(messages[0]["Attributes"]["ApproximateReceiveCount"]))
        dlq_messages = aws(
            "sqs", "receive-message", "--queue-url", args.dlq,
            "--max-number-of-messages", "1", "--visibility-timeout", "0",
            "--wait-time-seconds", "1", "--region", args.region,
        ).get("Messages", [])
        if dlq_messages and job_id in dlq_messages[0]["Body"]:
            break
        time.sleep(1)
    else:
        raise AssertionError("Invalid-video notification did not reach the DLQ")
    return {
        "job_id": job_id,
        "initial_attempt_count": initial_count,
        "attempts": attempts,
        "public_failure": visible["error"],
        "manual_receive_counts": receives,
        "dlq_contains_job": True,
        "redrive_accelerated_by_manual_receives": True,
    }


def timeout_recovery(args: argparse.Namespace, credentials: dict, original_timeout: int) -> dict:
    video = args.video.read_bytes()
    job_id = create_job(args, credentials, video)
    time.sleep(2)
    initial = job_item(args, job_id)
    if initial["status"] != "pending" or int(initial["attempt_count"]) != 0:
        raise AssertionError("S3 notification pause did not isolate timeout test")
    event = sqs_event(args, job_id, "phase9-timeout-recovery")
    set_timeout(args.worker, args.region, 10)
    first_metadata, first_response = invoke_worker(args, event)
    timed_out = job_item(args, job_id)
    if timed_out["status"] != "processing" or int(timed_out["attempt_count"]) != 1:
        raise AssertionError("Timed-out worker did not leave an owned processing lease")
    old_token = timed_out["worker_token"]
    set_timeout(args.worker, args.region, original_timeout)
    active_metadata, active_response = invoke_worker(args, event)
    active = job_item(args, job_id)
    if active["status"] != "processing" or int(active["attempt_count"]) != 1:
        raise AssertionError("Active lease allowed duplicate inference")

    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")
    aws(
        "dynamodb", "update-item", "--table-name", args.table,
        "--key", json.dumps({"job_id": {"S": job_id}}),
        "--update-expression", "SET lease_expires_at = :expired",
        "--condition-expression", "#s = :processing AND worker_token = :old",
        "--expression-attribute-names", json.dumps({"#s": "status"}),
        "--expression-attribute-values", json.dumps({
            ":expired": {"S": expired_at},
            ":processing": {"S": "processing"},
            ":old": {"S": old_token},
        }),
        "--region", args.region,
    )
    retry_metadata, retry_response = invoke_worker(args, event)
    # An S3 notification already in flight may win the expired lease before
    # this direct invoke does. Either worker is a valid reclaimer; wait for the
    # final owner to finish instead of assuming the direct invoke won.
    for _ in range(45):
        completed = job_item(args, job_id)
        if completed["status"] in ("completed", "failed"):
            break
        time.sleep(3)
    visible = public_job(args, credentials, job_id)
    if completed["status"] != "completed" or int(completed["attempt_count"]) != 2:
        raise AssertionError("Expired lease was not reclaimed and completed")
    if "worker_token" in completed or visible["status"] != "completed":
        raise AssertionError("New worker did not finalize the job")
    return {
        "job_id": job_id,
        "timeout_function_error": first_metadata.get("FunctionError"),
        "timeout_response_type": first_response.get("errorType"),
        "processing_after_timeout": timed_out["status"],
        "active_lease_batch_failures": active_response.get("batchItemFailures"),
        "active_lease_attempt_count": int(active["attempt_count"]),
        "lease_expiry_accelerated_for_test": True,
        "retry_function_error": retry_metadata.get("FunctionError"),
        "retry_batch_failures": retry_response.get("batchItemFailures"),
        "concurrent_reclaimer_possible": bool(retry_response.get("batchItemFailures")),
        "final_status": completed["status"],
        "final_attempt_count": int(completed["attempt_count"]),
        "old_worker_token_cleared": "worker_token" not in completed,
        "result_classifications": {
            key: visible["result"].get(key)
            for key in ("form_classification", "trajectory_classification")
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=("invalid", "timeout"))
    parser.add_argument("--expected-account-id", required=True)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--queue", required=True)
    parser.add_argument("--dlq", required=True)
    parser.add_argument("--table", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--existing-job-id")
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()
    args.api_base = args.api_base.rstrip("/")
    if args.scenario == "timeout" and args.video is None:
        parser.error("timeout scenario requires --video")
    expected_prefix = f"https://sqs.{args.region}.amazonaws.com/{args.expected_account_id}"
    if (
        args.bucket != f"sharp-shooter-dev-uploads-{args.expected_account_id}-{args.region}"
        or args.queue != f"{expected_prefix}/sharp-shooter-dev-inference"
        or args.dlq != f"{expected_prefix}/sharp-shooter-dev-inference-dlq"
        or args.table != "sharp-shooter-dev-jobs"
        or args.worker != "sharp-shooter-dev-inference"
    ):
        raise RuntimeError("Recovery exercises are restricted to the named Dev resources")
    identity = aws_json("sts", "get-caller-identity", "--region", args.region)
    if identity["Account"] != args.expected_account_id:
        raise RuntimeError("AWS account does not match --expected-account-id")
    mappings = aws(
        "lambda", "list-event-source-mappings", "--function-name", args.worker,
        "--region", args.region,
    )["EventSourceMappings"]
    matches = [item for item in mappings if item["EventSourceArn"].endswith(":sharp-shooter-dev-inference")]
    if len(matches) != 1 or matches[0]["State"] != "Enabled":
        raise RuntimeError("Expected exactly one enabled Dev SQS event mapping")
    mapping_uuid = matches[0]["UUID"]
    original_timeout = int(aws(
        "lambda", "get-function-configuration", "--function-name", args.worker,
        "--region", args.region,
    )["Timeout"])
    credentials = aws_json("configure", "export-credentials", "--format", "process")
    notification = aws(
        "s3api", "get-bucket-notification-configuration", "--bucket", args.bucket,
        "--region", args.region,
    )
    if (
        len(notification.get("QueueConfigurations", [])) != 1
        or notification["QueueConfigurations"][0]["QueueArn"]
        != f"arn:aws:sqs:{args.region}:{args.expected_account_id}:sharp-shooter-dev-inference"
    ):
        raise RuntimeError("Expected exactly one Dev S3 queue notification")
    notification_may_have_changed = False
    try:
        notification_may_have_changed = True
        aws(
            "s3api", "put-bucket-notification-configuration", "--bucket", args.bucket,
            "--notification-configuration", "{}", "--region", args.region,
        )
        if aws(
            "s3api", "get-bucket-notification-configuration", "--bucket", args.bucket,
            "--region", args.region,
        ).get("QueueConfigurations"):
            raise RuntimeError("S3 notification pause did not take effect")
        if args.scenario == "invalid":
            set_mapping(mapping_uuid, args.region, False)
            # State=Disabled can precede shutdown of existing long pollers.
            time.sleep(120)
            report = invalid_video(args, credentials)
        else:
            # S3 notification changes also take time to propagate.
            time.sleep(120)
            report = timeout_recovery(args, credentials, original_timeout)
    finally:
        try:
            current_timeout = int(aws(
                "lambda", "get-function-configuration", "--function-name", args.worker,
                "--region", args.region,
            )["Timeout"])
            if current_timeout != original_timeout:
                set_timeout(args.worker, args.region, original_timeout)
        finally:
            try:
                if notification_may_have_changed:
                    aws(
                        "s3api", "put-bucket-notification-configuration",
                        "--bucket", args.bucket,
                        "--notification-configuration", json.dumps(notification),
                        "--region", args.region,
                    )
            finally:
                if mapping_state(mapping_uuid, args.region) != "Enabled":
                    set_mapping(mapping_uuid, args.region, True)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
