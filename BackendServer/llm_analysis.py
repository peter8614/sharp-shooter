"""Privacy-conscious LLM coaching from locally aggregated pose landmarks."""

from __future__ import annotations

import csv
import io
import json
import math
import os
from typing import Any

import numpy as np

from coaching_labels import sanitize_coaching_context


DEFAULT_OPENAI_MODEL = "gpt-5.4-nano"
DEFAULT_REASONING_EFFORT = "low"
MAX_SOURCE_CHARACTERS = 2_000_000
MAX_LANDMARK_ROWS = 2_000
MIN_COACHING_FRAMES = 5
LANDMARK_NAMES = (
    "Left Shoulder",
    "Right Shoulder",
    "Left Elbow",
    "Right Elbow",
    "Left Wrist",
    "Right Wrist",
)
ALLOWED_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh"}
REQUIRED_OUTPUT_HEADINGS = ("main findings", "how to improve")
FORBIDDEN_OUTPUT_PHRASES = (
    "data quality",
    "limits and safety",
    "what looks good",
)


def _parse_point(value: object) -> np.ndarray:
    """Parse one MediaPipe x,y,z point and reject malformed coordinates."""
    point = np.asarray(str(value).split(","), dtype=float)
    if point.shape != (3,) or not np.isfinite(point).all():
        raise ValueError("Landmark data contains an invalid coordinate")
    return point


def _joint_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Return angle ABC in degrees, rejecting coincident landmark vectors."""
    first = a - b
    second = c - b
    denominator = np.linalg.norm(first) * np.linalg.norm(second)
    if denominator <= 1e-9:
        raise ValueError("Landmark data contains a degenerate joint")
    cosine = np.clip(np.dot(first, second) / denominator, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


def _statistics(values: list[float]) -> dict[str, float]:
    """Create a compact, rounded summary without retaining frame-level data."""
    array = np.asarray(values, dtype=float)
    return {
        "mean": round(float(np.mean(array)), 2),
        "standard_deviation": round(float(np.std(array)), 2),
        "minimum": round(float(np.min(array)), 2),
        "maximum": round(float(np.max(array)), 2),
        "start": round(float(array[0]), 2),
        "end": round(float(array[-1]), 2),
    }


def build_landmark_summary(content: str) -> dict[str, Any]:
    """Convert private frame landmarks into an anonymous aggregate summary."""
    if not content.strip():
        raise ValueError("Landmark data is empty")
    if len(content) > MAX_SOURCE_CHARACTERS:
        raise ValueError("Landmark data exceeds the local processing limit")

    reader = csv.DictReader(io.StringIO(content))
    required_columns = ("Frame", *LANDMARK_NAMES)
    missing = [name for name in required_columns if name not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"Landmark data is missing columns: {', '.join(missing)}")

    frame_numbers: list[float] = []
    left_angles: list[float] = []
    right_angles: list[float] = []
    left_wrist_heights: list[float] = []
    right_wrist_heights: list[float] = []
    left_forearm_offsets: list[float] = []
    right_forearm_offsets: list[float] = []
    shoulder_tilts: list[float] = []
    input_rows = dropped_rows = 0

    for row in reader:
        input_rows += 1
        if input_rows > MAX_LANDMARK_ROWS:
            raise ValueError("Landmark data contains too many rows")
        try:
            frame_number = float(row["Frame"])
            if not math.isfinite(frame_number):
                raise ValueError("Frame number is not finite")
            points = {name: _parse_point(row[name]) for name in LANDMARK_NAMES}
            left_shoulder = points["Left Shoulder"]
            right_shoulder = points["Right Shoulder"]

            left_elbow = points["Left Elbow"]
            right_elbow = points["Right Elbow"]
            left_wrist = points["Left Wrist"]
            right_wrist = points["Right Wrist"]
            left_angle = _joint_angle(left_shoulder, left_elbow, left_wrist)
            right_angle = _joint_angle(right_shoulder, right_elbow, right_wrist)

            # MediaPipe x/y values are already normalized by image dimensions.
            # Do not divide by apparent shoulder width: it approaches zero in a
            # side view and would amplify small tracking errors dramatically.
            left_wrist_height = float(left_shoulder[1] - left_wrist[1])
            right_wrist_height = float(right_shoulder[1] - right_wrist[1])
            left_forearm_offset = float(abs(left_wrist[0] - left_elbow[0]))
            right_forearm_offset = float(abs(right_wrist[0] - right_elbow[0]))
            raw_shoulder_tilt = math.degrees(
                math.atan2(
                    right_shoulder[1] - left_shoulder[1],
                    right_shoulder[0] - left_shoulder[0],
                )
            )
            # A line has no forward direction. Folding it into [-90, 90) avoids
            # artificial jumps between -180 and +180 degrees across frames.
            shoulder_tilt = float((raw_shoulder_tilt + 90.0) % 180.0 - 90.0)

            # Append only after the entire row has passed validation so every
            # measurement array represents the same set of usable frames.
            frame_numbers.append(frame_number)
            left_angles.append(left_angle)
            right_angles.append(right_angle)
            left_wrist_heights.append(left_wrist_height)
            right_wrist_heights.append(right_wrist_height)
            left_forearm_offsets.append(left_forearm_offset)
            right_forearm_offsets.append(right_forearm_offset)
            shoulder_tilts.append(shoulder_tilt)
        except (KeyError, TypeError, ValueError):
            # A few tracking failures should reduce the stated data quality, not
            # prevent all otherwise usable frames from being summarized.
            dropped_rows += 1

    if not frame_numbers:
        raise ValueError("Landmark data does not contain any usable frames")

    usable_rows = len(frame_numbers)
    return {
        "schema_version": 1,
        "data_quality": {
            "input_rows": input_rows,
            "usable_rows": usable_rows,
            "dropped_rows": dropped_rows,
            "frame_span": round(max(frame_numbers) - min(frame_numbers), 2),
            "sufficient_for_coaching": usable_rows >= MIN_COACHING_FRAMES,
        },
        "measurements": {
            "left_elbow_angle_degrees": _statistics(left_angles),
            "right_elbow_angle_degrees": _statistics(right_angles),
            "left_wrist_height_image_fraction": _statistics(left_wrist_heights),
            "right_wrist_height_image_fraction": _statistics(right_wrist_heights),
            "left_forearm_horizontal_offset_image_fraction": _statistics(
                left_forearm_offsets
            ),
            "right_forearm_horizontal_offset_image_fraction": _statistics(
                right_forearm_offsets
            ),
            "shoulder_line_angle_degrees": _statistics(shoulder_tilts),
        },
        "measurement_notes": [
            "Positive wrist height means the wrist is above its same-side shoulder in the image.",
            "Forearm horizontal offset is an absolute fraction of normalized image width.",
            "Shoulder-line angle is folded into the range from -90 to 90 degrees.",
            "The rows are filtered likely-shot frames and may be non-consecutive.",
        ],
        "known_limits": [
            "The shooting hand, camera viewpoint, and camera distance are unknown.",
            "Only shoulder, elbow, and wrist landmarks from likely shot frames are available.",
            "MediaPipe depth is relative and these measurements are not clinical biomechanics.",
            "Shot outcome, pain, fatigue, lower-body motion, and ball release are unavailable.",
        ],
    }


def build_coaching_instructions(output_language: str) -> str:
    """Return a concise prompt with explicit evidence and safety boundaries."""
    return f"""Provide educational basketball shooting-form feedback from the
supplied aggregate MediaPipe-landmark summary. Respond in {output_language}.

Evidence rules:
- Use only facts and measurements present in the JSON. Treat coordinate-derived
  patterns as observations, never diagnoses or proof of good or bad technique.
- Treat model_assessment.coaching_labels as the only source of named problems,
  correction goals, and drills. Never invent an issue. Describe every finding in
  natural user-facing language; never reproduce JSON field names, internal label
  codes, snake_case text, status values, or severity values. When a label includes
  numeric evidence, cite its observed value, reference band, and confidence.
  Reference bands describe this training dataset, not universal ideal biomechanics.
- The summary contains aggregates, not a continuous timeline. The start and end
  values are only the first and last usable rows; they are not named shot phases.
  Never claim frame-to-frame consistency, timing, sequencing, drift, stability,
  or repeatability from these aggregates.
- A range or standard deviation during a moving shot does not by itself identify
  a technique fault. Shoulder-line angles wrap at -90/+90 degrees, so values near
  opposite boundaries may represent similar orientations rather than a large
  change.
- Do not describe aggregate ranges as movement fluctuation or use words such as
  consistent, inconsistent, stable, unstable, variable, or changing. Do not use
  start, end, range, or standard deviation to name a shot phase or justify a
  correction, drill, or side-specific adjustment.
- Never infer the shooting hand, camera viewpoint, shot result, pain, injury,
  lower-body mechanics, set point, or ball-release timing when unavailable.
- If sufficient_for_coaching is false, say that the recording is insufficient
  and explain how to capture a better one; do not provide technique conclusions.
- Do not compare the user with a professional player or invent ideal angle ranges.

Before answering, silently audit the draft and rewrite any sentence that:
- treats a range or standard deviation as actual motion, instability, or a fault;
- names unavailable phases such as before release, after release, or set point;
- recommends narrowing, stabilizing, or standardizing a measured distribution; or
- treats shoulder angles near -90 and +90 degrees as a large physical rotation.

Output in English using exactly these two headings and no others:
1. Main Findings — explain at most two supported findings in plain language. Do
   not show internal codes or generic classifier flags. Express lower-confidence
   findings as possibilities rather than facts. If no specific finding is
   supported, say so briefly.
2. How to Improve — make this the majority of the response. Give one clear,
   practical action for each finding, using only its supplied coaching goal and
   practice instruction. Do not turn a generic classifier result into a specific
   body-mechanics claim.

Do not output sections titled Data Quality, What Looks Good, Limits and Safety,
or any additional section. Apply evidence, privacy, limitation, and safety rules
silently instead of listing them for the user. Use neutral, supportive language
and keep the complete response under 180 words."""


def _prepare_model_assessment(context: dict[str, Any] | None) -> dict[str, Any]:
    """Remove internal implementation details before constructing the API input."""
    safe_context = sanitize_coaching_context(context)
    labels = safe_context.get("coaching_labels", [])

    # Numeric observed/reference evidence marks a specific finding. When one is
    # available, the generic classifier flag would only duplicate and confuse it.
    specific_labels = [
        label
        for label in labels
        if isinstance(label.get("evidence"), dict)
        and "observed" in label["evidence"]
        and "reference_low" in label["evidence"]
        and "reference_high" in label["evidence"]
    ]
    selected_labels = specific_labels or labels

    public_labels: list[dict[str, Any]] = []
    for label in selected_labels[:2]:
        # Codes, statuses, and severity are useful for backend logic but should
        # never become visible jargon in a coaching response.
        public_label = {
            key: label[key]
            for key in (
                "area",
                "confidence",
                "evidence",
                "coaching_goal",
                "practice",
            )
            if key in label
        }
        if public_label:
            public_labels.append(public_label)

    return {"coaching_labels": public_labels} if public_labels else {}


def _validate_coaching_output(result: str) -> str:
    """Reject responses that expose internal codes or unwanted UI sections."""
    normalized = result.casefold()
    if any(heading not in normalized for heading in REQUIRED_OUTPUT_HEADINGS):
        raise RuntimeError("The model response is missing a required coaching section")
    if any(phrase in normalized for phrase in FORBIDDEN_OUTPUT_PHRASES):
        raise RuntimeError("The model response contains a disabled coaching section")
    if any("_" in token for token in result.split()):
        raise RuntimeError("The model response contains an internal label code")
    return result


def create_llm_analysis(
    content: str,
    safety_identifier: str,
    max_output_tokens: int = 700,
    client: Any | None = None,
    coaching_context: dict[str, Any] | None = None,
) -> str:
    """Generate bounded coaching without sending raw frame-level landmarks."""
    if not safety_identifier:
        raise ValueError("A privacy-preserving safety identifier is required")

    summary = build_landmark_summary(content)
    model_assessment = _prepare_model_assessment(coaching_context)
    if model_assessment:
        # Only bounded server-generated labels are added; raw feature vectors and
        # frame-level landmarks never leave the backend.
        summary["model_assessment"] = model_assessment
    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip()
    if not model:
        raise RuntimeError("OPENAI_MODEL must not be empty")
    reasoning_effort = os.getenv(
        "OPENAI_REASONING_EFFORT", DEFAULT_REASONING_EFFORT
    ).strip().lower()
    if reasoning_effort not in ALLOWED_REASONING_EFFORTS:
        raise RuntimeError(
            "OPENAI_REASONING_EFFORT must be none, low, medium, high, or xhigh"
        )
    if client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required")
        # Import lazily so privacy-summary unit tests do not require the runtime
        # OpenAI dependency or any credentials in continuous integration.
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

    response = client.responses.create(
        model=model,
        reasoning={"effort": reasoning_effort},
        text={"verbosity": "low"},
        max_output_tokens=max_output_tokens,
        instructions=build_coaching_instructions("English"),
        input=json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
        safety_identifier=safety_identifier,
        # Pose-derived summaries remain sensitive, so the response is not stored.
        store=False,
    )
    result = response.output_text.strip()
    if not result:
        raise RuntimeError("The model returned an empty analysis")
    return _validate_coaching_output(result)
