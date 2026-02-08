"""API routes for tags."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.api.deps import require_deleted, require_found
from bouwmeester.core.database import get_db
from bouwmeester.repositories.tag import TagRepository
from bouwmeester.schema.tag import (
    TagCreate,
    TagResponse,
    TagTreeResponse,
    TagUpdate,
)

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[TagResponse])
async def list_tags(db: AsyncSession = Depends(get_db)) -> list[TagResponse]:
    repo = TagRepository(db)
    tags = await repo.get_all()
    return [TagResponse.model_validate(t) for t in tags]


@router.get("/tree", response_model=list[TagTreeResponse])
async def get_tag_tree(db: AsyncSession = Depends(get_db)) -> list[TagTreeResponse]:
    repo = TagRepository(db)
    tags = await repo.get_tree()
    return [TagTreeResponse.model_validate(t) for t in tags]


@router.get("/search", response_model=list[TagResponse])
async def search_tags(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
) -> list[TagResponse]:
    repo = TagRepository(db)
    tags = await repo.search(q)
    return [TagResponse.model_validate(t) for t in tags]


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    data: TagCreate, db: AsyncSession = Depends(get_db)
) -> TagResponse:
    repo = TagRepository(db)
    tag = await repo.create(data)
    return TagResponse.model_validate(tag)


@router.get("/{tag_id}", response_model=TagResponse)
async def get_tag(tag_id: UUID, db: AsyncSession = Depends(get_db)) -> TagResponse:
    repo = TagRepository(db)
    tag = require_found(await repo.get_by_id(tag_id), "Tag")
    return TagResponse.model_validate(tag)


@router.put("/{tag_id}", response_model=TagResponse)
async def update_tag(
    tag_id: UUID, data: TagUpdate, db: AsyncSession = Depends(get_db)
) -> TagResponse:
    repo = TagRepository(db)
    tag = require_found(await repo.update(tag_id, data), "Tag")
    return TagResponse.model_validate(tag)


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: UUID, db: AsyncSession = Depends(get_db)) -> None:
    repo = TagRepository(db)
    require_deleted(await repo.delete(tag_id), "Tag")
