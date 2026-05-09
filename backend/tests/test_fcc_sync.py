"""Tests for FCC import/export services and API endpoints.

Sinds de TOOI-migratie matcht FCC `_resolve_opdrachtnemer` op
`OrganisatieEenheid` (afkorting -> naam -> nieuwe rij onder
'Marktpartijen en overige'). Tests gebruiken nu OrganisatieEenheid
ipv het verwijderde ExterneOrganisatie-model.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.fcc_sync_log import FccSyncLog
from bouwmeester.models.opdracht import Opdracht
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.services.fcc_import_service import FccImportService
from bouwmeester.services.fcc_odata_mock import FccODataMockClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def _use_mock_client(monkeypatch):
    """Patch get_client to return the mock client for all FCC services."""

    async def _mock_get_client(self):
        return FccODataMockClient()

    monkeypatch.setattr(FccImportService, "get_client", _mock_get_client)


@pytest.fixture
async def sample_fcc_opdracht(db_session: AsyncSession):
    """Create an opdracht that was previously imported from FCC."""
    opdracht = Opdracht(
        id=uuid.uuid4(),
        type="opdracht",
        titel="Realisatie publieke NL-Wallet",
        beschrijving="Mock FCC project",
        begrotingsjaar=2026,
        fcc_id="900001",
        fcc_entity_type="Portfolio_item",
        sync_status="synced",
        sync_direction="inbound",
        last_synced_at=datetime(2026, 3, 29, tzinfo=UTC),
        # Must be >= mock's Laatst_gewijzigd_op (2026-03-28) to avoid conflict
        fcc_modified_at=datetime(2026, 3, 29, tzinfo=UTC),
        status="actief",
    )
    db_session.add(opdracht)
    await db_session.flush()
    return opdracht


# ---------------------------------------------------------------------------
# No-op when unconfigured
# ---------------------------------------------------------------------------


async def test_import_noop_when_unconfigured(db_session: AsyncSession):
    """Import does nothing when FCC URL is not configured."""
    service = FccImportService(db_session)
    count = await service.poll_and_import()

    assert count == 0

    result = await db_session.execute(
        select(Opdracht).where(Opdracht.fcc_id.is_not(None))
    )
    assert list(result.scalars().all()) == []


# ---------------------------------------------------------------------------
# Import service: poll_and_import
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_use_mock_client")
async def test_import_creates_opdrachten(db_session: AsyncSession):
    """Import from mock FCC creates new Opdrachten with correct fields."""
    service = FccImportService(db_session)
    count = await service.poll_and_import()
    await db_session.flush()

    assert count >= 5

    result = await db_session.execute(
        select(Opdracht).where(Opdracht.fcc_id.is_not(None))
    )
    opdrachten = list(result.scalars().all())
    assert len(opdrachten) >= 5

    # Check first opdracht maps FCC fields correctly
    wallet = next(o for o in opdrachten if "NL-Wallet" in o.titel)
    assert wallet.fcc_id == "900001"
    assert wallet.sync_status == "synced"
    assert wallet.sync_direction == "inbound"
    assert wallet.fcc_entity_type == "Portfolio_item"
    assert wallet.budget == Decimal("4900000")
    assert str(wallet.startdatum) == "2026-01-01"
    assert str(wallet.einddatum) == "2026-12-31"
    assert wallet.fcc_raw_data is not None
    assert wallet.fcc_raw_data.get("Uitvoeringsorganisatie") == "ICTU"


@pytest.mark.usefixtures("_use_mock_client")
async def test_import_idempotent(db_session: AsyncSession):
    """Running import twice doesn't duplicate opdrachten."""
    service = FccImportService(db_session)

    count1 = await service.poll_and_import()
    await db_session.flush()

    count2 = await service.poll_and_import()
    await db_session.flush()

    assert count1 >= 5
    assert count2 == 0


@pytest.mark.usefixtures("_use_mock_client")
async def test_import_creates_sync_logs(db_session: AsyncSession):
    """Import creates FccSyncLog entries."""
    service = FccImportService(db_session)
    await service.poll_and_import()
    await db_session.flush()

    result = await db_session.execute(
        select(FccSyncLog).where(FccSyncLog.direction == "inbound")
    )
    logs = list(result.scalars().all())
    assert len(logs) >= 5
    assert all(log.action == "created" for log in logs)


# ---------------------------------------------------------------------------
# Import service: conflict detection
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_use_mock_client")
async def test_import_detects_conflict_with_pending_push(
    db_session: AsyncSession, sample_fcc_opdracht
):
    """Import marks opdracht as conflict when it has pending_push."""
    sample_fcc_opdracht.sync_status = "pending_push"
    sample_fcc_opdracht.fcc_modified_at = datetime(2026, 1, 1, tzinfo=UTC)
    sample_fcc_opdracht.last_synced_at = datetime(2026, 1, 1, tzinfo=UTC)
    await db_session.flush()

    service = FccImportService(db_session)
    await service.poll_and_import()
    await db_session.flush()

    await db_session.refresh(sample_fcc_opdracht)
    assert sample_fcc_opdracht.sync_status == "conflict"

    result = await db_session.execute(
        select(FccSyncLog).where(
            FccSyncLog.opdracht_id == sample_fcc_opdracht.id,
            FccSyncLog.action == "conflict",
        )
    )
    assert result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# Import service: field mapping
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_use_mock_client")
async def test_import_maps_fields_correctly(db_session: AsyncSession):
    """Imported opdrachten have correct field values from FCC data."""
    service = FccImportService(db_session)
    await service.poll_and_import()
    await db_session.flush()

    result = await db_session.execute(
        select(Opdracht).where(Opdracht.fcc_id == "900002")
    )
    opdracht = result.scalar_one()

    assert opdracht.titel == "Doorontwikkeling DigiD"
    assert opdracht.budget == Decimal("12000000")
    assert opdracht.gerealiseerd == Decimal("3200000")
    assert str(opdracht.startdatum) == "2026-01-01"
    assert str(opdracht.einddatum) == "2026-12-31"


@pytest.mark.usefixtures("_use_mock_client")
async def test_import_stores_raw_fcc_data(db_session: AsyncSession):
    """Raw FCC data is stored for fields not mapped to Opdracht columns."""
    service = FccImportService(db_session)
    await service.poll_and_import()
    await db_session.flush()

    result = await db_session.execute(
        select(Opdracht).where(Opdracht.fcc_id == "900001")
    )
    opdracht = result.scalar_one()

    raw = opdracht.fcc_raw_data
    assert raw["Uitvoeringsorganisatie"] == "ICTU"
    assert raw["Afdeling_PDD"] == "Toegang"
    assert raw["PDD_Domein"] == "Toegang"
    assert raw["Status_Planning_2"] == "green"


# ---------------------------------------------------------------------------
# Import service: pull_single
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_use_mock_client")
async def test_pull_single_updates_opdracht(
    db_session: AsyncSession, sample_fcc_opdracht
):
    """pull_single re-fetches from FCC and updates the opdracht."""
    service = FccImportService(db_session)
    result = await service.pull_single(sample_fcc_opdracht.id)
    await db_session.flush()

    assert result is True

    await db_session.refresh(sample_fcc_opdracht)
    assert sample_fcc_opdracht.sync_status == "synced"
    assert sample_fcc_opdracht.titel == "Realisatie publieke NL-Wallet"


async def test_pull_single_nonexistent(db_session: AsyncSession):
    """pull_single returns False for unknown opdracht."""
    service = FccImportService(db_session)
    result = await service.pull_single(uuid.uuid4())
    assert result is False


# ---------------------------------------------------------------------------
# Export service
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_use_mock_client")
async def test_export_push_pending(db_session: AsyncSession, sample_fcc_opdracht):
    """push_pending pushes opdrachten with pending_push status."""
    from bouwmeester.services.fcc_export_service import FccExportService

    sample_fcc_opdracht.sync_status = "pending_push"
    await db_session.flush()

    service = FccExportService(db_session)
    count = await service.push_pending()
    await db_session.flush()

    assert count == 1

    await db_session.refresh(sample_fcc_opdracht)
    assert sample_fcc_opdracht.sync_status == "synced"
    assert sample_fcc_opdracht.last_synced_at is not None


@pytest.mark.usefixtures("_use_mock_client")
async def test_export_push_single(db_session: AsyncSession, sample_fcc_opdracht):
    """push_single pushes a specific opdracht to FCC."""
    from bouwmeester.services.fcc_export_service import FccExportService

    service = FccExportService(db_session)
    result = await service.push_single(sample_fcc_opdracht.id)
    await db_session.flush()

    assert result is True

    await db_session.refresh(sample_fcc_opdracht)
    assert sample_fcc_opdracht.sync_status == "synced"


@pytest.mark.usefixtures("_use_mock_client")
async def test_export_push_creates_new_in_fcc(db_session: AsyncSession):
    """Pushing an opdracht without fcc_id creates it in FCC."""
    from bouwmeester.services.fcc_export_service import FccExportService

    opdracht = Opdracht(
        id=uuid.uuid4(),
        type="opdracht",
        titel="Nieuw vanuit Bouwmeester",
        begrotingsjaar=2026,
        status="actief",
        sync_status="pending_push",
    )
    db_session.add(opdracht)
    await db_session.flush()

    service = FccExportService(db_session)
    result = await service.push_single(opdracht.id)
    await db_session.flush()

    assert result is True
    await db_session.refresh(opdracht)
    assert opdracht.fcc_id is not None
    assert opdracht.sync_status == "synced"
    assert opdracht.sync_direction == "outbound"
    assert opdracht.fcc_entity_type == "Portfolio_item"


@pytest.mark.usefixtures("_use_mock_client")
async def test_export_maps_fcc_field_names(
    db_session: AsyncSession, sample_fcc_opdracht
):
    """Export uses correct FCC field names in the payload."""
    from bouwmeester.services.fcc_export_service import FccExportService

    sample_fcc_opdracht.budget = Decimal("5000000")
    sample_fcc_opdracht.gerealiseerd = Decimal("1000000")
    sample_fcc_opdracht.referentie = "PRJ-001"
    sample_fcc_opdracht.sync_status = "pending_push"
    await db_session.flush()

    service = FccExportService(db_session)
    fcc_data = service._map_opdracht_to_fcc(sample_fcc_opdracht)

    assert fcc_data["Naam"] == "Realisatie publieke NL-Wallet"
    assert fcc_data["Budget_huidig_jaar_"] == 5_000_000.0
    assert fcc_data["Gerealiseerde_kosten_huidig_jaar_"] == 1_000_000.0
    assert fcc_data["Project_Nummer"] == "PRJ-001"
    # Should NOT contain old English field names
    assert "Name" not in fcc_data
    assert "Budget" not in fcc_data


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


async def test_api_fcc_schema_empty_when_unconfigured(client):
    """GET /api/fcc/schema returns empty when no FCC URL configured."""
    resp = await client.get("/api/fcc/schema")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"entity_sets": {}}


async def test_api_fcc_sync_trigger_noop_when_unconfigured(client):
    """POST /api/fcc/sync/trigger does nothing when FCC is not configured."""
    resp = await client.post("/api/fcc/sync/trigger")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pulled"] == 0
    assert data["pushed"] == 0


async def test_api_fcc_sync_logs_empty(client):
    """GET /api/fcc/sync/logs returns empty list initially."""
    resp = await client.get("/api/fcc/sync/logs")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_api_fcc_conflicts_empty(client):
    """GET /api/fcc/conflicts returns empty list when no conflicts."""
    resp = await client.get("/api/fcc/conflicts")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Opdrachtnemer resolution
# ---------------------------------------------------------------------------


async def test_eliminate_migratie_levert_ictu_seed(db_session: AsyncSession):
    """Verifieer dat de eliminate-migratie de oude ExterneOrganisatie-seed
    correct heeft overgezet naar OrganisatieEenheid met afkorting='ICTU'.

    De seed-migratie c4a1f2e83b01 zette ICTU in externe_organisatie. De
    eliminate-migratie 9a1b2c3d4e5f migreerde dat naar organisatie_eenheid.
    Als dat breekt valt het FCC-import-pad terug op auto-create en duikt
    er een tweede ICTU op met andere bron.
    """
    result = await db_session.execute(
        select(OrganisatieEenheid).where(OrganisatieEenheid.afkorting == "ICTU")
    )
    rows = result.scalars().all()
    assert len(rows) >= 1, (
        "ICTU ontbreekt — eliminate-migratie heeft seed niet opgepikt"
    )
    # Geen dubbele rijen die beide afkorting='ICTU' hebben en bron='handmatig'
    handmatig = [r for r in rows if r.bron == "handmatig"]
    assert len(handmatig) <= 1, "Meer dan één handmatige ICTU — reconciliation-risico"


@pytest.mark.usefixtures("_use_mock_client")
async def test_import_resolves_existing_opdrachtnemer(db_session: AsyncSession):
    """Import koppelt Uitvoeringsorganisatie aan bestaande OrganisatieEenheid op afkorting."""  # noqa: E501
    # ICTU kan al bestaan via de eliminate-externe-organisatie-migratie
    # (oude seed). Hergebruik die rij of maak hem aan als hij ontbreekt,
    # zodat de FCC resolver hem op afkorting matcht.
    existing = await db_session.execute(
        select(OrganisatieEenheid).where(OrganisatieEenheid.afkorting == "ICTU")
    )
    ictu = existing.scalars().first()
    if ictu is None:
        ictu = OrganisatieEenheid(
            naam="ICTU",
            afkorting="ICTU",
            type="uitvoeringsorganisatie",
            bron="handmatig",
        )
        db_session.add(ictu)
        await db_session.flush()

    service = FccImportService(db_session)
    await service.poll_and_import()
    await db_session.flush()

    # Mock item 900001 has Uitvoeringsorganisatie="ICTU"
    result = await db_session.execute(
        select(Opdracht).where(Opdracht.fcc_id == "900001")
    )
    wallet = result.scalar_one()
    assert wallet.opdrachtnemer_eenheid_id == ictu.id


@pytest.mark.usefixtures("_use_mock_client")
async def test_import_auto_creates_unknown_opdrachtnemer(db_session: AsyncSession):
    """Import maakt nieuwe OrganisatieEenheid aan voor onbekende Uitvoeringsorganisatie."""  # noqa: E501
    service = FccImportService(db_session)
    await service.poll_and_import()
    await db_session.flush()

    # Mock item 900003 has Uitvoeringsorganisatie="KOOP" (niet aanwezig
    # als afkorting/naam in DB) -> nieuwe rij onder Marktpartijen en overige
    # met bron='fcc_import'.
    result = await db_session.execute(
        select(Opdracht).where(Opdracht.fcc_id == "900003")
    )
    overheid_nl = result.scalar_one()
    assert overheid_nl.opdrachtnemer_eenheid_id is not None

    org = await db_session.get(OrganisatieEenheid, overheid_nl.opdrachtnemer_eenheid_id)
    assert org is not None
    assert org.naam == "KOOP"
    assert org.bron == "fcc_import"


# ---------------------------------------------------------------------------
# FCC metadata fields
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_use_mock_client")
async def test_import_maps_metadata_fields(db_session: AsyncSession):
    """Import maps Funnelfase, Afdeling_PDD, Portfolio, Labels to opdracht."""
    service = FccImportService(db_session)
    await service.poll_and_import()
    await db_session.flush()

    result = await db_session.execute(
        select(Opdracht).where(Opdracht.fcc_id == "900001")
    )
    opdracht = result.scalar_one()

    assert opdracht.fcc_funnelfase == "GDI Doorontwikkeling"
    assert opdracht.fcc_afdeling == "Toegang"
    assert opdracht.fcc_portfolio == "Directie PDD"
    assert opdracht.fcc_labels == "GDI,Sub-opdracht"


@pytest.mark.usefixtures("_use_mock_client")
async def test_import_maps_metadata_for_item_without_labels(db_session: AsyncSession):
    """Import handles items without Labels field gracefully."""
    service = FccImportService(db_session)
    await service.poll_and_import()
    await db_session.flush()

    # Mock item 900003 has no Labels field
    result = await db_session.execute(
        select(Opdracht).where(Opdracht.fcc_id == "900003")
    )
    opdracht = result.scalar_one()

    assert opdracht.fcc_funnelfase == "GDI Doorontwikkeling"
    assert opdracht.fcc_afdeling == "Informatie"
    assert opdracht.fcc_labels is None


# ---------------------------------------------------------------------------
# Export with Uitvoeringsorganisatie
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_use_mock_client")
async def test_export_includes_uitvoeringsorganisatie(
    db_session: AsyncSession, sample_fcc_opdracht
):
    """Export mapt opdrachtnemer (OrganisatieEenheid) terug naar Uitvoeringsorganisatie-veld."""  # noqa: E501
    from bouwmeester.services.fcc_export_service import FccExportService

    org = OrganisatieEenheid(
        naam="Test Org",
        afkorting="TST",
        type="uitvoeringsorganisatie",
        bron="handmatig",
    )
    db_session.add(org)
    await db_session.flush()

    sample_fcc_opdracht.opdrachtnemer_eenheid_id = org.id
    await db_session.flush()
    await db_session.refresh(sample_fcc_opdracht, ["opdrachtnemer"])

    service = FccExportService(db_session)
    fcc_data = service._map_opdracht_to_fcc(sample_fcc_opdracht)

    assert fcc_data["Uitvoeringsorganisatie"] == "TST"


# ---------------------------------------------------------------------------
# API response includes fcc_raw_data and metadata
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_use_mock_client")
async def test_api_opdracht_response_includes_fcc_fields(
    client, db_session: AsyncSession
):
    """GET /api/opdrachten/{id} includes fcc_raw_data and metadata fields."""
    service = FccImportService(db_session)
    await service.poll_and_import()
    await db_session.flush()

    result = await db_session.execute(
        select(Opdracht).where(Opdracht.fcc_id == "900001")
    )
    opdracht = result.scalar_one()

    resp = await client.get(f"/api/opdrachten/{opdracht.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["fcc_funnelfase"] == "GDI Doorontwikkeling"
    assert data["fcc_afdeling"] == "Toegang"
    assert data["fcc_portfolio"] == "Directie PDD"
    assert data["fcc_labels"] == "GDI,Sub-opdracht"
    assert data["fcc_raw_data"] is not None
    assert data["fcc_raw_data"]["Uitvoeringsorganisatie"] == "ICTU"
