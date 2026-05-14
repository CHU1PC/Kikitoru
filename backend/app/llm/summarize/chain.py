from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.runnables import RunnableLambda

from app.llm.google_genai import gemini
from app.llm.summarize.prompts import prompt
from app.llm.summarize.schema import Summary

if TYPE_CHECKING:
    from app.stt.types import Segment


def _format_segments(segments: list[Segment]) -> dict[str, str]:
    """Convert list[Segment] into the dict shape expected by the prompt.

    Args:
        segments (list[Segment]): List of transcribed segments.

    Returns:
        dict[str, str]: A dictionary with a single key "segments_json" containing the JSON string of segments.
    """
    payload: list[dict[str, int | str]] = [
        {"id": i, "speaker": s.speaker_label, "text": s.text}
        for i, s in enumerate(segments)
    ]
    return {
        "segments_json": json.dumps(payload, ensure_ascii=False, indent=2),
    }


summarize_chain = (
    RunnableLambda(_format_segments)
    | prompt
    | gemini.with_structured_output(Summary)
)
