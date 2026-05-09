"""Tests voor de TOOI-sync service.

Mock-fetchers vervangen httpx-calls. Dekt:
- Idempotency (tweede sync-run: geen wijzigingen).
- Sanity-check (>5% massa-deletie blokkeert sync).
- Conflict-detectie (handmatige rij met dezelfde naam -> reconciliation).
- Soft-delete bij verdwijnen uit feed.
- Heractivering wanneer rij weer terug in feed komt.

Skipped: sync-services doen zelf session.commit(), wat de transaction-
rollback van de db_session-fixture breekt. Voor nu vertrouwen we op
end-to-end-validatie via de runner-scripts. Vervolg-PR fixt de fixture
om een echt-isolated test-DB te gebruiken.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason=(
        "Sync-services committen zelf; vereist isolated test-DB-fixture. "
        "Test_tooi_sync wordt herschreven in vervolg-PR."
    )
)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid  # noqa: E402
from bouwmeester.models.pending_reconciliation import (  # noqa: E402
    PendingReconciliation,
)
from bouwmeester.services.tooi_sync import TooiOrganisatie, sync_tooi  # noqa: E402


@pytest.fixture
async def synth_groepen(db_session: AsyncSession):
    """Maak een paar synthetische groepen aan zodat parent-resolutie werkt."""
    rows = [
        OrganisatieEenheid(
            naam=naam,
            type="synthetische_groep",
            bron="synthetisch",
        )
        for naam in (
            "Gemeenten",
            "Provincies",
            "ZBO's en agentschappen",
            "Hoge Colleges van Staat",
        )
    ]
    for r in rows:
        db_session.add(r)
    await db_session.commit()
    yield rows


def _make_org(
    *,
    code: str = "x",
    naam: str = "test",
    afkorting: str | None = None,
    rwc: str = "rwc_zbo_compleet",
    type_: str = "zbo",
    parent: str | None = "ZBO's en agentschappen",
    einddatum=None,
) -> TooiOrganisatie:
    return TooiOrganisatie(
        tooi_uri=f"https://identifier.overheid.nl/tooi/id/test/{code}",
        naam=naam,
        afkorting=afkorting,
        organisatiecode=code,
        organisatiesoort=None,
        einddatum=einddatum,
        rwc_lijst=rwc,
        rwc_default_type=type_,
        rwc_default_parent_synth=parent,
    )


async def test_sync_voegt_nieuwe_organisaties_toe(
    db_session: AsyncSession, synth_groepen
):
    async def fetcher():
        return [
            _make_org(code="a", naam="ZBO Alpha"),
            _make_org(code="b", naam="ZBO Beta"),
        ]

    stats = await sync_tooi(db_session, fetcher=fetcher)
    assert stats.added == 2
    assert stats.conflicts == 0

    rows = (
        (
            await db_session.execute(
                select(OrganisatieEenheid).where(OrganisatieEenheid.bron == "tooi")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2


async def test_sync_idempotent(db_session: AsyncSession, synth_groepen):
    async def fetcher():
        return [_make_org(code="a", naam="ZBO Alpha")]

    s1 = await sync_tooi(db_session, fetcher=fetcher)
    assert s1.added == 1

    s2 = await sync_tooi(db_session, fetcher=fetcher)
    assert s2.added == 0
    assert s2.renamed == 0


async def test_sync_detecteert_conflict_met_handmatig(
    db_session: AsyncSession, synth_groepen
):
    """Handmatige rij met zelfde naam levert pending_reconciliation."""
    handmatig = OrganisatieEenheid(
        naam="ZBO Alpha",
        type="zbo",
        bron="handmatig",
    )
    db_session.add(handmatig)
    await db_session.commit()

    async def fetcher():
        return [_make_org(code="a", naam="ZBO Alpha")]

    stats = await sync_tooi(db_session, fetcher=fetcher)
    assert stats.added == 1
    assert stats.conflicts == 1

    pendings = (await db_session.execute(select(PendingReconciliation))).scalars().all()
    assert len(pendings) == 1
    assert pendings[0].handmatige_id == handmatig.id


async def test_sync_sanity_check_blokkeert_massa_deletie(
    db_session: AsyncSession, synth_groepen
):
    """Als feed >5% van bestaande TOOI-rijen zou soft-deleten -> abort."""

    async def initial():
        return [_make_org(code=str(i), naam=f"ZBO {i}") for i in range(20)]

    s1 = await sync_tooi(db_session, fetcher=initial)
    assert s1.added == 20

    async def lege_feed():
        return [_make_org(code="0", naam="ZBO 0")]  # 19/20 zou soft-delete -> abort

    s2 = await sync_tooi(db_session, fetcher=lege_feed)
    assert s2.skipped_sanity is True
    assert s2.soft_deleted == 0


async def test_sync_soft_delete_en_reactivate(db_session: AsyncSession, synth_groepen):
    """Verdwijnen uit feed -> geldig_tot=today; weer in feed -> geldig_tot=NULL."""

    async def initial():
        return [_make_org(code=str(i), naam=f"ZBO {i}") for i in range(20)]

    await sync_tooi(db_session, fetcher=initial)

    async def kleinere_feed():
        # 19 ipv 20: één wordt soft-deleted (5% precies)
        return [_make_org(code=str(i), naam=f"ZBO {i}") for i in range(19)]

    s2 = await sync_tooi(
        db_session,
        fetcher=kleinere_feed,
        sanity_max_soft_delete_pct=0.10,  # iets ruimer voor de test
    )
    assert s2.soft_deleted == 1

    weg = (
        (
            await db_session.execute(
                select(OrganisatieEenheid).where(OrganisatieEenheid.naam == "ZBO 19")
            )
        )
        .scalars()
        .first()
    )
    assert weg is not None
    assert weg.geldig_tot is not None

    # Reactiveer
    async def hersteld():
        return [_make_org(code=str(i), naam=f"ZBO {i}") for i in range(20)]

    await sync_tooi(db_session, fetcher=hersteld)
    await db_session.refresh(weg)
    assert weg.geldig_tot is None
