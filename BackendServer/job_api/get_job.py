"""GET /jobs/{job_id} handler."""

from __future__ import annotations

import logging

from aws_backend import job_store

from .common import app_subject, json_response


logger = logging.getLogger(__name__)


def public_job(job: dict) -> dict:
    response = {
        "job_id": job["job_id"],
        "status": job["status"],
    }
    if job["status"] == job_store.COMPLETED:
        result = dict(job["result"])
        result.pop("coaching_summary", None)
        processed_key = result.pop("processed_video_key", None)
        reference_key = result.pop("player_video_key", None)
        if processed_key:
            result["processed_video_available"] = True
        if reference_key:
            result["reference_video_available"] = True
        response["result"] = result
    elif job["status"] == job_store.FAILED:
        response["error"] = job.get("error", job_store.SAFE_PROCESSING_ERROR)
    return response


def get_job(job_id: str, *, owner_sub: str | None = None) -> dict | None:
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("job_id is required.")
    job = job_store.get_job(job_id)
    if job is not None and owner_sub is not None and job.get("owner_sub") != owner_sub:
        return None
    return public_job(job) if job is not None else None


def lambda_handler(event, _context):
    if (event or {}).get("routeKey") == "GET /app/jobs/{job_id}/videos/{video_kind}":
        from .get_video import lambda_handler as get_video_handler

        return get_video_handler(event, _context)
    try:
        owner_sub = app_subject(event or {}, "GET /app/jobs/{job_id}")
        path_parameters = (event or {}).get("pathParameters") or {}
        job = get_job(path_parameters.get("job_id"), owner_sub=owner_sub)
        if job is None:
            return json_response(404, {"error": "Job not found."})
        return json_response(200, job)
    except PermissionError:
        return json_response(401, {"error": "Unauthorized."})
    except ValueError:
        return json_response(400, {"error": "Invalid job ID."})
    except Exception:
        logger.exception("Unable to read inference job")
        return json_response(500, {"error": "Unable to read job."})
