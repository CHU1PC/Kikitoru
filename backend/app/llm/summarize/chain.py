from __future__ import annotations

import json
from typing import TYPE_CHECKING

from langchain_core.runnables import RunnableLambda

from app.llm.google_genai import gemini
from app.llm.summarize.prompts import prompt
from app.llm.summarize.schema import Summary

if TYPE_CHECKING:
    from datetime import date

    from app.stt.types import Segment


def _format_input(inputs: tuple[list[Segment], date]) -> dict[str, str]:
    """Convert (segments, recorded_at) into the dict shape expected by the prompt.

    Args:
        inputs (tuple[list[Segment], date]): Segments and reference date for resolving
            relative date expressions in the audio.

    Returns:
        dict[str, str]: Dictionary with "segments_json" and "recorded_at" keys.
    """
    segments, recorded_at = inputs
    payload: list[dict[str, int | str]] = [
        {"id": i, "speaker": s.speaker_label, "text": s.text}
        for i, s in enumerate(segments)
    ]
    return {
        "segments_json": json.dumps(payload, ensure_ascii=False, indent=2),
        "recorded_at": recorded_at.isoformat(),
    }


summarize_chain = (
    RunnableLambda(_format_input)
    | prompt
    | gemini.with_structured_output(Summary)
)
