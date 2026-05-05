"""Public (unauthenticated) endpoints for an initiatief community page."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.core.database import get_db
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.initiatief_update import InitiatiefUpdatePost
from bouwmeester.schema.initiatief_update import InitiatiefUpdatePostPublicResponse

router = APIRouter(prefix="/public/initiatieven", tags=["public-initiatief"])


class PublicInitiatiefResponse(BaseModel):
    naam: str
    slug: str
    beschrijving: str | None = None
    kleur: str | None = None
    updates: list[InitiatiefUpdatePostPublicResponse] = []

    model_config = ConfigDict(from_attributes=True)


@router.get("/by-slug/{slug}", response_model=PublicInitiatiefResponse)
async def get_public_initiatief(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> PublicInitiatiefResponse:
    """Return naam/beschrijving/kleur + published updates only.

    Returns 404 (not 403) when slug is unknown OR public_page_enabled is
    false. Hiding existence on disabled pages is intentional — leaks no
    information about which initiatieven exist internally.
    """
    stmt = (
        select(Initiatief)
        .where(Initiatief.slug == slug)
        .options(
            selectinload(Initiatief.updates).selectinload(
                InitiatiefUpdatePost.published_by
            )
        )
    )
    result = await db.execute(stmt)
    initiatief = result.scalar_one_or_none()
    if initiatief is None or not initiatief.public_page_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Pagina niet gevonden"
        )

    published_updates = sorted(
        (u for u in initiatief.updates if u.published_at is not None),
        key=lambda u: u.published_at,
        reverse=True,
    )

    return PublicInitiatiefResponse(
        naam=initiatief.naam,
        slug=initiatief.slug or "",
        beschrijving=initiatief.beschrijving,
        kleur=initiatief.kleur,
        updates=[
            InitiatiefUpdatePostPublicResponse(
                titel=u.titel,
                body=u.body,
                published_at=u.published_at,
                published_by_naam=(u.published_by.naam if u.published_by else None),
            )
            for u in published_updates
        ],
    )
