from dataclasses import dataclass


@dataclass
class WhisperSegment:
    """
    start: float - The start time of the segment in seconds.
    end: float - The end time of the segment in seconds.
    text: str - The transcribed text for the segment.
    """
    start: float
    end: float
    text: str


@dataclass
class DiarizationTurn:
    """
    start: float - The start time of the speaker turn in seconds.
    end: float - The end time of the speaker turn in seconds.
    speaker: str - The label for the speaker (e.g., "Speaker 1", "Speaker 2", etc.).
    """
    start: float
    end: float
    speaker: str


@dataclass
class Segment:
    """
    start_seconds: float - The start time of the segment in seconds.
    end_seconds: float - The end time of the segment in seconds.
    speaker_label: str - The label for the speaker (e.g., "Speaker 1", "Speaker 2", etc.).
    text: str - The transcribed text for the segment
    """
    start_seconds: float
    end_seconds: float
    speaker_label: str
    text: str
