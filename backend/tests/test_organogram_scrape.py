"""Tests voor organogram-scrape dedup op genormaliseerde naam.

De DGDOO-duplicaat: seed maakt 'DG Digitalisering en Overheidsorganisatie',
organogram.overheid.nl noemt diezelfde DG 'Digitalisering en
Overheidsorganisatie'. Exacte string-match liet dat als tweede rij
ontstaan; na de fix matcht de scrape op genormaliseerde naam.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.text import normalize_org_name
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.services.organogram_scrape import DgInfo, sync_organogram


def test_normalize_org_name_stript_dg_prefix():
    assert normalize_org_name("DG Digitalisering en Overheidsorganisatie") == (
        normalize_org_name("Digitalisering en Overheidsorganisatie")
    )
    assert normalize_org_name("Ministerie van Financiën") == "financiën"
    assert normalize_org_name("  Agentschap   Telecom ") == "telecom"
    # Slechts één prefix wordt gestript (geen herhaalde pass)
    assert normalize_org_name("DG DG Test") == "dg test"


async def test_organogram_scrape_geen_duplicaat_op_dg_prefix(
    db_session: AsyncSession,
):
    """Bestaande seed-DG 'DG X' + organogram levert 'X' -> geen tweede rij."""
    bzk = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="ministerie van Binnenlandse Zaken en Koninkrijksrelaties",
        type="ministerie",
        bron="handmatig",
    )
    seed_dg = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="DG Digitalisering en Overheidsorganisatie",
        type="directoraat_generaal",
        bron="handmatig",
        parent_id=bzk.id,
    )
    db_session.add_all([bzk, seed_dg])
    await db_session.flush()

    async def fake_fetch(slug: str):
        # organogram noemt de DG zonder "DG "-prefix
        return (
            [DgInfo(naam="Digitalisering en Overheidsorganisatie", detail_url="x")],
            {},
        )

    stats = await sync_organogram(db_session, fetcher=fake_fetch)

    # De bestaande DG werd herkend -> geen nieuwe DG aangemaakt
    assert stats.dgs_added == 0

    count = (
        await db_session.execute(
            select(func.count())
            .select_from(OrganisatieEenheid)
            .where(
                OrganisatieEenheid.parent_id == bzk.id,
                OrganisatieEenheid.geldig_tot.is_(None),
            )
        )
    ).scalar_one()
    assert count == 1, f"Verwacht 1 DG onder BZK, kreeg {count} (duplicaat!)"


async def test_organogram_scrape_maakt_wel_nieuwe_dg_aan(
    db_session: AsyncSession,
):
    """Sanity: een echt nieuwe DG wordt nog steeds aangemaakt."""
    bzk = OrganisatieEenheid(
        id=uuid.uuid4(),
        naam="ministerie van Binnenlandse Zaken en Koninkrijksrelaties",
        type="ministerie",
        bron="handmatig",
    )
    db_session.add(bzk)
    await db_session.flush()

    async def fake_fetch(slug: str):
        return ([DgInfo(naam="DG Volkshuisvesting en Bouwen", detail_url="y")], {})

    stats = await sync_organogram(db_session, fetcher=fake_fetch)
    assert stats.dgs_added == 1
