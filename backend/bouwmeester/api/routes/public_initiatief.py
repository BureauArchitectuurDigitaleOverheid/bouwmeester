"""Public (unauthenticated) endpoints for an initiatief community page."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bouwmeester.core.database import get_db
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.initiatief_update import InitiatiefUpdatePost
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_column import LeadColumn
from bouwmeester.models.lead_update import LeadUpdatePost
from bouwmeester.schema.initiatief_update import InitiatiefUpdatePostPublicResponse
from bouwmeester.schema.lead_update import LeadUpdatePostPublicResponse

router = APIRouter(prefix="/public/initiatieven", tags=["public-initiatief"])


class PublicCasus(BaseModel):
    """Lead-derived public summary; only fields the eigenaar wrote for outside."""

    titel: str
    samenvatting: str | None = None
    updates: list[LeadUpdatePostPublicResponse] = []


class PublicInitiatiefResponse(BaseModel):
    naam: str
    slug: str
    beschrijving: str | None = None
    kleur: str | None = None
    updates: list[InitiatiefUpdatePostPublicResponse] = []
    casussen: list[PublicCasus] = []

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

    Two-step query keeps timing roughly constant between "slug doesn't
    exist" and "exists but private": both bail before any relation loads.
    """
    lookup = await db.execute(select(Initiatief).where(Initiatief.slug == slug))
    initiatief = lookup.scalar_one_or_none()
    if initiatief is None or not initiatief.public_page_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Pagina niet gevonden"
        )

    detail = await db.execute(
        select(Initiatief)
        .where(Initiatief.id == initiatief.id)
        .options(
            selectinload(Initiatief.updates).selectinload(
                InitiatiefUpdatePost.published_by
            )
        )
    )
    initiatief = detail.scalar_one()

    published_updates = sorted(
        (u for u in initiatief.updates if u.published_at is not None),
        key=lambda u: u.published_at,
        reverse=True,
    )

    # Lopende casussen: leads waar de eigenaar/contributor expliciet een
    # publieks-titel heeft geschreven, de toggle aan zette, en de stage
    # behoort tot een kolom die per-initiatief als publiek-zichtbaar is
    # gemarkeerd (LeadColumn.is_public_visible).
    public_slugs_subq = select(LeadColumn.slug).where(
        LeadColumn.initiatief_id == initiatief.id,
        LeadColumn.is_public_visible.is_(True),
    )
    leads_result = await db.execute(
        select(Lead)
        .where(
            Lead.initiatief_id == initiatief.id,
            Lead.public_visible.is_(True),
            Lead.public_title.is_not(None),
            Lead.stage.in_(public_slugs_subq),
        )
        .options(selectinload(Lead.updates).selectinload(LeadUpdatePost.published_by))
        .order_by(Lead.created_at.desc())
    )
    casussen: list[PublicCasus] = []
    for lead in leads_result.scalars().all():
        published = sorted(
            (u for u in lead.updates if u.published_at is not None and u.body_public),
            key=lambda u: u.published_at,
            reverse=True,
        )
        casussen.append(
            PublicCasus(
                titel=lead.public_title or "",
                samenvatting=lead.public_summary,
                updates=[
                    LeadUpdatePostPublicResponse(
                        titel=u.titel,
                        body_public=u.body_public,
                        published_at=u.published_at,
                        published_by_naam=(
                            u.published_by.naam if u.published_by else None
                        ),
                    )
                    for u in published
                ],
            )
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
        casussen=casussen,
    )
