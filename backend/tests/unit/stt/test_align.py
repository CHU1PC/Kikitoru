from app.stt.align import align
from app.stt.types import DiarizationTurn, Segment, WhisperSegment


def test_transcript_fully_within_turn() -> None:
    """文字起こしが話者ターンに完全に収まるとき、その話者が割り当てられることを確認するテスト."""
    transcripts = [WhisperSegment(start=1.0, end=2.0, text="hello")]
    turns = [DiarizationTurn(start=0.0, end=5.0, speaker="SPEAKER_00")]

    result = align(transcripts, turns)

    assert result == [
        Segment(
            start=1.0,
            end=2.0,
            speaker_label="SPEAKER_00",
            text="hello",
        ),
    ]


def test_transcript_spans_two_turns_picks_max_overlap() -> None:
    """2つのターンにまたがるとき、重なりが最大の話者が選ばれることを確認するテスト."""
    # 文字起こし: 4.0 - 7.0
    # SPEAKER_00 ターン: 0.0 - 5.0  (重なり = 1.0 秒)
    # SPEAKER_01 ターン: 5.0 - 10.0 (重なり = 2.0 秒)
    transcripts = [WhisperSegment(start=4.0, end=7.0, text="across")]
    turns = [
        DiarizationTurn(start=0.0, end=5.0, speaker="SPEAKER_00"),
        DiarizationTurn(start=5.0, end=10.0, speaker="SPEAKER_01"),
    ]

    result = align(transcripts, turns)

    assert len(result) == 1
    assert result[0].speaker_label == "SPEAKER_01"


def test_no_overlapping_turn_uses_unknown() -> None:
    """重なる話者ターンが無いとき、話者が UNKNOWN になることを確認するテスト."""
    transcripts = [WhisperSegment(start=10.0, end=12.0, text="silent")]
    turns = [DiarizationTurn(start=0.0, end=5.0, speaker="SPEAKER_00")]

    result = align(transcripts, turns)

    assert len(result) == 1
    assert result[0].speaker_label == "UNKNOWN"


def test_empty_transcripts_returns_empty() -> None:
    """文字起こしが空なら結果も空になることを確認するテスト."""
    turns = [DiarizationTurn(start=0.0, end=5.0, speaker="SPEAKER_00")]

    result = align([], turns)

    assert result == []


def test_empty_diarization_marks_all_unknown() -> None:
    """話者ターンが空のとき、全セグメントが UNKNOWN になることを確認するテスト."""
    transcripts = [
        WhisperSegment(start=0.0, end=1.0, text="a"),
        WhisperSegment(start=1.0, end=2.0, text="b"),
    ]

    result = align(transcripts, [])

    expected_count = 2
    assert len(result) == expected_count
    assert all(s.speaker_label == "UNKNOWN" for s in result)
    assert [s.text for s in result] == ["a", "b"]


def test_multiple_transcripts_aligned_in_order() -> None:
    """複数の文字起こしが入力順を保って話者割り当てされることを確認するテスト."""
    transcripts = [
        WhisperSegment(start=0.0, end=2.0, text="first"),
        WhisperSegment(start=2.5, end=4.5, text="second"),
    ]
    turns = [
        DiarizationTurn(start=0.0, end=2.0, speaker="SPEAKER_00"),
        DiarizationTurn(start=2.0, end=5.0, speaker="SPEAKER_01"),
    ]

    result = align(transcripts, turns)

    assert [s.speaker_label for s in result] == ["SPEAKER_00", "SPEAKER_01"]
    assert [s.text for s in result] == ["first", "second"]
