"""Shared helpers for temporal record rotation.

Temporal tables follow the pattern: each record has ``geldig_van`` / ``geldig_tot``
columns.  The "active" record is the one where ``geldig_tot IS NULL``.  Rotating
means closing the current active record and inserting a new one.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InspectionAttr


async def rotate_temporal_record(
    session: AsyncSession,
    model_cls: type,
    fk_column: InspectionAttr,
    owner_id: UUID,
    effective: date,
    new_record: Any,
) -> None:
    """Close the active record and insert a new one.

    Args:
        session: The async DB session.
        model_cls: The SQLAlchemy model class (e.g. ``CorpusNodeTitle``).
        fk_column: The FK column attribute (e.g. ``CorpusNodeTitle.node_id``).
        owner_id: The FK value to filter on.
        effective: The date to set as ``geldig_tot`` on the old record
                   and ``geldig_van`` on the new.
        new_record: The new model instance to add.  May be ``None`` to
                    only close the active record without inserting.
    """
    stmt = select(model_cls).where(
        fk_column == owner_id,
        model_cls.geldig_tot.is_(None),
    )
    result = await session.execute(stmt)
    active = result.scalar_one_or_none()
    if active:
        active.geldig_tot = effective
    if new_record is not None:
        session.add(new_record)


async def close_active_records(
    session: AsyncSession,
    model_classes: list[tuple[type, InspectionAttr]],
    owner_id: UUID,
    end_date: date,
) -> None:
    """Close all active temporal records for a set of model classes.

    Args:
        session: The async DB session.
        model_classes: List of ``(ModelClass, fk_column)`` tuples.
        owner_id: The FK value to filter on.
        end_date: The date to set as ``geldig_tot``.
    """
    for model_cls, fk_column in model_classes:
        stmt = select(model_cls).where(
            fk_column == owner_id,
            model_cls.geldig_tot.is_(None),
        )
        result = await session.execute(stmt)
        for record in result.scalars().all():
            record.geldig_tot = end_date
