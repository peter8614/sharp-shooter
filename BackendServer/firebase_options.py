"""Firebase authentication, Firestore, and Storage helpers.

Credentials are loaded from the environment instead of repository files. In
production, prefer the platform's application-default identity or a secret manager.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path

import firebase_admin
import requests
from firebase_admin import auth, credentials, firestore, storage
from dotenv import load_dotenv


# Loading a local ignored .env is convenient for development; production
# environments should inject the same values through a secret manager.
load_dotenv(Path(__file__).resolve().parent / ".env")


def _initialize_firebase() -> None:
    """Initialize Firebase once using application-default credentials."""
    if firebase_admin._apps:
        return

    bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET")
    if not bucket_name:
        raise RuntimeError("FIREBASE_STORAGE_BUCKET is required")

    credential_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if credential_path:
        path = Path(credential_path).expanduser()
        if not path.is_file():
            raise RuntimeError(f"Firebase credential file does not exist: {path}")
        firebase_credential = credentials.Certificate(path)
    else:
        # Cloud runtimes can provide a service identity without a JSON key file.
        firebase_credential = credentials.ApplicationDefault()

    firebase_admin.initialize_app(
        firebase_credential,
        {"storageBucket": bucket_name},
    )


_initialize_firebase()
db = firestore.client()
bucket = storage.bucket()


def save_to_firestore(
    user_id,
    landmark_path,
    trajectory_path,
    form_classification,
    trajectory_classification,
    processed_video,
    player_name=None,
    similarity_percent=None,
    player_recording_path=None,
    form_confidence=None,
    trajectory_confidence=None,
    coaching_labels=None,
):
    """Create and return one analysis document for an authenticated user."""
    doc_ref = db.collection("users").document(user_id).collection("analysis").document()
    doc_ref.set(
        {
            "form_classification": form_classification,
            "trajectory_classification": trajectory_classification,
            "landmark_file": landmark_path,
            "trajectory_file": trajectory_path,
            "processed_video": processed_video,
            "timestamp": firestore.SERVER_TIMESTAMP,
            "player_name": player_name,
            "similarity_percentage": similarity_percent,
            "player_recording_path": player_recording_path,
            "form_confidence": form_confidence,
            "trajectory_confidence": trajectory_confidence,
            # Labels contain aggregate evidence and controlled text only; raw
            # pose frames remain in the user's private storage artifact.
            "coaching_labels": coaching_labels or [],
        }
    )
    return doc_ref.id


def update_document(
    collection_name,
    document_name,
    sub_collection_name,
    analysis_id,
    field_name,
    field_value,
):
    """Update one field in an existing nested Firestore document."""
    document_reference = (
        db.collection(collection_name)
        .document(document_name)
        .collection(sub_collection_name)
        .document(analysis_id)
    )
    document_reference.set({field_name: field_value}, merge=True)


def get_analysis_by_id(collection_name, user_id, analysis_id):
    """Return one analysis owned by the supplied, already-authenticated UID."""
    document = (
        db.collection(collection_name)
        .document(user_id)
        .collection("analysis")
        .document(analysis_id)
        .get()
    )
    return document.to_dict() if document.exists else None


def save_analysis_by_id(user_id, analysis_id, llm_analysis):
    """Persist generated coaching feedback without replacing other fields."""
    document = db.collection("users").document(user_id).collection("analysis").document(analysis_id)
    document.set({"llm_analysis": llm_analysis}, merge=True)


def register_or_login(email, password, is_registering=False):
    """Call Firebase Identity Toolkit and return a JSON-ready payload and status."""
    api_key = os.getenv("FIREBASE_WEB_API_KEY")
    if not api_key:
        raise RuntimeError("FIREBASE_WEB_API_KEY is required")

    action = "signUp" if is_registering else "signInWithPassword"
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:{action}?key={api_key}"
    response = requests.post(
        url,
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=15,
    )
    payload = response.json()
    if response.ok:
        return {
            "idToken": payload.get("idToken"),
            "user_id": payload.get("localId"),
        }, 200

    # Avoid returning the full upstream response, which may contain internal details.
    message = payload.get("error", {}).get("message", "Authentication failed")
    return {"error": message}, 400


def verify_user_token(token):
    """Verify a Firebase ID token and return its authenticated UID."""
    if not token:
        raise ValueError("A Firebase ID token is required")
    return auth.verify_id_token(token)["uid"]


def save_to_firebase_storage(user_id, folder, filename, local_file_path):
    """Upload one generated artifact below the authenticated user's prefix."""
    storage_path = f"{user_id}/{folder}/{filename}"
    bucket.blob(storage_path).upload_from_filename(local_file_path)
    return storage_path


def grab_file_from_storage(blob_path):
    """Download a Storage object as bytes."""
    blob = bucket.blob(blob_path)
    if not blob.exists():
        raise FileNotFoundError("File not found in Firebase Storage")
    return blob.download_as_bytes()


def generate_signed_url(blob_path, days=1):
    """Generate a short-lived URL for an existing Storage object."""
    blob = bucket.blob(blob_path)
    if not blob.exists():
        raise FileNotFoundError("File not found in Firebase Storage")
    return blob.generate_signed_url(expiration=datetime.timedelta(days=days))
