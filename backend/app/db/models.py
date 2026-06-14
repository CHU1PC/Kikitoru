from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """A User of the system."""

    __tablename__ = "users"  # pyright: ignore[reportAssignmentType]

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="Unique identifier of the user")
    email: str | None = Field(default=None, max_length=320, description="Email address of the user")
    name: str = Field(default="", max_length=255, description="Full name of the user")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the user was created (UTC)",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=lambda: datetime.now(UTC)),
        description="Timestamp when the user was last updated (UTC)",
    )


class OAuthIdentity(SQLModel, table=True):
    """ユーザーの外部 IdP アカウント(provider, subjectのペア)."""

    __tablename__ = "oauth_identities"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_provider_subject"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True, description="Unique identifier of the OAuth identity")
    user_id: UUID = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        index=True,
        description="このOAuthIdentityが属するユーザーのID",
    )
    provider: str = Field(..., max_length=50, description="OAuth provider name (e.g., 'google', 'github')")
    subject: str = Field(
        ...,
        max_length=255,
        description="The unique identifier for the user within the provider's system"
    )
    email: str | None = Field(
        default=None,
        max_length=320,
        description="Email address from the OAuth provider, if available"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the OAuth identity was created (UTC)",
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
        description="このセッションが作成されたTimestamp (UTC)",
    )
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC) + timedelta(days=1),
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
        description="このセッションが期限切れになるTimestamp (UTC)",
    )
    last_seen_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False, onupdate=lambda: datetime.now(UTC)),
        description="このセッションが最後に使用されたTimestamp (UTC)",
    )
    revoked_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
        description="このセッションが削除されたTimestamp (UTC); null if active",
    )
    user_agent: str | None = Field(
        default=None,
        max_length=512,
        description="クライアントのブラウザから取得したUser agent文字列"
    )
    ip_address: str | None = Field(
        default=None,
        max_length=45,
        description="セッションを作成したクライアントのIPアドレス"
    )


class Summary(SQLModel, table=True):
    """Persisted meeting summary."""

    __tablename__ = "summaries"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        UniqueConstraint("user_id", "content_hash", name="uq_summaries_user_content_hash"),
    )

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        description="Unique identifier of the summary",
    )
    user_id: UUID = Field(
        foreign_key="users.id",
        ondelete="CASCADE",
        index=True,
        description="UserのID",
    )
    filename: str = Field(..., max_length=255, description="Name of the uploaded audio file")
    content_hash: str | None = Field(
        default=None,
        max_length=64,
        index=True,
        description=(
            "SHA-256 hex digest of the audio combined with num_speakers; "
            "makes re-uploads idempotent per speaker-count setting"
        ),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the summary was created (UTC)",
    )
    overall_summary: str = Field(..., description="Overall summary of the meeting")


class Topic(SQLModel, table=True):
    """A topic discussed in the meeting."""

    __tablename__ = "topics"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True, description="Primary key")
    summary_id: UUID = Field(
        foreign_key="summaries.id",
        ondelete="CASCADE",
        index=True,
        description="FK to the parent summary",
    )
    title: str = Field(..., description="Title of the topic")
    summary: str = Field(..., description="Detailed summary of the topic")


class Decision(SQLModel, table=True):
    """A decision made during the meeting."""

    __tablename__ = "decisions"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True, description="Primary key")
    summary_id: UUID = Field(
        foreign_key="summaries.id",
        ondelete="CASCADE",
        index=True,
        description="FK to the parent summary",
    )
    description: str = Field(..., description="Description of the decision")
    decided_by: str | None = Field(default=None, description="Person or group that made the decision")


class ActionItem(SQLModel, table=True):
    """An action item assigned during the meeting."""

    __tablename__ = "action_items"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True, description="Primary key")
    summary_id: UUID = Field(
        foreign_key="summaries.id",
        ondelete="CASCADE",
        index=True,
        description="FK to the parent summary",
    )
    description: str = Field(..., description="Description of the action item")
    assignee: str | None = Field(default=None, description="Person responsible for the action item")
    due_date: date | None = Field(default=None, description="Due date for the action item")
