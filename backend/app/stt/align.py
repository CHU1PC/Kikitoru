from app.stt.types import DiarizationTurn, Segment, WhisperSegment


def align(transcripts: list[WhisperSegment], diarization_turns: list[DiarizationTurn]) -> list[Segment]:
    """Aligns transcribed segments with speaker diarization turns.

    Args:
        transcripts (list[WhisperSegment]): list of transcribed segments from Whisper,
            each with start time, end time, and text.
        diarization_turns (list[DiarizationTurn]): list of speaker diarization
            turns, each with start time, end time, and speaker label.

    Returns:
        list[Segment]: list of aligned segments with speaker labels and transcribed text.
    """
    segments: list[Segment] = []

    for transcript in transcripts:
        candidates = [
            d
            for d in diarization_turns
            if (
                d.start < transcript.end
                and transcript.start < d.end
            )
        ]
        if not candidates:
            speaker = "UNKNOWN"
        else:
            speaker = max(candidates, key=lambda d: min(d.end, transcript.end) - max(d.start, transcript.start)).speaker

        segments.append(
            Segment(
                start_seconds=transcript.start,
                end_seconds=transcript.end,
                speaker_label=speaker,
                text=transcript.text
            )
        )

    return segments
