from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func
from sqlmodel import col, select

from app.db.models import Summary
from app.db.summaries import build_summary_read
from app.dependencies import ApprovedUser, DbSessionDep
from app.schema.summaries import (
    SummaryListItem,
    SummaryPageResponse,
    SummaryResponse,
)

router = APIRouter(prefix="/summaries", tags=["summaries"])


@router.get("")
async def list_summaries_endpoint(
    db_session: DbSessionDep,
    user: ApprovedUser,
    limit: Annotated[int, Query(ge=1, le=100, description="1ページあたりの件数")] = 50,
    offset: Annotated[int, Query(ge=0, description="スキップする件数")] = 0,
) -> SummaryPageResponse:
    """日付順に並べた要約のページを返す.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー。FastAPI の依存性注入で解決される.
        limit (int): 1ページあたりの要約の最大数. 1〜100 の範囲で指定する必要がある. default: 50
        offset (int): ページの先頭からスキップする要約の数. 0以上の整数で指定する必要がある. default: 0

    Returns:
        SummaryPageResponse: ページ内の要約のリストと、総数、ページサイズ、オフセットを含むページ情報を返す.
    """
    total_col = func.count().over().label("total")
    rows = (
        await db_session.exec(  # limit と offset を使ってページングされた Summary のリストを取得する
            select(Summary, total_col)
            .where(col(Summary.user_id) == user.id)
            .order_by(col(Summary.created_at).desc(), col(Summary.id).desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    if rows:
        total = int(rows[0][1])
        items = [SummaryListItem.model_validate(summary) for summary, _ in rows]
    else:
        total = (
            await db_session.exec(
                select(func.count()).select_from(Summary).where(col(Summary.user_id) == user.id)
            )
        ).one()
        items = []

    return SummaryPageResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{summary_id}")
async def get_summary_endpoint(summary_id: UUID, db_session: DbSessionDep, user: ApprovedUser) -> SummaryResponse:
    """一つの要約の詳細を返す. 存在しない要約や他のユーザーの要約は 404 を返す.

    Args:
        summary_id (UUID): 要約の ID.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー。FastAPI の依存性注入で解決される.

    Returns:
        SummaryResponse: 要約の詳細情報.

    Raises:
        HTTPException: 404 - 要約が存在しない場合、または他のユーザーの要約にアクセスしようとした場合
    """
    row = await db_session.get(Summary, summary_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Summary not found")

    return await build_summary_read(db_session, row)
