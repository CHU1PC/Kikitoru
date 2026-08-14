from dataclasses import dataclass


@dataclass
class Segment:
    """話者情報付きの、整列された音声セグメント.

    start_ms (int): セグメントの開始時刻 (ミリ秒).
    end_ms (int): セグメントの終了時刻 (ミリ秒).
    speaker_label (str): 話者ラベル (例: "Speaker 1", "Speaker 2" など).
    text (str): セグメントの文字起こしテキスト.
    """
    start_ms: int
    end_ms: int
    speaker_label: str
    text: str
