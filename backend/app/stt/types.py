from dataclasses import dataclass


@dataclass
class Segment:
    """話者情報付きの、整列された音声セグメント.

    start (float): セグメントの開始時刻 (秒).
    end (float): セグメントの終了時刻 (秒).
    speaker_label (str): 話者ラベル (例: "Speaker 1", "Speaker 2" など).
    text (str): セグメントの文字起こしテキスト.
    """
    start: float
    end: float
    speaker_label: str
    text: str
