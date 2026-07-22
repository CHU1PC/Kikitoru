from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    import tempfile
    from uuid import UUID

    from mypy_boto3_s3 import S3Client

from app.settings import settings

s3: S3Client = boto3.client("s3", region_name=settings.AWS_REGION)  # pyright: ignore[reportUnknownMemberType]

UPLOAD_PREFIX = "uploads"
TRANSCRIPT_PREFIX = "transcripts"


def media_uri(key: str) -> str:
    """S3上のオブジェクトのURIを返す.

    Args:
        key (str): S3上のオブジェクトのキー

    Returns:
        str: S3上のオブジェクトのURI
    """
    return f"s3://{settings.S3_BUCKET}/{key}"


async def persist_upload(spooled: tempfile.SpooledTemporaryFile[bytes], job_id: UUID) -> str:
    """Spool したアップロード(音声/動画)を S3 (uploads/{job_id}) に永続化し, そのkeyを返す.

    Args:
        spooled (tempfile.SpooledTemporaryFile[bytes]): Spool したファイル
        job_id (UUID): TranscriptionJob の ID

    Returns:
        str: S3上のオブジェクトのキー
    """
    key = f"{UPLOAD_PREFIX}/{job_id}"
    spooled.seek(0)
    await asyncio.to_thread(s3.upload_fileobj, spooled, settings.S3_BUCKET, key)
    return key


async def get_object_bytes(key: str) -> bytes:
    """S3 オブジェクトの中身を bytes で返す.

    Args:
        key (str): S3上のオブジェクトのキー

    Returns:
        bytes: S3オブジェクトの中身
    """
    obj = await asyncio.to_thread(s3.get_object, Bucket=settings.S3_BUCKET, Key=key)
    return await asyncio.to_thread(obj["Body"].read)


async def delete_object(key: str) -> None:
    """S3 オブジェクトを削除する.

    Args:
        key (str): S3上のオブジェクトのキー
    """
    await asyncio.to_thread(s3.delete_object, Bucket=settings.S3_BUCKET, Key=key)
