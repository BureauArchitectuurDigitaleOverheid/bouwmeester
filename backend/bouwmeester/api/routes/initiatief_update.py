"""API routes for InitiatiefUpdatePost (publication posts on an initiatief)."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.api.deps import require_found
from bouwmeester.api.routes.initiatief import _require_access
from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.permissions import (
    PermissionContext,
    get_permission_context,
)
from bouwmeester.models.initiatief_update import InitiatiefUpdatePost
from bouwmeester.repositories.initiatief import InitiatiefRepository
from bouwmeester.schema.initiatief_update import (
    InitiatiefUpdatePostCreate,
    InitiatiefUpdatePostEdit,
    InitiatiefUpdatePostResponse,
)

router = APIRouter(prefix="/initiatieven", tags=["initiatief-updates"])


def _to_response(post: InitiatiefUpdatePost) -> InitiatiefUpdatePostResponse:
    return InitiatiefUpdatePostResponse(
        id=post.id,
        initiatief_id=post.initiatief_id,
        titel=post.titel,
        body=post.body,
        published_at=post.published_at,
        published_by_id=post.published_by_id,
        published_by_naam=(post.published_by.naam if post.published_by else None),
        created_at=post.created_at,
        updated_at=post.updated_at,
    )


async def _load_post(
    db: AsyncSession, initiatief_id: UUID, post_id: UUID
) -> InitiatiefUpdatePost | None:
    stmt = (
        select(InitiatiefUpdatePost)
        .where(
            InitiatiefUpdatePost.id == post_id,
            InitiatiefUpdatePost.initiatief_id == initiatief_id,
        )
        .options(selectinload(InitiatiefUpdatePost.published_by))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


@router.get(
    "/{initiatief_id}/updates",
    response_model=list[InitiatiefUpdatePostResponse],
)
async def list_updates(
    initiatief_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> list[InitiatiefUpdatePostResponse]:
    """All updates (drafts + published) for members; viewers see same."""
    repo = InitiatiefRepository(db)
    require_found(await repo.get_by_id(initiatief_id), "Initiatief")
    await _require_access(repo, initiatief_id, current_user, perm_ctx, "viewer")

    stmt = (
        select(InitiatiefUpdatePost)
        .where(InitiatiefUpdatePost.initiatief_id == initiatief_id)
        .options(selectinload(InitiatiefUpdatePost.published_by))
        .order_by(InitiatiefUpdatePost.created_at.desc())
    )
    result = await db.execute(stmt)
    return [_to_response(p) for p in result.scalars().all()]


@router.post(
    "/{initiatief_id}/updates",
    response_model=InitiatiefUpdatePostResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_update(
    initiatief_id: UUID,
    data: InitiatiefUpdatePostCreate,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> InitiatiefUpdatePostResponse:
    repo = InitiatiefRepository(db)
    require_found(await repo.get_by_id(initiatief_id), "Initiatief")
    await _require_access(repo, initiatief_id, current_user, perm_ctx, "contributor")

    post = InitiatiefUpdatePost(
        initiatief_id=initiatief_id,
        titel=data.titel,
        body=data.body,
    )
    if data.publish:
        post.published_at = datetime.now(UTC)
        post.published_by_id = current_user.id if current_user else None

    db.add(post)
    await db.flush()
    await db.refresh(post)
    await db.refresh(post, attribute_names=["published_by"])
    return _to_response(post)


@router.put(
    "/{initiatief_id}/updates/{post_id}",
    response_model=InitiatiefUpdatePostResponse,
)
async def edit_update(
    initiatief_id: UUID,
    post_id: UUID,
    data: InitiatiefUpdatePostEdit,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> InitiatiefUpdatePostResponse:
    repo = InitiatiefRepository(db)
    await _require_access(repo, initiatief_id, current_user, perm_ctx, "contributor")
    post = require_found(await _load_post(db, initiatief_id, post_id), "Update")
    payload = data.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(post, key, value)
    await db.flush()
    await db.refresh(post)
    await db.refresh(post, attribute_names=["published_by"])
    return _to_response(post)


@router.post(
    "/{initiatief_id}/updates/{post_id}/publish",
    response_model=InitiatiefUpdatePostResponse,
)
async def publish_update(
    initiatief_id: UUID,
    post_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> InitiatiefUpdatePostResponse:
    repo = InitiatiefRepository(db)
    await _require_access(repo, initiatief_id, current_user, perm_ctx, "contributor")
    post = require_found(await _load_post(db, initiatief_id, post_id), "Update")
    post.published_at = datetime.now(UTC)
    post.published_by_id = current_user.id if current_user else None
    await db.flush()
    await db.refresh(post)
    await db.refresh(post, attribute_names=["published_by"])
    return _to_response(post)


@router.post(
    "/{initiatief_id}/updates/{post_id}/unpublish",
    response_model=InitiatiefUpdatePostResponse,
)
async def unpublish_update(
    initiatief_id: UUID,
    post_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> InitiatiefUpdatePostResponse:
    repo = InitiatiefRepository(db)
    await _require_access(repo, initiatief_id, current_user, perm_ctx, "contributor")
    post = require_found(await _load_post(db, initiatief_id, post_id), "Update")
    # Keep published_by_id as audit trail of last publisher; republishing
    # overwrites it again.
    post.published_at = None
    await db.flush()
    await db.refresh(post)
    await db.refresh(post, attribute_names=["published_by"])
    return _to_response(post)


@router.delete(
    "/{initiatief_id}/updates/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_update(
    initiatief_id: UUID,
    post_id: UUID,
    current_user: OptionalUser,
    db: AsyncSession = Depends(get_db),
    perm_ctx: PermissionContext = Depends(get_permission_context),
) -> None:
    repo = InitiatiefRepository(db)
    await _require_access(repo, initiatief_id, current_user, perm_ctx, "contributor")
    post = await _load_post(db, initiatief_id, post_id)
    if post is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Update niet gevonden"
        )
    await db.delete(post)
    await db.flush()
