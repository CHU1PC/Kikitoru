from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class UserRole(StrEnum):
    """ユーザーの役割."""

    user = "user"
    admin = "admin"


class UserStatus(StrEnum):
    """ユーザーの状態."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class User(SQLModel, table=True):
    """システムのユーザー."""

    __tablename__ = "users"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="ユーザーの一意識別子")
    email: str | None = Field(default=None, max_length=320, description="ユーザーのメールアドレス")
    name: str = Field(default="", max_length=255, description="ユーザーのフルネーム")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="ユーザーが作成された日時 (UTC)",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=lambda: datetime.now(UTC)),
        description="ユーザーが最後に更新された日時 (UTC)",
    )
    role: UserRole = Field(default=UserRole.user, description="ユーザーの役割")
    status: UserStatus = Field(default=UserStatus.pending, description="ユーザーの状態")


class OAuthIdentity(SQLModel, table=True):
    """ユーザーの外部 IdP アカウント(provider, subjectのペア)."""

    __tablename__ = "oauth_identities"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_provider_subject"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="OAuth identity の一意識別子")
    user_id: UUID = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        index=True,
        description="このOAuthIdentityが属するユーザーのID",
    )
    provider: str = Field(..., max_length=50, description="OAuth プロバイダ名 (例: 'google', 'github')")
    subject: str = Field(
        ...,
        max_length=255,
        description="プロバイダのシステム内でのユーザーの一意識別子"
    )
    email: str | None = Field(
        default=None,
        max_length=320,
        description="OAuth プロバイダから取得したメールアドレス (あれば)"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="OAuth identity が作成された日時 (UTC)",
    )


class UserSession(SQLModel, table=True):
    """ログインを維持するためのユーザーセッション."""

    __tablename__ = "user_sessions"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="セッションの一意識別子")
    user_id: UUID = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        index=True,
        description="このセッションが属するユーザーのID",
    )
    token_hash: str = Field(..., max_length=64, unique=True, description="SHA-256でハッシュ化されたセッショントークン")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="このセッションが作成された日時 (UTC)",
    )
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC) + timedelta(days=1),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
        description="このセッションが期限切れになる日時 (UTC)",
    )
    last_seen_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=lambda: datetime.now(UTC)),
        description="このセッションが最後に使用された日時 (UTC)",
    )
    revoked_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="このセッションが削除された日時 (UTC). アクティブなら null",
    )
    user_agent: str | None = Field(
        default=None,
        max_length=512,
        description="クライアントのブラウザから取得したユーザーエージェント文字列"
    )
    ip_address: str | None = Field(
        default=None,
        max_length=45,
        description="セッションを作成したクライアントのIPアドレス"
    )


class Summary(SQLModel, table=True):
    """永続化された会議の要約."""

    __tablename__ = "summaries"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("user_id", "content_hash", name="uq_summaries_user_content_hash"),
    )

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        description="要約の一意識別子",
    )
    user_id: UUID = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        index=True,
        description="ユーザーのID",
    )
    filename: str = Field(..., max_length=255, description="アップロードされた音声ファイル名")
    content_hash: str | None = Field(
        default=None,
        max_length=64,
        index=True,
        description=(
            "音声と num_speakers を組み合わせた SHA-256 hex ダイジェスト. "
            "話者数の設定ごとに再アップロードを冪等にする"
        ),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="要約が作成された日時 (UTC)",
    )
    overall_summary: str = Field(..., description="会議全体の要約")
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="要約が削除された日時 (UTC). アクティブなら None",
    )


class Topic(SQLModel, table=True):
    """会議で議論された議題."""

    __tablename__ = "topics"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True, description="主キー")
    summary_id: UUID = Field(
        foreign_key="summaries.id",
        ondelete="CASCADE",
        index=True,
        description="親 summary への外部キー",
    )
    title: str = Field(..., description="議題のタイトル")
    summary: str = Field(..., description="議題の詳細な要約")


class Decision(SQLModel, table=True):
    """会議中に決定された事項."""

    __tablename__ = "decisions"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True, description="主キー")
    summary_id: UUID = Field(
        foreign_key="summaries.id",
        ondelete="CASCADE",
        index=True,
        description="親 summary への外部キー",
    )
    description: str = Field(..., description="決定事項の説明")
    decided_by: str | None = Field(default=None, description="決定した人物またはグループ")


class ActionItem(SQLModel, table=True):
    """会議中に割り当てられたアクションアイテム."""

    __tablename__ = "action_items"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True, description="主キー")
    summary_id: UUID = Field(
        foreign_key="summaries.id",
        ondelete="CASCADE",
        index=True,
        description="親 summary への外部キー",
    )
    description: str = Field(..., description="アクションアイテムの説明")
    assignee: str | None = Field(default=None, description="アクションアイテムの担当者")
    due_date: date | None = Field(default=None, description="アクションアイテムの期限")
