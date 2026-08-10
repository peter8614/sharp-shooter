"""Authenticated HTTP API for asynchronous shooting-video analysis."""

from __future__ import annotations

import datetime
import hashlib
import hmac
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from pathlib import Path

import cv2
from flask import Flask, g, jsonify, request
from werkzeug.utils import secure_filename

from firebase_options import (
    db,
    generate_signed_url,
    get_analysis_by_id,
    grab_file_from_storage,
    register_or_login,
    save_analysis_by_id,
    save_to_firebase_storage,
    save_to_firestore,
    update_document,
    verify_user_token,
)
from landmark_classification import landmark_predict, load_landmark_model, load_single_landmark_file
from llm_analysis import create_llm_analysis
from main import break_down_video
from NBA_compare import compare_user_to_player
from trajectory_classification import load_trajectory, load_trajectory_model, trajectory_predict


BACKEND_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = BACKEND_DIR / "uploads"
WORK_ROOT = BACKEND_DIR / "server_data"
LANDMARK_MODEL = BACKEND_DIR / "data/landmark_data/basketball_shot_model.pkl"
TRAJECTORY_MODEL = BACKEND_DIR / "data/trajectory_data/trajectory_model.pkl"
NBA_DATA_DIR = BACKEND_DIR / "NBA Data"
NBA_VIDEO_DIR = BACKEND_DIR / "NBA Players"
ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv"}
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)))

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
server = Flask(__name__)
server.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
WORK_ROOT.mkdir(parents=True, exist_ok=True)

# A bounded pool prevents an upload burst from creating unlimited OS threads.
executor = ThreadPoolExecutor(max_workers=int(os.getenv("ANALYSIS_WORKERS", "2")))
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()
llm_last_request: dict[str, float] = {}


def _set_job(job_id: str, **updates) -> None:
    """Update one in-memory job record atomically."""
    with jobs_lock:
        jobs[job_id].update(updates)


def _prune_completed_jobs(now: float) -> None:
    """Bound memory use by dropping terminal job metadata after 24 hours."""
    expiration = now - 24 * 60 * 60
    expired_ids = [
        job_id
        for job_id, job in jobs.items()
        if job["created_at"] < expiration and job["status"] in {"complete", "failed"}
    ]
    for job_id in expired_ids:
        jobs.pop(job_id, None)


def _error(message: str, status: int):
    """Return a consistent JSON error without exposing a stack trace."""
    return jsonify({"error": message}), status


def require_auth(view):
    """Verify a Firebase bearer token and expose only its trusted UID."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return _error("A bearer token is required", 401)
        try:
            g.user_id = verify_user_token(token)
        except Exception:
            return _error("The authentication token is invalid or expired", 401)
        return view(*args, **kwargs)

    return wrapped


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _validate_video(path: Path) -> None:
    """Reject files whose content cannot be decoded as at least one frame."""
    capture = cv2.VideoCapture(str(path))
    try:
        opened, frame = capture.isOpened(), capture.read()[1]
    finally:
        capture.release()
    if not opened or frame is None:
        raise ValueError("The uploaded file is not a readable video")


def _convert_to_mp4(input_path: Path, output_path: Path) -> None:
    """Create a broadly playable H.264 MP4 and fail on encoder errors."""
    completed = subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(input_path),
            "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-profile:v", "baseline", "-level", "3.0", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or not output_path.is_file():
        raise RuntimeError("ffmpeg could not create the processed MP4")


def _classification(model_path: Path, loader, feature_loader, predictor, data_path: Path) -> str:
    """Run a current versioned model, or report a retraining requirement."""
    if not model_path.is_file():
        return "unavailable"
    try:
        bundle = loader(model_path)
        prediction = predictor(bundle, feature_loader(data_path))
        return "good" if int(prediction[0]) == 1 else "bad"
    except (ValueError, OSError) as error:
        logger.warning("Model unavailable: %s", error)
        return "unavailable"


def _llm_safety_identifier(user_id: str) -> str:
    """Create a stable pseudonym without sending the Firebase UID upstream."""
    salt = os.getenv("SAFETY_IDENTIFIER_SALT")
    if not salt:
        raise RuntimeError("SAFETY_IDENTIFIER_SALT is required for LLM requests")
    return hmac.new(salt.encode(), user_id.encode(), hashlib.sha256).hexdigest()


def _process_prediction(job_id: str, user_id: str, video_path: Path, work_dir: Path) -> None:
    """Process one isolated upload and publish only artifacts owned by its UID."""
    _set_job(job_id, status="processing")
    try:
        artifacts = break_down_video(video_path, work_dir, work_dir, clean=True)
        landmark_path = Path(artifacts["landmarks"])
        trajectory_path = Path(artifacts["trajectory"])
        annotated_avi = Path(artifacts["annotated_video"])
        processed_mp4 = work_dir / "processed_video.mp4"
        for required_path in (landmark_path, trajectory_path, annotated_avi):
            if not required_path.is_file():
                raise RuntimeError("The analysis pipeline did not produce all required artifacts")
        _convert_to_mp4(annotated_avi, processed_mp4)

        form_result = _classification(
            LANDMARK_MODEL, load_landmark_model, load_single_landmark_file, landmark_predict, landmark_path
        )
        trajectory_result = _classification(
            TRAJECTORY_MODEL, load_trajectory_model, load_trajectory, trajectory_predict, trajectory_path
        )

        artifact_id = uuid.uuid4().hex
        landmark_storage = save_to_firebase_storage(user_id, "landmarks", f"{artifact_id}.csv", landmark_path)
        trajectory_storage = save_to_firebase_storage(user_id, "trajectories", f"{artifact_id}.txt", trajectory_path)
        video_storage = save_to_firebase_storage(user_id, "videos", f"{artifact_id}.mp4", processed_mp4)

        player_name, similarity, player_path = compare_user_to_player(landmark_path, NBA_DATA_DIR, NBA_VIDEO_DIR)
        player_storage = None
        if player_path:
            # Copying the reference below the user's prefix makes later ownership
            # checks simple and avoids exposing arbitrary bucket objects.
            player_storage = save_to_firebase_storage(
                user_id, "references", f"{artifact_id}.mp4", player_path
            )
        analysis_id = save_to_firestore(
            user_id,
            landmark_storage,
            trajectory_storage,
            form_result,
            trajectory_result,
            video_storage,
            player_name,
            similarity,
            player_storage,
        )
        _set_job(job_id, status="complete", analysis_id=analysis_id)
    except Exception:
        logger.exception("Analysis job %s failed", job_id)
        _set_job(job_id, status="failed", error="Video analysis failed")
    finally:
        # Per-job folders make cleanup safe even while other jobs are running.
        shutil.rmtree(video_path.parent, ignore_errors=True)
        shutil.rmtree(work_dir, ignore_errors=True)


@server.get("/")
def home():
    return jsonify({"service": "Sharp Shooter API", "status": "ok"})


@server.errorhandler(413)
def upload_too_large(_error_value):
    return _error("The uploaded video exceeds the configured size limit", 413)


@server.post("/sign_in")
def sign_in():
    data = request.get_json(silent=True) or {}
    if not data.get("username") or not data.get("password"):
        return _error("Email and password are required", 400)
    try:
        return register_or_login(data["username"], data["password"])
    except Exception:
        logger.exception("Sign-in service failure")
        return _error("Authentication service is unavailable", 503)


@server.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    if not data.get("username") or not data.get("password"):
        return _error("Email and password are required", 400)
    try:
        return register_or_login(data["username"], data["password"], is_registering=True)
    except Exception:
        logger.exception("Registration service failure")
        return _error("Authentication service is unavailable", 503)


@server.post("/verify_token")
@require_auth
def verify_token_route():
    return jsonify({"status": "success", "user_id": g.user_id})


@server.post("/get_prediction")
@require_auth
def get_prediction():
    video_file = request.files.get("video")
    if not video_file or not video_file.filename:
        return _error("A video file is required", 400)
    safe_name = secure_filename(video_file.filename)
    if not safe_name or not _allowed_file(safe_name):
        return _error("Unsupported video file type", 400)

    job_id = uuid.uuid4().hex
    upload_dir = UPLOAD_ROOT / job_id
    work_dir = WORK_ROOT / job_id
    upload_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True)
    video_path = upload_dir / safe_name
    try:
        video_file.save(video_path)
        _validate_video(video_path)
    except ValueError as error:
        shutil.rmtree(upload_dir, ignore_errors=True)
        shutil.rmtree(work_dir, ignore_errors=True)
        return _error(str(error), 400)
    except Exception:
        logger.exception("Upload could not be saved")
        shutil.rmtree(upload_dir, ignore_errors=True)
        shutil.rmtree(work_dir, ignore_errors=True)
        return _error("The upload could not be saved", 500)

    with jobs_lock:
        _prune_completed_jobs(time.time())
        jobs[job_id] = {"owner": g.user_id, "status": "queued", "created_at": time.time()}
    executor.submit(_process_prediction, job_id, g.user_id, video_path, work_dir)
    return jsonify({"job_id": job_id, "status": "queued"}), 202


@server.get("/jobs/<job_id>")
@require_auth
def get_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or job["owner"] != g.user_id:
            return _error("Job not found", 404)
        response = {key: value for key, value in job.items() if key not in {"owner", "created_at"}}
    return jsonify(response)


@server.post("/get_user_history")
@require_auth
def get_user_history():
    try:
        documents = db.collection("users").document(g.user_id).collection("analysis").stream()
        history = []
        for document in documents:
            data = document.to_dict() or {}
            timestamp = data.get("timestamp")
            if isinstance(timestamp, (datetime.datetime, datetime.date)):
                timestamp = timestamp.isoformat()
            player_path = data.get("player_recording_path")
            history.append(
                {
                    "analysis_id": document.id,
                    "form_classification": data.get("form_classification"),
                    "trajectory_classification": data.get("trajectory_classification"),
                    "processed_video": data.get("processed_video"),
                    "timestamp": timestamp,
                    "llm_analysis": data.get("llm_analysis"),
                    "player_recording": generate_signed_url(player_path) if player_path else None,
                    "player_name": data.get("player_name"),
                    "similarity_percentage": data.get("similarity_percentage"),
                }
            )
        return jsonify({"history": history})
    except Exception:
        logger.exception("History retrieval failed")
        return _error("Could not retrieve analysis history", 500)


@server.post("/get_video")
@require_auth
def get_video():
    data = request.get_json(silent=True) or {}
    video_path = data.get("processed_video", "")
    # Never sign a bucket object outside the authenticated user's video prefix.
    if not video_path.startswith(f"{g.user_id}/videos/"):
        return _error("Video not found", 404)
    try:
        return jsonify({"video_url": generate_signed_url(video_path)})
    except FileNotFoundError:
        return _error("Video not found", 404)


@server.post("/get_nba_player_data")
@require_auth
def get_nba_player_data():
    data = request.get_json(silent=True) or {}
    analysis_id = data.get("analysis_id")
    if not analysis_id:
        return _error("Analysis ID is required", 400)
    analysis = get_analysis_by_id("users", g.user_id, analysis_id)
    if not analysis:
        return _error("Analysis not found", 404)

    temporary_dir = WORK_ROOT / f"nba-{uuid.uuid4().hex}"
    temporary_dir.mkdir(parents=True)
    try:
        landmark_path = temporary_dir / "landmarks.csv"
        landmark_path.write_bytes(grab_file_from_storage(analysis["landmark_file"]))
        player_name, similarity, player_path = compare_user_to_player(landmark_path, NBA_DATA_DIR, NBA_VIDEO_DIR)
        player_storage = None
        if player_path:
            player_storage = save_to_firebase_storage(g.user_id, "references", f"{uuid.uuid4().hex}.mp4", player_path)
        update_document("users", g.user_id, "analysis", analysis_id, "player_name", player_name)
        update_document("users", g.user_id, "analysis", analysis_id, "similarity_percentage", similarity)
        update_document("users", g.user_id, "analysis", analysis_id, "player_recording_path", player_storage)
        return jsonify({"status": "success", "player_name": player_name, "similarity_percentage": similarity})
    except Exception:
        logger.exception("NBA comparison failed")
        return _error("Could not compare this analysis", 500)
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


@server.post("/get_llm_analysis")
@require_auth
def get_llm_analysis():
    data = request.get_json(silent=True) or {}
    analysis_id = data.get("analysis_id")
    if not analysis_id:
        return _error("Analysis ID is required", 400)
    analysis = get_analysis_by_id("users", g.user_id, analysis_id)
    if not analysis:
        return _error("Analysis not found", 404)

    now = time.monotonic()
    if now - llm_last_request.get(g.user_id, 0.0) < 30:
        return _error("Please wait before requesting another generated analysis", 429)
    llm_last_request[g.user_id] = now
    try:
        landmark_data = grab_file_from_storage(analysis["landmark_file"]).decode("utf-8")
        result = create_llm_analysis(landmark_data, _llm_safety_identifier(g.user_id))
        save_analysis_by_id(g.user_id, analysis_id, result)
        return jsonify({"text": result})
    except (UnicodeDecodeError, KeyError):
        return _error("Stored landmark data is invalid", 422)
    except Exception:
        logger.exception("Generated analysis failed")
        return _error("Could not generate coaching feedback", 503)


if __name__ == "__main__":
    # Use a production WSGI server and TLS-terminating proxy outside development.
    server.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
