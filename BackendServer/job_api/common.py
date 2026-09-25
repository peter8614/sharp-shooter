"""Shared API Gateway response helpers."""

from __future__ import annotations

import base64
import json


def json_response(status_code: int, payload: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload, separators=(",", ":")),
    }


def parse_json_body(event: dict) -> dict:
    body = event.get("body")
    if isinstance(body, dict):
        return body
    if not isinstance(body, str) or not body.strip():
        raise ValueError("A JSON request body is required.")
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body, validate=True).decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("The JSON request body must be an object.")
    return parsed


def app_subject(event: dict, route_key: str) -> str | None:
    """Return the trusted JWT subject for an App route; IAM routes stay separate."""
    if event.get("routeKey") != route_key:
        return None
    claims = (
        ((event.get("requestContext") or {}).get("authorizer") or {})
        .get("jwt", {})
        .get("claims", {})
    )
    subject = claims.get("sub") if isinstance(claims, dict) else None
    if not isinstance(subject, str) or not subject.strip():
        raise PermissionError("Missing authenticated user")
    return subject
