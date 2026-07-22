import asyncio
import uuid

import boto3
from loguru import logger

from app.settings import settings
from app.storage import TRANSCRIPT_PREFIX, delete_object, get_object_bytes, media_uri
from app.stt.schema import Transcript
from app.stt.types import Segment

transcribe = boto3.client("transcribe", region_name=settings.AWS_REGION)  # pyright: ignore[reportUnknownMemberType]


async def transcribe_with_diarization(media_key: str, num_speakers: int | None = None) -> list[Segment]:
    """S3 上の音声/動画 (media_key) を AWS Transcribe で文字起こしし, 話者分離する.

    音声は既に S3 (uploads/{job_id}) に永続化されている前提で, MediaFileUri から直接読む

    Args:
        media_key (str): S3 上の音声/動画のキー
        num_speakers (int | None, optional): 話者数. Defaults to None.

    Returns:
        list[Segment]: 話者分離されたセグメントのリスト
    """
    job_name = f"transcription-job-{uuid.uuid4()}"
    transcript_key = f"{TRANSCRIPT_PREFIX}/{job_name}.json"

    try:
        await asyncio.to_thread(
            transcribe.start_transcription_job,
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": media_uri(media_key)},
            LanguageCode="ja-JP",
            OutputBucketName=settings.S3_BUCKET,
            OutputKey=transcript_key,
            Settings={
                "ShowSpeakerLabels": True,
                "MaxSpeakerLabels": min(max(2, num_speakers or 10), 10)
            } if num_speakers != 1 else {},
        )

        await _wait_for_completion(job_name)

        body = await get_object_bytes(transcript_key)
        transcript = Transcript.model_validate_json(body)
        return _to_segments(transcript)
    finally:
        await _cleanup(job_name, transcript_key)


async def _wait_for_completion(job_name: str, *, max_attempts: int = 360, poll_interval: int = 5) -> None:
    """AWS Transcribe のジョブが完了するまで待機する.

    Args:
        job_name (str): AWS Transcribe のジョブ名
        max_attempts (int, optional): 最大ポーリング回数. Defaults to 360.
        poll_interval (int, optional): ポーリング間隔(秒). Defaults to 5.

    Raises:
        RuntimeError: ジョブが失敗した場合に送出される
        TimeoutError: ジョブが完了する前に最大ポーリング回数に達した場合に送出される
    """
    for _ in range(max_attempts):
        await asyncio.sleep(poll_interval)  # Wait for the specified interval before checking again
        response = await asyncio.to_thread(transcribe.get_transcription_job, TranscriptionJobName=job_name)
        status = response["TranscriptionJob"].get("TranscriptionJobStatus")
        if status == "COMPLETED":
            return
        if status == "FAILED":
            reason = response["TranscriptionJob"].get("FailureReason", "Unknown reason")
            msg = f"Transcription job {job_name} failed: {reason}"
            logger.error(msg)
            raise RuntimeError(msg)
    msg = f"Transcription job {job_name} did not complete within {max_attempts * poll_interval} seconds."
    raise TimeoutError(msg)


async def _cleanup(job_name: str, transcript_key: str) -> None:
    """Transcribe の結果 JSON とジョブを削除する.

    Args:
        job_name (str): AWS Transcribe のジョブ名
        transcript_key (str): S3上のトランスクリプト JSON のキー
    """
    try:
        await delete_object(transcript_key)
    except Exception as e:  # ruff:ignore[blind-except] - どのような例外でも処理を続けたい
        logger.error(f"Error deleting {transcript_key}: {e}")
    try:
        await asyncio.to_thread(transcribe.delete_transcription_job, TranscriptionJobName=job_name)
    except Exception as e:  # ruff:ignore[blind-except] - どのような例外でも処理を続けたい
        logger.error(f"Error deleting transcription job {job_name}: {e}")


def _to_segments(transcript: Transcript) -> list[Segment]:
    """AWS Transcribe のバッチ結果 JSON を話者分離されたセグメントのリストに変換する.

    Args:
        transcript (Transcript): AWS Transcribe のバッチ結果 JSON (使うフィールドのみ)

    Returns:
        list[Segment]: 話者分離されたセグメントのリスト
    """
    speaker_by_start: dict[str, str] = {}  # start_time -> speaker_label
    if transcript.results.speaker_labels:  # 話者分離が有効な場合、speaker_labels が存在する
        for segment in transcript.results.speaker_labels.segments:
            for item in segment.items:
                speaker_by_start[item.start_time] = item.speaker_label

    segments: list[Segment] = []
    current_speaker: str | None = None
    current_text, current_start, current_end = "", 0.0, 0.0

    for item in transcript.results.items:
        content = item.alternatives[0].content
        if item.type == "punctuation" or item.start_time is None or item.end_time is None:
            current_text += content  # 句読点は話者分離の対象外なので、現在の話者のテキストに追加する
            continue
        speaker = speaker_by_start.get(item.start_time, current_speaker or "spk_0")
        start, end = float(item.start_time), float(item.end_time)
        if speaker != current_speaker:  # 話者が変わった場合、現在のセグメントを確定して新しいセグメントを開始する
            if current_speaker:
                segments.append(
                    Segment(
                        start_ms=round(current_start * 1000),
                        end_ms=round(current_end * 1000),
                        speaker_label=f"Speaker {int(current_speaker.removeprefix('spk_')) + 1}",
                        text=current_text
                    )
                )
                current_text = ""  # 確定したセグメントのテキストはリセット
            # 新しいセグメントの初期化。先頭に溜めた句読点が current_text に残っていれば += で引き継ぐ
            current_speaker, current_start, current_end = speaker, start, end
            current_text += content
        else:  # 同じ話者の場合、テキストを追加して終了時間を更新する
            current_text += content
            current_end = end

    if current_speaker:  # 最後のセグメントを追加する
        segments.append(
            Segment(
                start_ms=round(current_start * 1000),
                end_ms=round(current_end * 1000),
                speaker_label=f"Speaker {int(current_speaker.removeprefix('spk_')) + 1}",
                text=current_text
            )
        )
    return segments
