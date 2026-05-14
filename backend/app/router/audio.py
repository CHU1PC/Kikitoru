from __future__ import annotations

import asyncio
import io

from fastapi import APIRouter, HTTPException, UploadFile

from app.llm.summarize import summarize_chain
from app.llm.summarize.schema import Summary
from app.stt.pipeline import transcribe_with_diarization

router = APIRouter(prefix="/audio", tags=["audio"])

_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB
_ALLOWED_CONTENT_TYPES = frozenset({
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
    "audio/flac",
    "audio/x-flac",
    "audio/m4a",
    "audio/x-m4a",
})


@router.post("/summarize", response_model=Summary)
async def summarize_audio(file: UploadFile) -> Summary:
    """Accepts an audio file and returns a structured meeting summary.

    Args:
        file (UploadFile): The audio file to process (mp3, m4a, wav, flac). Max 200 MB.

    Returns:
        Summary: Structured meeting summary including topics, decisions, and action items.

    Raises:
        HTTPException: 413 if the file exceeds 200 MB, 415 if the format is unsupported.
    """
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported media type: {file.content_type}")

    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 200 MB limit")

    data = io.BytesIO(raw)
    segments = await asyncio.to_thread(transcribe_with_diarization, data)
    return await summarize_chain.ainvoke(segments)
