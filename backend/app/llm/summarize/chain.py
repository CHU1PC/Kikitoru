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
    """(segments, recorded_at) を prompt が期待する dict の形に変換する.

    Args:
        inputs (tuple[list[Segment], date]): セグメントと、音声内の相対日付表現を解決するための基準日.

    Returns:
        dict[str, str]: "segments_json" と "recorded_at" のキーを持つ辞書.
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
