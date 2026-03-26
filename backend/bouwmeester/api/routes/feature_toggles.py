"""Feature toggle API routes - per-eenheid feature visibility."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import AdminUser, get_optional_user
from bouwmeester.core.database import get_db
from bouwmeester.core.org_context import OrgContext, get_org_context
from bouwmeester.models.feature_toggle import FeatureToggle
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.person import Person
from bouwmeester.schema.feature_toggle import (
    EenheidFeatureConfig,
    FeatureToggleBulkUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feature-toggles", tags=["feature-toggles"])


@router.get("/my", response_model=dict[str, bool])
async def get_my_feature_config(
    person: Person | None = Depends(get_optional_user),
    org_ctx: OrgContext = Depends(get_org_context),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Return merged feature config for the current user's eenheden.

    A feature is enabled if it is enabled for ANY of the user's eenheden
    (OR logic). If no toggle row exists for a feature, default is True.
    """
    if person is None:
        return {}

    # Admins see everything
    if org_ctx.is_admin:
        return {}

    eenheid_ids = org_ctx.own_eenheid_ids
    if not eenheid_ids:
        return {}

    stmt = select(FeatureToggle).where(
        FeatureToggle.organisatie_eenheid_id.in_(eenheid_ids)
    )
    result = await db.execute(stmt)
    toggles = result.scalars().all()

    # Merge: OR logic across eenheden
    merged: dict[str, bool] = {}
    for toggle in toggles:
        key = toggle.feature_key
        if key not in merged:
            merged[key] = toggle.enabled
        elif toggle.enabled:
            merged[key] = True

    return merged


@router.get("/{eenheid_id}", response_model=EenheidFeatureConfig)
async def get_eenheid_feature_config(
    eenheid_id: UUID,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> EenheidFeatureConfig:
    """Get all feature toggles for a specific eenheid (admin only)."""
    eenheid = await db.get(OrganisatieEenheid, eenheid_id)
    if eenheid is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisatie-eenheid niet gevonden",
        )

    stmt = select(FeatureToggle).where(
        FeatureToggle.organisatie_eenheid_id == eenheid_id
    )
    result = await db.execute(stmt)
    toggles = result.scalars().all()

    features = {t.feature_key: t.enabled for t in toggles}

    return EenheidFeatureConfig(
        organisatie_eenheid_id=eenheid.id,
        organisatie_eenheid_naam=eenheid.naam,
        features=features,
    )


@router.put("/{eenheid_id}", response_model=EenheidFeatureConfig)
async def update_eenheid_feature_config(
    eenheid_id: UUID,
    data: FeatureToggleBulkUpdate,
    admin: AdminUser,
    db: AsyncSession = Depends(get_db),
) -> EenheidFeatureConfig:
    """Bulk update feature toggles for an eenheid (admin only).

    Creates new toggles if they don't exist, updates existing ones.
    """
    eenheid = await db.get(OrganisatieEenheid, eenheid_id)
    if eenheid is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organisatie-eenheid niet gevonden",
        )

    # Load existing toggles for this eenheid
    stmt = select(FeatureToggle).where(
        FeatureToggle.organisatie_eenheid_id == eenheid_id
    )
    result = await db.execute(stmt)
    existing = {t.feature_key: t for t in result.scalars().all()}

    for item in data.toggles:
        if item.feature_key in existing:
            existing[item.feature_key].enabled = item.enabled
        else:
            toggle = FeatureToggle(
                organisatie_eenheid_id=eenheid_id,
                feature_key=item.feature_key,
                enabled=item.enabled,
            )
            db.add(toggle)
            existing[item.feature_key] = toggle

    await db.flush()

    features = {key: t.enabled for key, t in existing.items()}

    return EenheidFeatureConfig(
        organisatie_eenheid_id=eenheid.id,
        organisatie_eenheid_naam=eenheid.naam,
        features=features,
    )
