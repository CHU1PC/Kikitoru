from pydantic import BaseModel, Field


class _Alternative(BaseModel):
    """1トークンの認識候補 (最有力候補のテキストを持つ)."""

    content: str = Field(description="認識候補のうち最有力の文字列")


class _Item(BaseModel):
    """results.items の1トークン (単語または句読点)."""

    type: str = Field(description="トークン種別 ('pronunciation' か 'punctuation')")
    alternatives: list[_Alternative] = Field(description="認識候補 (先頭が最有力)")
    start_time: str | None = Field(default=None, description="開始秒 (文字列). 句読点には無い")
    end_time: str | None = Field(default=None, description="終了秒 (文字列). 句読点には無い")


class _SpeakerItem(BaseModel):
    """speaker_labels 内の1トークン (時刻と話者の対応)."""

    start_time: str = Field(description="トークンの開始秒. results.items と突き合わせるキー")
    speaker_label: str = Field(description="話者ラベル (例: 'spk_0')")


class _SpeakerSegment(BaseModel):
    """同一話者の発話区間 (属するトークン群を持つ)."""

    items: list[_SpeakerItem] = Field(description="この発話区間に属するトークン群")


class _SpeakerLabels(BaseModel):
    """話者分離の結果 (発話区間のリスト)."""

    segments: list[_SpeakerSegment] = Field(description="話者ごとの発話区間")


class _Result(BaseModel):
    """文字起こし結果の本体 (トークン列と話者分離結果)."""

    items: list[_Item] = Field(description="単語・句読点のトークン列 (テキストと時刻)")
    speaker_labels: _SpeakerLabels | None = Field(
        default=None, description="話者分離の結果. 分離OFF時は欠ける"
    )


class Transcript(BaseModel):
    """AWS Transcribe のバッチ結果 JSON (使うフィールドのみ)."""

    results: _Result = Field(description="文字起こし結果の本体")
