"""Account-data deletion independent of Flask and Firebase initialization."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


FIRESTORE_BATCH_SIZE = 400


def _chunks(items: Iterable[Any], size: int):
    chunk = []
    for item in items:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def delete_account_data(
    user_id: str, *, firestore_client, storage_bucket, auth_client
) -> dict:
    """Delete one user's analysis data, storage objects, and auth identity.

    Authentication is deleted last. If an earlier service fails, the identity
    remains available so the authenticated caller can safely retry. Every
    operation is idempotent, which also makes partial-failure recovery safe.
    """
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("A user ID is required")

    user_reference = firestore_client.collection("users").document(user_id)
    analysis_documents = user_reference.collection("analysis").stream()
    deleted_documents = 0
    for documents in _chunks(analysis_documents, FIRESTORE_BATCH_SIZE):
        batch = firestore_client.batch()
        for document in documents:
            batch.delete(document.reference)
        batch.commit()
        deleted_documents += len(documents)

    user_reference.delete()

    deleted_objects = 0
    for blob in storage_bucket.list_blobs(prefix=f"{user_id}/"):
        blob.delete()
        deleted_objects += 1

    auth_client.delete_user(user_id)
    return {
        "analysis_documents": deleted_documents,
        "storage_objects": deleted_objects,
    }
