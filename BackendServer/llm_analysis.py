"""Optional LLM-generated coaching feedback."""

from __future__ import annotations

import os

from openai import OpenAI

MAX_INPUT_CHARACTERS = 40_000


def create_llm_analysis(
    content: str,
    safety_identifier: str,
    max_output_tokens: int = 500,
) -> str:
    """Generate cautious coaching suggestions from a bounded landmark payload."""
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    if not api_key or not model:
        raise RuntimeError("OPENAI_API_KEY and OPENAI_MODEL are required")
    if not content.strip():
        raise ValueError("Landmark data is empty")
    if not safety_identifier:
        raise ValueError("A privacy-preserving safety identifier is required")

    # Bounding the payload controls cost and limits unnecessary biometric data.
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        max_output_tokens=max_output_tokens,
        instructions=(
            "You are a basketball coach. Explain only patterns supported by the "
            "provided pose landmarks. Clearly state uncertainty, do not diagnose "
            "injuries, and give concise, actionable shooting-form suggestions."
        ),
        input=content[:MAX_INPUT_CHARACTERS],
        safety_identifier=safety_identifier,
        # Pose landmarks are sensitive, so this one-shot response is not stored.
        store=False,
    )
    result = response.output_text.strip()
    if not result:
        raise RuntimeError("The model returned an empty analysis")
    return result
