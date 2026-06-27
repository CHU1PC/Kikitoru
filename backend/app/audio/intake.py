from __future__ import annotations

import hashlib
import re
import tempfile
import unicodedata
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import magic
from fastapi import HTTPException

if TYPE_CHECKING:
    from fastapi import UploadFile

MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB
_READ_CHUNK_SIZE = 1024 * 1024  # 1 MB
_SPOOL_MAX_BYTES = 8 * 1024 * 1024  # 8 MB
_MAGIC_SNIFF_BYTES = 8192
_MAX_FILENAME_LENGTH = 255

ALLOWED_MIME_TYPES = frozenset({
    "audio/mpeg",
    "audio/mp4",
    "audio/x-m4a",
    "audio/wav",
    "audio/x-wav",
    "audio/flac",
    "audio/x-flac",
})

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_magic_mime = magic.Magic(mime=True)


def sanitize_filename(filename: str | None) -> str:
    """アップロードファイル名を安全で長さ制限のある basename に整える.

    ディレクトリ要素を除去し、制御文字を削除し、Unicode を NFC に正規化し、
    Summary.filename カラムに収まるよう長さを制限する.

    Args:
        filename (str | None): クライアントから渡された生のファイル名.

    Returns:
        str: 保存・表示に使える安全で空でないファイル名.
    """
    if not filename:
        return "unknown"
    name = PurePosixPath(filename).name
    name = unicodedata.normalize("NFC", name)
    name = _CONTROL_CHAR_RE.sub("", name).strip()
    if not name:
        return "unknown"
    if len(name) > _MAX_FILENAME_LENGTH:
        if "." in name:
            stem, _, ext = name.rpartition(".")
            ext = ext[:50]
            name = stem[: _MAX_FILENAME_LENGTH - len(ext) - 1] + "." + ext
        else:
            name = name[:_MAX_FILENAME_LENGTH]
    return name


async def spool_upload(file: UploadFile) -> tuple[tempfile.SpooledTemporaryFile[bytes], str, str]:
    """アップロードを spooled 一時ファイルに書き出しつつ、ハッシュ化と MIME 判定を同じ走査で行う.

    チャンク単位で読み、ファイル全体をメモリに保持しない. 小さいアップロードはメモリ上に残り、
    _SPOOL_MAX_BYTES を超えるとディスクに退避する. SHA-256 ダイジェストと先頭バイト
    (MIME sniff 用) を同じ1回の走査で計算するため、内容は1度しか読まない.

    Args:
        file (UploadFile): 受信したファイル.

    Returns:
        tuple[SpooledTemporaryFile, str, str]: 先頭に巻き戻した一時ファイル、その内容の
            SHA-256 hex ダイジェスト、libmagic が判定した MIME タイプ.

    Raises:
        HTTPException: 累積サイズが MAX_UPLOAD_BYTES を超えた場合は 413.
    """
    spooled: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_BYTES)  # noqa: SIM115
    hasher = hashlib.sha256()
    head = bytearray()
    total = 0
    while chunk := await file.read(_READ_CHUNK_SIZE):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            spooled.close()
            raise HTTPException(status_code=413, detail="File exceeds the 200 MB limit")
        hasher.update(chunk)
        if len(head) < _MAGIC_SNIFF_BYTES:
            head.extend(chunk[: _MAGIC_SNIFF_BYTES - len(head)])
        spooled.write(chunk)

    spooled.seek(0)
    detected_mime = _magic_mime.from_buffer(bytes(head))
    return spooled, hasher.hexdigest(), detected_mime
