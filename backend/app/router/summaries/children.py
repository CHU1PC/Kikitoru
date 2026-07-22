from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.db.models import ActionItem, Decision, Topic
from app.db.summaries import get_owned_summary
from app.db.summary_edits import add_child, delete_child, load_owned_child, update_child
from app.dependencies import ApprovedUser, DbSessionDep
from app.schema.summaries import (
    ActionItemCreate,
    ActionItemEdit,
    ActionItemResponse,
    DecisionCreate,
    DecisionEdit,
    DecisionResponse,
    TopicCreate,
    TopicEdit,
    TopicResponse,
)

router = APIRouter(tags=["summaries"])


@router.post("/{summary_id}/topics", status_code=201)
async def create_topic_endpoint(
    summary_id: UUID, body: TopicCreate, db_session: DbSessionDep, user: ApprovedUser
) -> TopicResponse:
    """要約に議題を1件追加する. 要約が見つからなければ 404.

    Args:
        summary_id (UUID): 親要約の ID.
        body (TopicCreate): 追加する議題.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Returns:
        TopicResponse: 追加された議題 (id 付き).

    Raises:
        HTTPException: 404 - 要約が見つからない場合.
    """
    summary = await get_owned_summary(db_session, user.id, summary_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    topic = Topic(summary_id=summary_id, **body.model_dump())
    created = await add_child(db_session, topic)
    return TopicResponse.model_validate(created)


@router.patch("/{summary_id}/topics/{topic_id}")
async def update_topic_endpoint(
    summary_id: UUID, topic_id: int, body: TopicEdit, db_session: DbSessionDep, user: ApprovedUser
) -> TopicResponse:
    """議題を部分更新する. 見つからなければ 404, 必須を null にすると 422.

    Args:
        summary_id (UUID): 親要約の ID.
        topic_id (int): 議題の ID.
        body (TopicEdit): 更新内容.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Returns:
        TopicResponse: 更新後の議題.

    Raises:
        HTTPException: 404 - 議題が見つからない場合. 422 - 必須フィールドを null にした場合.
    """
    topic = await load_owned_child(db_session, user.id, summary_id, Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    try:
        updated = await update_child(db_session, topic, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TopicResponse.model_validate(updated)


@router.delete("/{summary_id}/topics/{topic_id}", status_code=204)
async def delete_topic_endpoint(
    summary_id: UUID, topic_id: int, db_session: DbSessionDep, user: ApprovedUser
) -> None:
    """議題を1件削除する. 見つからなければ 404.

    Args:
        summary_id (UUID): 親要約の ID.
        topic_id (int): 議題の ID.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Raises:
        HTTPException: 404 - 議題が見つからない場合.
    """
    topic = await load_owned_child(db_session, user.id, summary_id, Topic, topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    await delete_child(db_session, topic)


@router.post("/{summary_id}/decisions", status_code=201)
async def create_decision_endpoint(
    summary_id: UUID, body: DecisionCreate, db_session: DbSessionDep, user: ApprovedUser
) -> DecisionResponse:
    """要約に決定事項を1件追加する. 要約が見つからなければ 404.

    Args:
        summary_id (UUID): 親要約の ID.
        body (DecisionCreate): 追加する決定事項.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Returns:
        DecisionResponse: 追加された決定事項 (id 付き).

    Raises:
        HTTPException: 404 - 要約が見つからない場合.
    """
    summary = await get_owned_summary(db_session, user.id, summary_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    decision = Decision(summary_id=summary_id, **body.model_dump())
    created = await add_child(db_session, decision)
    return DecisionResponse.model_validate(created)


@router.patch("/{summary_id}/decisions/{decision_id}")
async def update_decision_endpoint(
    summary_id: UUID, decision_id: int, body: DecisionEdit, db_session: DbSessionDep, user: ApprovedUser
) -> DecisionResponse:
    """決定事項を部分更新する. 見つからなければ 404, 必須を null にすると 422.

    Args:
        summary_id (UUID): 親要約の ID.
        decision_id (int): 決定事項の ID.
        body (DecisionEdit): 更新内容.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Returns:
        DecisionResponse: 更新後の決定事項.

    Raises:
        HTTPException: 404 - 決定事項が見つからない場合. 422 - 必須フィールドを null にした場合.
    """
    decision = await load_owned_child(db_session, user.id, summary_id, Decision, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    try:
        updated = await update_child(db_session, decision, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DecisionResponse.model_validate(updated)


@router.delete("/{summary_id}/decisions/{decision_id}", status_code=204)
async def delete_decision_endpoint(
    summary_id: UUID, decision_id: int, db_session: DbSessionDep, user: ApprovedUser
) -> None:
    """決定事項を1件削除する. 見つからなければ 404.

    Args:
        summary_id (UUID): 親要約の ID.
        decision_id (int): 決定事項の ID.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Raises:
        HTTPException: 404 - 決定事項が見つからない場合.
    """
    decision = await load_owned_child(db_session, user.id, summary_id, Decision, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    await delete_child(db_session, decision)


@router.post("/{summary_id}/action-items", status_code=201)
async def create_action_item_endpoint(
    summary_id: UUID, body: ActionItemCreate, db_session: DbSessionDep, user: ApprovedUser
) -> ActionItemResponse:
    """要約にアクションアイテムを1件追加する. 要約が見つからなければ 404.

    Args:
        summary_id (UUID): 親要約の ID.
        body (ActionItemCreate): 追加するアクションアイテム.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Returns:
        ActionItemResponse: 追加されたアクションアイテム (id 付き).

    Raises:
        HTTPException: 404 - 要約が見つからない場合.
    """
    summary = await get_owned_summary(db_session, user.id, summary_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    action_item = ActionItem(summary_id=summary_id, **body.model_dump())
    created = await add_child(db_session, action_item)
    return ActionItemResponse.model_validate(created)


@router.patch("/{summary_id}/action-items/{action_item_id}")
async def update_action_item_endpoint(
    summary_id: UUID, action_item_id: int, body: ActionItemEdit, db_session: DbSessionDep, user: ApprovedUser
) -> ActionItemResponse:
    """アクションアイテムを部分更新する. 見つからなければ 404, 必須を null にすると 422.

    Args:
        summary_id (UUID): 親要約の ID.
        action_item_id (int): アクションアイテムの ID.
        body (ActionItemEdit): 更新内容.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Returns:
        ActionItemResponse: 更新後のアクションアイテム.

    Raises:
        HTTPException: 404 - アクションアイテムが見つからない場合. 422 - 必須フィールドを null にした場合.
    """
    action_item = await load_owned_child(db_session, user.id, summary_id, ActionItem, action_item_id)
    if action_item is None:
        raise HTTPException(status_code=404, detail="Action item not found")
    try:
        updated = await update_child(db_session, action_item, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ActionItemResponse.model_validate(updated)


@router.delete("/{summary_id}/action-items/{action_item_id}", status_code=204)
async def delete_action_item_endpoint(
    summary_id: UUID, action_item_id: int, db_session: DbSessionDep, user: ApprovedUser
) -> None:
    """アクションアイテムを1件削除する. 見つからなければ 404.

    Args:
        summary_id (UUID): 親要約の ID.
        action_item_id (int): アクションアイテムの ID.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Raises:
        HTTPException: 404 - アクションアイテムが見つからない場合.
    """
    action_item = await load_owned_child(db_session, user.id, summary_id, ActionItem, action_item_id)
    if action_item is None:
        raise HTTPException(status_code=404, detail="Action item not found")
    await delete_child(db_session, action_item)
