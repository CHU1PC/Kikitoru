import asyncio
import json
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    """環境変数から読み込むアプリケーション設定."""

    FRONTEND_URL: str = Field(default="http://localhost:5173", description="フロントエンドの URL")

    DATABASE_URL: SecretStr = Field(default=..., description="データベース接続用の URL")
    DATABASE_SSL_MODE: str = Field(
        default="disable",
        description=(
            "asyncpg 用の PostgreSQL SSL モード. 'disable' (平文) は backend と DB が "
            "同一ホストにある場合 (例: docker-compose) のみ妥当. マネージド DB や "
            "ネットワーク越しの接続では 'verify-full' を使い、サーバ証明書とホスト名を検証する."
        ),
    )

    # AWS Transcribe / S3 (STT)
    AWS_REGION: str = Field(default="ap-northeast-1", description="S3 と Transcribe の AWS リージョン")
    S3_BUCKET: str = Field(default=..., description="音声ファイルを保存する S3 バケット名")

    # LLM Settings
    GOOGLE_API_KEY: SecretStr = Field(default=..., description="Google サービス用の API キー")
    LLM_CONCURRENT_LIMIT: int = Field(default=80, description="LLM への最大同時リクエスト数")
    LLM_TIMEOUT_SECONDS: int = Field(default=120, description="LLM 応答のタイムアウト秒数")

    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173"],
        description='CORS で許可するオリジン. カンマ区切り (a,b) または JSON 配列 (["a","b"]).',
    )

    # Google OAuth (sign-in)
    GOOGLE_CLIENT_ID: str = Field(
        ..., description="Google 認証用の OAuth 2.0 クライアント ID"
    )
    GOOGLE_CLIENT_SECRET: SecretStr = Field(
        ..., description="Google 認証用の OAuth 2.0 クライアントシークレット"
    )
    GOOGLE_REDIRECT_URI: str = Field(
        ...,
        description=(
            "OAuth 2.0 のリダイレクト URI. Google Cloud Console の "
            "'Authorized redirect URIs' に登録した値と完全一致する必要がある."
        ),
    )

    # Cookie / Session
    COOKIE_SECURE: bool = Field(
        default=True,
        description=(
            "セッション Cookie に Secure フラグを付ける. 本番 (HTTPS) では必須. "
            "ローカル HTTP 開発時のみ false にする."
        ),
    )
    SESSION_EXPIRY_DAYS: int = Field(
        default=1,
        description="新しいセッションが再ログインを要するまで有効な日数.",
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, value: object) -> object:
        """環境変数からカンマ区切り文字列または JSON 配列のどちらかを受け取る.

        Args:
            value (object): 環境変数からの生の値 (str) またはデフォルト (list).

        Returns:
            object: オリジン文字列のリスト. str でない場合は値をそのまま返す.

        Raises:
            ValueError: 値が JSON 配列に見えるが有効な JSON でない場合.
        """
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                try:
                    return json.loads(text)
                except json.JSONDecodeError as exc:
                    msg = f"ALLOWED_ORIGINS looks like JSON but is invalid: {text!r}"
                    raise ValueError(msg) from exc
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value

    # Rate limiting
    RATE_LIMIT_STORAGE_URI: str = Field(
        default="memory://",
        description=(
            "レート制限カウンタの保存先. 'memory://' はプロセスごと (単一ワーカーでは正しい). "
            "複数ワーカー/レプリカで動かす場合はカウンタを共有するため 'redis://...' に切り替える."
        ),
    )

    # Deployment
    ENABLE_DOCS: bool = Field(
        default=False,
        description="/docs, /redoc, /openapi.json を公開するか. 本番では false にする.",
    )


settings = Settings()  # type: ignore[call-arg]

llm_semaphore = asyncio.Semaphore(settings.LLM_CONCURRENT_LIMIT)
