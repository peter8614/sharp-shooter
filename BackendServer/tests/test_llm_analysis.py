"""Tests for local pose aggregation and bounded OpenAI request construction."""

from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from llm_analysis import (
    DEFAULT_OPENAI_MODEL,
    build_coaching_instructions,
    build_landmark_summary,
    create_llm_analysis,
    create_llm_analysis_from_summary,
)


HEADER = (
    "Frame,Left Shoulder,Right Shoulder,Left Elbow,Right Elbow,"
    "Left Wrist,Right Wrist\n"
)


def landmark_csv(row_count: int = 5, include_invalid_row: bool = False) -> str:
    """Create deterministic upper-body rows with quoted coordinate fields."""
    rows = []
    for index in range(row_count):
        elbow_y = 0.4 - index * 0.01
        wrist_y = 0.2 - index * 0.01
        rows.append(
            f'{index},"0.4,0.5,0","0.6,0.5,0",'
            f'"0.4,{elbow_y},0","0.6,{elbow_y},0",'
            f'"0.4,{wrist_y},0","0.6,{wrist_y},0"'
        )
    if include_invalid_row:
        rows.append('bad,"invalid","0.6,0.5,0","0.4,0.4,0","0.6,0.4,0","0.4,0.2,0","0.6,0.2,0"')
    return HEADER + "\n".join(rows) + "\n"


class FakeResponses:
    def __init__(self):
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            output_text=(
                "  Main Findings\nA possible wrist-position issue was found.\n\n"
                "How to Improve\nUse slow close-range repetitions.  "
            )
        )


class LlmAnalysisTests(unittest.TestCase):
    def test_chinese_coaching_from_summary_uses_private_aggregate_only(self):
        responses = FakeResponses()
        responses.create = lambda **kwargs: SimpleNamespace(
            output_text="主要发现\n现有数据不能定位具体原因。\n如何改进\n保持同一机位复测。"
        )
        summary = build_landmark_summary(landmark_csv())
        with patch.dict(os.environ, {}, clear=True):
            response = create_llm_analysis_from_summary(
                summary, "anonymous-safety-id",
                client=SimpleNamespace(responses=responses),
                output_language="Chinese",
            )
        self.assertIn("主要发现", response)
        self.assertIn("如何改进", response)
        self.assertIn("Output in Chinese", build_coaching_instructions("Chinese"))

    def test_generic_concern_omits_raw_class_and_strength_when_flagged(self):
        responses = FakeResponses()
        with patch.dict(os.environ, {}, clear=True):
            create_llm_analysis_from_summary(
                build_landmark_summary(landmark_csv()),
                "anonymous-safety-id", client=SimpleNamespace(responses=responses),
                coaching_context={"coaching_labels": [
                    {
                        "code": "form_model_no_issue_detected", "status": "strength",
                        "area": "form", "confidence": 0.88,
                        "evidence": {"classification": "good"},
                        "coaching_goal": "Preserve the pattern.",
                        "practice": "Retest.",
                    },
                    {
                        "code": "trajectory_model_flagged", "status": "needs_attention",
                        "area": "trajectory", "confidence": 0.87,
                        "evidence": {"classification": "bad"},
                        "coaching_goal": "The cause is unknown.",
                        "practice": "Use controlled close-range repetitions.",
                    },
                ]},
            )
        labels = json.loads(responses.request["input"])["model_assessment"]["coaching_labels"]
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0]["area"], "trajectory")
        self.assertNotIn("evidence", labels[0])
        self.assertNotIn("good", responses.request["input"])
        self.assertNotIn('"bad"', responses.request["input"])

    def test_summary_aggregates_rows_and_reports_tracking_failures(self):
        summary = build_landmark_summary(landmark_csv(include_invalid_row=True))

        self.assertEqual(summary["data_quality"]["input_rows"], 6)
        self.assertEqual(summary["data_quality"]["usable_rows"], 5)
        self.assertEqual(summary["data_quality"]["dropped_rows"], 1)
        self.assertTrue(summary["data_quality"]["sufficient_for_coaching"])
        self.assertIn("left_elbow_angle_degrees", summary["measurements"])
        self.assertNotIn("frames", summary)

    def test_too_few_frames_are_marked_insufficient(self):
        summary = build_landmark_summary(landmark_csv(row_count=4))
        self.assertFalse(summary["data_quality"]["sufficient_for_coaching"])

    def test_missing_columns_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing columns"):
            build_landmark_summary("Frame,Left Shoulder\n0,0\n")

    def test_request_uses_low_cost_default_and_never_sends_raw_rows(self):
        responses = FakeResponses()
        client = SimpleNamespace(responses=responses)
        raw_content = landmark_csv()

        with patch.dict(os.environ, {}, clear=True):
            result = create_llm_analysis(
                raw_content,
                "anonymous-safety-id",
                client=client,
                coaching_context={
                    "form_classification": "bad",
                    "form_confidence": 0.84,
                    "coaching_labels": [
                        {
                            "code": "form_model_flagged",
                            "status": "needs_attention",
                            "area": "form",
                            "confidence": 0.84,
                            "severity": "medium",
                            "evidence": {"classification": "bad"},
                            "coaching_goal": "Review the specific evidence.",
                            "practice": "Use controlled repetitions.",
                        },
                        {
                            "code": "right_wrist_lower_than_good_reference",
                            "status": "needs_attention",
                            "area": "right_wrist",
                            "confidence": 0.8,
                            "severity": "medium",
                            "evidence": {
                                "observed": 0.3,
                                "reference_low": -0.2,
                                "reference_high": 0.1,
                            },
                            "coaching_goal": "Explore a slightly higher wrist position.",
                            "practice": "Use slow close-range repetitions.",
                            "untrusted_extra": "must not be sent",
                        }
                    ],
                },
            )

        self.assertIn("Main Findings", result)
        self.assertIn("How to Improve", result)
        self.assertEqual(responses.request["model"], DEFAULT_OPENAI_MODEL)
        self.assertEqual(responses.request["reasoning"], {"effort": "low"})
        self.assertEqual(responses.request["text"], {"verbosity": "low"})
        self.assertFalse(responses.request["store"])
        self.assertEqual(responses.request["safety_identifier"], "anonymous-safety-id")
        sent_summary = json.loads(responses.request["input"])
        self.assertEqual(sent_summary["data_quality"]["usable_rows"], 5)
        self.assertEqual(len(sent_summary["model_assessment"]["coaching_labels"]), 1)
        sent_label = sent_summary["model_assessment"]["coaching_labels"][0]
        self.assertEqual(sent_label["area"], "right_wrist")
        self.assertNotIn("code", sent_label)
        self.assertNotIn("severity", sent_label)
        self.assertNotIn("status", sent_label)
        self.assertNotIn("untrusted_extra", sent_label)
        self.assertNotIn("form_model_flagged", responses.request["input"])
        self.assertNotIn(raw_content, responses.request["input"])

    def test_prompt_defines_evidence_output_and_safety_boundaries(self):
        prompt = build_coaching_instructions("English")
        self.assertIn("Use only facts and measurements", prompt)
        self.assertIn("not a continuous timeline", prompt)
        self.assertIn("first and last usable rows", prompt)
        self.assertIn("Never claim frame-to-frame consistency", prompt)
        self.assertIn("wrap at -90/+90 degrees", prompt)
        self.assertIn("Do not describe aggregate ranges as movement fluctuation", prompt)
        self.assertIn("names unavailable phases", prompt)
        self.assertIn("never diagnoses or proof of good or bad technique", prompt)
        self.assertIn("silently audit the draft", prompt)
        self.assertIn("recommends narrowing, stabilizing, or standardizing", prompt)
        self.assertIn("Output in English", prompt)
        self.assertIn("Main Findings", prompt)
        self.assertIn("How to Improve", prompt)
        self.assertIn("Make How to Improve the majority of the response", prompt)
        self.assertIn("never reproduce JSON field names", prompt)
        self.assertIn("Do not output sections titled Data Quality", prompt)
        self.assertIn("only source of named problems", prompt)
        self.assertIn("under 180 words", prompt)

    def test_disabled_sections_and_internal_codes_are_rejected(self):
        responses = FakeResponses()
        client = SimpleNamespace(responses=responses)

        responses.create = lambda **kwargs: SimpleNamespace(
            output_text=(
                "Main Findings\nform_model_flagged\n\n"
                "How to Improve\nPractise close-range shots.\n\n"
                "Limits and Safety\nNot shown."
            )
        )

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "disabled coaching section"):
                create_llm_analysis(
                    landmark_csv(),
                    "anonymous-safety-id",
                    client=client,
                )

    def test_instruction_text_copied_into_heading_is_rejected(self):
        client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(
            output_text="Main Findings — explain two findings\nNothing specific.\nHow to Improve\nRetest."
        )))
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "missing a required coaching section"):
                create_llm_analysis_from_summary(
                    build_landmark_summary(landmark_csv()),
                    "anonymous-safety-id", client=client,
                )


if __name__ == "__main__":
    unittest.main()
