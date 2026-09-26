"""Shared API dependencies and utilities."""

import logging
from uuid import UUID

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.authz import require
from bouwmeester.core.permissions import PermissionContext
from bouwmeester.repositories.tag import TagRepository
from bouwmeester.schema.tag import TagCreate

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_CSV_TYPES = {
    "text/csv",
    "application/csv",
    "text/plain",
    "application/vnd.ms-excel",
}


async def validate_csv_upload(file: UploadFile) -> bytes:
    """Validate and read a CSV upload. Returns file content bytes."""
    content_type = file.content_type or ""
    if content_type not in ALLOWED_CSV_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Ongeldig bestandstype: {content_type}. Alleen CSV is toegestaan."
            ),
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        max_mb = MAX_UPLOAD_SIZE // (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=(
                f"Bestand te groot ({len(content)} bytes). Maximum is {max_mb} MB."
            ),
        )

    return content


def require_found[T](obj: T | None, name: str = "Resource") -> T:
    """Return obj if not None, else raise 404."""
    if obj is None:
        raise HTTPException(
            status_code=404,
            detail=f"{name} not found",
        )
    return obj


def require_deleted(deleted: bool, name: str = "Resource") -> None:
    """Raise 404 if the delete operation found nothing."""
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"{name} not found",
        )


def validate_list[T: BaseModel](
    schema: type[T],
    items: list,
) -> list[T]:
    """Validate a list of ORM objects, skipping items that fail serialisation.

    This prevents a single broken record from crashing an entire list endpoint.
    Failures are logged with full Pydantic error details.
    """
    results: list[T] = []
    for item in items:
        try:
            results.append(schema.model_validate(item))
        except ValidationError:
            item_id = getattr(item, "id", "?")
            logger.warning(
                "Skipping %s id=%s: serialisation failed",
                schema.__name__,
                item_id,
                exc_info=True,
            )
    return results


async def resolve_tag_to_link(
    db: AsyncSession,
    perm_ctx: PermissionContext,
    *,
    tag_id: UUID | None,
    tag_name: str | None,
) -> UUID:
    """The tag to link, by id or by name; a new name needs ``tag:create``.

    Linking an existing tag is part of editing the item; a new name adds to
    the shared vocabulary, which is a permission of its own.
    """
    if tag_id is not None:
        return tag_id
    if not tag_name:
        raise HTTPException(status_code=400, detail="Provide tag_id or tag_name")
    repo = TagRepository(db)
    existing = await repo.get_by_name(tag_name)
    if existing is not None:
        return existing.id
    await require(db, perm_ctx, "tag:create", "tag")
    return (await repo.create(TagCreate(name=tag_name))).id
