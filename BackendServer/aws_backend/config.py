"""Environment-backed configuration for the AWS job backend."""

from __future__ import annotations

import os


SUPPORTED_VIDEO_TYPES = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/x-matroska": ".mkv",
}


def required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable is not set: {name}")
    return value


def aws_region() -> str:
    return required_environment("AWS_REGION")


def upload_bucket() -> str:
    return required_environment("UPLOAD_BUCKET")


def jobs_table() -> str:
    return required_environment("JOBS_TABLE")


def _positive_integer_environment(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive integer") from error
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def processing_lease_seconds() -> int:
    return _positive_integer_environment("PROCESSING_LEASE_SECONDS", 960)


def max_processing_attempts() -> int:
    return _positive_integer_environment("MAX_PROCESSING_ATTEMPTS", 3)
