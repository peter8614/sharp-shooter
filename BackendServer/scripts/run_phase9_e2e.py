"""Exercise the deployed IAM-protected Dev API with a real public demo video.

Uses Python's standard library, AWS CLI login credentials, and curl for the
presigned PUT. ``certifi`` is optional for Windows/Anaconda TLS trust. It never
prints credentials or the presigned upload URL.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

try:
    import certifi
except ImportError:
    certifi = None


def tls_context() -> ssl.SSLContext:
    # Some Windows/Anaconda installations have a malformed system cert entry.
    # Prefer their maintained CA bundle, but never disable certificate checks.
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def aws_json(*arguments: str) -> dict:
    result = subprocess.run(
        ["aws", *arguments, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _hmac(key: bytes, value: str) -> bytes:
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()


def signed_api_request(
    *, method: str, url: str, payload: dict | None, region: str, credentials: dict
) -> tuple[int, dict]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query:
        raise ValueError("The Dev API URL must be HTTPS without a query string")
    body = (
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if payload is not None
        else b""
    )
    body_hash = hashlib.sha256(body).hexdigest()
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    date = now[:8]
    headers = {
        "host": parsed.netloc,
        "x-amz-content-sha256": body_hash,
        "x-amz-date": now,
        "x-amz-security-token": credentials["SessionToken"],
    }
    if payload is not None:
        headers["content-type"] = "application/json"
    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(f"{key}:{headers[key]}\n" for key in sorted(headers))
    canonical_request = "\n".join(
        [
            method,
            quote(parsed.path or "/", safe="/-_.~"),
            "",
            canonical_headers,
            signed_headers,
            body_hash,
        ]
    )
    scope = f"{date}/{region}/execute-api/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            now,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signing_key = _hmac(
        _hmac(_hmac(_hmac(("AWS4" + credentials["SecretAccessKey"]).encode(), date), region), "execute-api"),
        "aws4_request",
    )
    signature = hmac.new(
        signing_key, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    headers["authorization"] = (
        "AWS4-HMAC-SHA256 "
        f"Credential={credentials['AccessKeyId']}/{scope},"
        f"SignedHeaders={signed_headers},Signature={signature}"
    )
    request = Request(url, data=body if payload is not None else None, method=method)
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urlopen(request, timeout=30, context=tls_context()) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def run(args: argparse.Namespace) -> dict:
    identity = aws_json("sts", "get-caller-identity", "--region", args.region)
    if identity["Account"] != args.expected_account_id:
        raise RuntimeError("AWS account does not match --expected-account-id")
    credentials = aws_json("configure", "export-credentials", "--format", "process")
    video = args.video.resolve(strict=True)
    if video.suffix.lower() != ".mp4":
        raise ValueError("Expected an MP4 demo video")
    video_hash = hashlib.sha256(video.read_bytes()).hexdigest()
    started = time.monotonic()
    code, created = signed_api_request(
        method="POST",
        url=f"{args.api_base}/jobs",
        payload={"filename": video.name, "content_type": "video/mp4"},
        region=args.region,
        credentials=credentials,
    )
    if code != 201 or created.get("status") != "pending":
        raise RuntimeError(f"POST /jobs returned {code}: {created}")
    job_id = created["job_id"]
    print(f"created job {job_id}", flush=True)
    upload_url = created["upload_url"]
    if urlparse(upload_url).scheme != "https":
        raise RuntimeError("Presigned upload URL is not HTTPS")
    # curl uses the OS TLS stack on Windows, avoiding Anaconda's large-upload
    # SSL error. Capture output so the presigned URL never enters test logs.
    upload = subprocess.run(
        [
            "curl.exe", "--fail", "--silent", "--show-error", "--request", "PUT",
            "--header", "Content-Type: video/mp4", "--data-binary", f"@{video}",
            "--write-out", "%{http_code}", "--output", os.devnull, upload_url,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if upload.returncode:
        raise RuntimeError(f"S3 presigned upload failed: {upload.stderr.strip()}")
    upload_status = int(upload.stdout)
    if upload_status != 200:
        raise RuntimeError(f"S3 upload returned {upload_status}")
    uploaded_at = time.monotonic()
    deadline = uploaded_at + args.timeout_seconds
    statuses = []
    while True:
        code, job = signed_api_request(
            method="GET",
            url=f"{args.api_base}/jobs/{job_id}",
            payload=None,
            region=args.region,
            credentials=credentials,
        )
        if code != 200:
            raise RuntimeError(f"GET /jobs returned {code}: {job}")
        status = job["status"]
        if not statuses or status != statuses[-1]:
            statuses.append(status)
            print(f"{job_id}: {status}", flush=True)
        if status in ("completed", "failed"):
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Job {job_id} remained {status} after timeout")
        time.sleep(args.poll_seconds)
    report = {
        "job_id": job_id,
        "video": video.name,
        "video_sha256": video_hash,
        "create_status": 201,
        "upload_status": upload_status,
        "status_path": statuses,
        "final_status": status,
        "upload_to_final_seconds": round(time.monotonic() - uploaded_at, 3),
        "create_to_final_seconds": round(time.monotonic() - started, 3),
    }
    if status == "completed":
        result = job.get("result", {})
        report["result"] = result
        if args.coaching_timeout_seconds > 0 and result.get("coaching_status") in ("queued", "processing"):
            coaching_deadline = time.monotonic() + args.coaching_timeout_seconds
            while time.monotonic() < coaching_deadline:
                time.sleep(args.poll_seconds)
                code, coaching_job = signed_api_request(
                    method="GET",
                    url=f"{args.api_base}/jobs/{job_id}",
                    payload=None,
                    region=args.region,
                    credentials=credentials,
                )
                if code != 200:
                    raise RuntimeError(f"Coaching poll returned HTTP {code}")
                coaching_result = coaching_job.get("result", {})
                if coaching_result.get("coaching_status") not in ("queued", "processing"):
                    report["result"] = coaching_result
                    break
            report["coaching_poll_seconds"] = round(
                time.monotonic() - uploaded_at - report["upload_to_final_seconds"], 3
            )
        if args.phase7_report:
            baseline = json.loads(args.phase7_report.read_text(encoding="utf-8"))
            matching = next(
                (entry for entry in baseline["invocations"] if entry["video"] == video.name),
                None,
            )
            if matching:
                expected = matching["expected_result"]
                report["phase7_exact_match"] = result == expected
                report["phase7_classification_match"] = all(
                    result.get(key) == expected.get(key)
                    for key in ("success", "form_classification", "trajectory_classification")
                )
    else:
        report["error"] = job.get("error")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-account-id", required=True)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--phase7-report", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=480)
    parser.add_argument("--poll-seconds", type=float, default=3)
    parser.add_argument("--coaching-timeout-seconds", type=int, default=0)
    args = parser.parse_args()
    args.api_base = args.api_base.rstrip("/")
    report = run(args)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if report["final_status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
