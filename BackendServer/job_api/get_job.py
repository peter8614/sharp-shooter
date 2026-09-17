"""GET /jobs/{job_id} handler."""

from __future__ import annotations

import logging

from aws_backend import job_store

from .common import json_response


logger = logging.getLogger(__name__)


def public_job(job: dict) -> dict:
    response = {
        "job_id": job["job_id"],
        "status": job["status"],
    }
    if job["status"] == job_store.COMPLETED:
        response["result"] = job["result"]
    elif job["status"] == job_store.FAILED:
        response["error"] = job.get("error", job_store.SAFE_PROCESSING_ERROR)
    return response


def get_job(job_id: str) -> dict | None:
    if not isinstance(job_id, str) or not job_id.strip():
        raise ValueError("job_id is required.")
    job = job_store.get_job(job_id)
    return public_job(job) if job is not None else None


def lambda_handler(event, _context):
    try:
        path_parameters = (event or {}).get("pathParameters") or {}
        job = get_job(path_parameters.get("job_id"))
        if job is None:
            return json_response(404, {"error": "Job not found."})
        return json_response(200, job)
    except ValueError:
        return json_response(400, {"error": "Invalid job ID."})
    except Exception:
        logger.exception("Unable to read inference job")
        return json_response(500, {"error": "Unable to read job."})
