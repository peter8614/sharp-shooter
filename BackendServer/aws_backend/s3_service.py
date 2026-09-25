"""Reusable S3 operations for direct uploads and worker downloads."""

from __future__ import annotations

from pathlib import Path

from .config import aws_region

try:
    import boto3
except ImportError:  # Allows mock-only unit tests without installing the AWS SDK.
    boto3 = None


_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        if boto3 is None:
            raise RuntimeError("boto3 is required for S3 operations")
        _s3_client = boto3.client("s3", region_name=aws_region())
    return _s3_client


def generate_upload_url(
    *,
    bucket: str,
    key: str,
    content_type: str,
    expires_in: int = 900,
    client=None,
) -> str:
    return (client or _get_s3_client()).generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expires_in,
    )


def download_video(
    *, bucket: str, key: str, destination: str | Path, client=None
) -> Path:
    resolved_destination = Path(destination)
    resolved_destination.parent.mkdir(parents=True, exist_ok=True)
    (client or _get_s3_client()).download_file(
        bucket,
        key,
        str(resolved_destination),
    )
    return resolved_destination


def upload_processed_video(
    *, bucket: str, key: str, source: str | Path, client=None
) -> None:
    if not key.startswith("results/") or not key.endswith(".mp4"):
        raise ValueError("Invalid processed video key")
    (client or _get_s3_client()).upload_file(
        str(source),
        bucket,
        key,
        ExtraArgs={"ContentType": "video/mp4", "ServerSideEncryption": "AES256"},
    )


def generate_download_url(
    *, bucket: str, key: str, expires_in: int = 300, client=None
) -> str:
    if expires_in < 1 or expires_in > 900:
        raise ValueError("Invalid download URL lifetime")
    return (client or _get_s3_client()).generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )
