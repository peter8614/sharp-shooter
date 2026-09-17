"""POST /jobs handler."""

from __future__ import annotations

import logging
import uuid

from aws_backend import job_store, s3_service
from aws_backend.config import SUPPORTED_VIDEO_TYPES, upload_bucket

from .common import json_response, parse_json_body


logger = logging.getLogger(__name__)


class UnsupportedContentTypeError(ValueError):
    """Raised when an upload MIME type is outside the video allowlist."""


def create_job(payload: dict, *, bucket: str | None = None) -> dict:
    filename = payload.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("filename is required.")

    supplied_content_type = payload.get("content_type")
    if not isinstance(supplied_content_type, str):
        raise ValueError("content_type is required.")
    content_type = supplied_content_type.split(";", 1)[0].strip().lower()
    extension = SUPPORTED_VIDEO_TYPES.get(content_type)
    if extension is None:
        raise UnsupportedContentTypeError("Unsupported video content type.")

    job_id = str(uuid.uuid4())
    resolved_bucket = bucket or upload_bucket()
    key = f"uploads/{job_id}/input{extension}"
    upload_url = s3_service.generate_upload_url(
        bucket=resolved_bucket,
        key=key,
        content_type=content_type,
    )
    # Presigning is local. Generate first so a signing/configuration failure does
    # not leave behind a pending job that can never receive its upload.
    job_store.create_job(
        job_id=job_id,
        s3_bucket=resolved_bucket,
        s3_key=key,
    )
    return {
        "job_id": job_id,
        "upload_url": upload_url,
        "status": job_store.PENDING,
    }


def lambda_handler(event, _context):
    try:
        payload = parse_json_body(event or {})
        return json_response(201, create_job(payload))
    except UnsupportedContentTypeError:
        return json_response(415, {"error": "Unsupported video content type."})
    except (ValueError, UnicodeDecodeError):
        return json_response(400, {"error": "Invalid job request."})
    except Exception:
        logger.exception("Unable to create inference job")
        return json_response(500, {"error": "Unable to create job."})
