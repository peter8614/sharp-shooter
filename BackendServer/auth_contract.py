"""Pure adapters between Firebase response shapes and the mobile API contract."""

from __future__ import annotations


def _required_text(payload: dict, field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Firebase response is missing {field}")
    return value


def sign_in_session_payload(payload: dict) -> dict:
    """Adapt Identity Toolkit's camel-case session response."""
    return {
        "idToken": _required_text(payload, "idToken"),
        "user_id": _required_text(payload, "localId"),
        "refreshToken": payload.get("refreshToken"),
        "expiresIn": payload.get("expiresIn"),
    }


def refreshed_session_payload(payload: dict, previous_refresh_token: str) -> dict:
    """Adapt Secure Token's snake-case response to the stable mobile contract."""
    return {
        "idToken": _required_text(payload, "id_token"),
        "user_id": _required_text(payload, "user_id"),
        "refreshToken": payload.get("refresh_token") or previous_refresh_token,
        "expiresIn": payload.get("expires_in"),
    }
