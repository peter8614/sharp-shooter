"""Private, versioned NBA reference index used by the AWS worker."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from NBA_compare import _variance_vector, find_landmark_variances
from . import s3_service


_CATALOG_KEY = re.compile(r"^references/catalog-[0-9a-f]{64}\.json$")
_VIDEO_KEY = re.compile(r"^references/videos/[a-z0-9-]{1,80}\.mp4$")


@dataclass(frozen=True)
class ReferenceEntry:
    reference_id: str
    player_name: str
    variance: np.ndarray
    video_key: str


def parse_catalog(raw: bytes) -> tuple[ReferenceEntry, ...]:
    if len(raw) > 1_000_000:
        raise ValueError("Reference catalog is too large")
    document = json.loads(raw)
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("Unsupported reference catalog")
    entries = document.get("entries")
    if not isinstance(entries, list) or len(entries) > 500:
        raise ValueError("Invalid reference entries")
    parsed = []
    seen_ids = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid reference entry")
        reference_id = entry.get("id")
        player_name = entry.get("player_name")
        video_key = entry.get("video_key")
        if (
            not isinstance(reference_id, str)
            or not re.fullmatch(r"[a-z0-9-]{1,80}", reference_id)
            or reference_id in seen_ids
            or not isinstance(player_name, str)
            or not player_name.strip()
            or len(player_name) > 100
            or not isinstance(video_key, str)
            or not _VIDEO_KEY.fullmatch(video_key)
            or not video_key.startswith(f"references/videos/{reference_id}-")
        ):
            raise ValueError("Invalid reference metadata")
        variance = _variance_vector(entry.get("variance"))
        parsed.append(ReferenceEntry(reference_id, player_name, variance, video_key))
        seen_ids.add(reference_id)
    return tuple(parsed)


@lru_cache(maxsize=4)
def load_catalog(bucket: str, key: str) -> tuple[ReferenceEntry, ...]:
    if not _CATALOG_KEY.fullmatch(key):
        raise ValueError("Invalid reference catalog key")
    response = s3_service._get_s3_client().get_object(Bucket=bucket, Key=key)
    return parse_catalog(response["Body"].read(1_000_001))


def closest_reference(
    user_landmark_csv: str | Path, entries: tuple[ReferenceEntry, ...]
) -> tuple[ReferenceEntry | None, float | None]:
    if not entries:
        return None, None
    user_vector = _variance_vector(find_landmark_variances(user_landmark_csv))
    candidates = []
    for entry in entries:
        scale = np.maximum(np.abs(user_vector) + np.abs(entry.variance), 1e-9)
        distance = float(np.mean(np.abs(user_vector - entry.variance) / scale))
        candidates.append((distance, entry.reference_id, entry))
    distance, _, entry = min(candidates)
    score = round(max(0.0, min(100.0, (1.0 - distance) * 100.0)), 2)
    return entry, score
