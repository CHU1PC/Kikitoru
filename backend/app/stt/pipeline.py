import asyncio
import uuid
from typing import IO

import boto3
from loguru import logger

from app.settings import settings
from app.storage import s3
from app.stt.schema import Transcript
from app.stt.types import Segment

transcribe = boto3.client("transcribe", region_name=settings.AWS_REGION)  # pyright: ignore[reportUnknownMemberType]


async def transcribe_with_diarization(audio: IO[bytes], num_speakers: int | None = None) -> list[Segment]:
    """AWS Transcribeを用いて音声を文字起こしし、話者を分離する.

    S3に音声ファイルをアップロードし、AWS Transcribeのバッチジョブを開始する。
    ジョブが完了するまで待機し、結果を取得して話者分離されたセグメントのリストに変換する。
    最後に、S3上の音声ファイルと文字起こし結果を削除する。

    Args:
        audio (IO[bytes]): 音声ファイルのバイナリストリーム
        num_speakers (int | None, optional): 話者数. Defaults to None.

    Returns:
        list[Segment]: 話者分離されたセグメントのリスト
    """
    job_name = f"transcription-job-{uuid.uuid4()}"
    audio_key = f"audio/{job_name}"
    transcript_key = f"transcripts/{job_name}.json"

    try:
        await asyncio.to_thread(s3.upload_fileobj, audio, settings.S3_BUCKET, audio_key)

        await asyncio.to_thread(
            transcribe.start_transcription_job,
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": f"s3://{settings.S3_BUCKET}/{audio_key}"},
            LanguageCode="ja-JP",
            OutputBucketName=settings.S3_BUCKET,
            OutputKey=transcript_key,
            Settings={
                "ShowSpeakerLabels": True,
                "MaxSpeakerLabels": min(max(2, num_speakers or 10), 10)
            } if num_speakers != 1 else {},
        )  # MaxSpeakerLabels は 2 以上である必要があるため、num_speakers が 1 の場合は話者分離を無効化する

        await _wait_for_completion(job_name)

        obj = await asyncio.to_thread(
            s3.get_object, Bucket=settings.S3_BUCKET, Key=transcript_key
        )
        body = await asyncio.to_thread(obj["Body"].read)
        transcript = Transcript.model_validate_json(body)
        return _to_segments(transcript)
    finally:
        await asyncio.to_thread(_cleanup, job_name, audio_key, transcript_key)


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
            raise RuntimeError(msg)
    msg = f"Transcription job {job_name} did not complete within {max_attempts * poll_interval} seconds."
    raise TimeoutError(msg)


def _cleanup(job_name: str, audio_key: str, transcript_key: str) -> None:
    """AWS Transcribe のジョブと S3 上の音声ファイル・文字起こし結果を削除するクリーンアップ関数.

    Args:
        job_name (str): AWS Transcribe のジョブ名
        audio_key (str): S3 にアップロードした音声ファイルのキー
        transcript_key (str): S3 にアップロードした文字起こし結果のキー
    """
    for key in (audio_key, transcript_key):
        try:
            s3.delete_object(Bucket=settings.S3_BUCKET, Key=key)
        except Exception as e:  # noqa: BLE001 - どのような例外でも処理を続けたい
            logger.error(f"Error deleting {key}: {e}")
    try:
        transcribe.delete_transcription_job(TranscriptionJobName=job_name)
    except Exception as e:  # noqa: BLE001 - どのような例外でも処理を続けたい
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
                        start=current_start,
                        end=current_end,
                        speaker_label=f"Speaker {int(current_speaker.removeprefix('spk_')) + 1}",
                        text=current_text
                    )
                )
            # 新しいセグメントの初期化
            current_speaker, current_text, current_start, current_end = speaker, content, start, end
        else:  # 同じ話者の場合、テキストを追加して終了時間を更新する
            current_text += content
            current_end = end

    if current_speaker:  # 最後のセグメントを追加する
        segments.append(
            Segment(
                start=current_start,
                end=current_end,
                speaker_label=f"Speaker {int(current_speaker.removeprefix('spk_')) + 1}",
                text=current_text
            )
        )
    return segments
