"""Issue short-lived video links only after JWT ownership verification."""

from __future__ import annotations

import logging
import re

from aws_backend import job_store, s3_service
from aws_backend.config import upload_bucket

from .common import app_subject, json_response


logger = logging.getLogger(__name__)
_ROUTE = "GET /app/jobs/{job_id}/videos/{video_kind}"
_REFERENCE_KEY = re.compile(r"^references/videos/[a-z0-9-]{1,80}\.mp4$")


def video_link(job_id: str, video_kind: str, owner_sub: str) -> str | None:
    if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,80}", job_id):
        raise ValueError("Invalid job ID")
    if video_kind not in ("processed", "reference"):
        raise ValueError("Invalid video kind")
    job = job_store.get_job(job_id)
    if job is None or job.get("owner_sub") != owner_sub:
        return None
    if job.get("status") != job_store.COMPLETED:
        return None
    result = job.get("result") or {}
    key = result.get(
        "processed_video_key" if video_kind == "processed" else "player_video_key"
    )
    if not isinstance(key, str):
        return None
    if video_kind == "processed":
        if not re.fullmatch(rf"results/{re.escape(job_id)}/[0-9a-f]{{32}}\.mp4", key):
            raise ValueError("Invalid processed video key")
    elif not _REFERENCE_KEY.fullmatch(key):
        raise ValueError("Invalid reference video key")
    return s3_service.generate_download_url(bucket=upload_bucket(), key=key)


def lambda_handler(event, _context):
    try:
        owner_sub = app_subject(event or {}, _ROUTE)
        if owner_sub is None:
            raise PermissionError("Unauthorized")
        params = (event or {}).get("pathParameters") or {}
        url = video_link(params.get("job_id"), params.get("video_kind"), owner_sub)
        if url is None:
            return json_response(404, {"error": "Video not found."})
        return json_response(200, {"video_url": url, "expires_in": 300})
    except PermissionError:
        return json_response(401, {"error": "Unauthorized."})
    except ValueError:
        return json_response(400, {"error": "Invalid video request."})
    except Exception:
        logger.exception("Unable to sign video download")
        return json_response(500, {"error": "Unable to load video."})
