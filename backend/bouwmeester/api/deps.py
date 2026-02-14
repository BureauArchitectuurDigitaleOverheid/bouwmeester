"""Shared API dependencies and utilities."""

import logging

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel, ValidationError

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
