"""The automatic ministerie merge after a TOOI sync.

Only a top-level manual ministerie merges, and the TOOI row survives: a
ministerie someone hung below their own organisation must not take over the
official row (and with it everything placed below it).
"""

import uuid

from sqlalchemy import select

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.pending_reconciliation import PendingReconciliation
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.services import tooi_sync
from bouwmeester.services.auto_merge_ministeries import merge_ministries
from tests.factories import make_org, make_person

NAAM = "Ministerie van Testzaken"


async def _tooi_row(db) -> OrganisatieEenheid:
    row = await make_org(db, NAAM, "ministerie")
    row.bron = "tooi"
    row.tooi_uri = f"https://identifier.overheid.nl/tooi/id/ministerie/{uuid.uuid4()}"
    await db.flush()
    return row


async def _reconcile(db, handmatig, kandidaat) -> PendingReconciliation:
    rec = PendingReconciliation(
        resource_type="organisatie_eenheid",
        handmatige_id=handmatig.id,
        kandidaat_id=kandidaat.id,
        kandidaat_bron="tooi",
        match_reden="naam_normalized",
        status="open",
    )
    db.add(rec)
    await db.flush()
    return rec


def test_tooi_sync_uses_the_real_module():
    # The sync imported a module that does not exist, so the merge (and
    # the organogram scrape after it in the worker) never ran.
    assert tooi_sync.merge_ministries is merge_ministries


async def test_ministerie_below_user_root_is_not_merged(db_session):
    db = db_session
    attacker = await make_person(db, "Aanvaller")
    root = await make_org(db, "Eigen stichting", "stichting")
    db.add(
        ResourcePermission(
            person_id=attacker.id,
            resource_type="organisatie_eenheid",
            resource_id=root.id,
            rol="eigenaar",
        )
    )
    fake = await make_org(db, NAAM, "ministerie", root)
    tooi = await _tooi_row(db)
    rec = await _reconcile(db, fake, tooi)

    assert await merge_ministries(db) == 0

    assert await db.get(OrganisatieEenheid, tooi.id) is not None
    assert (await db.get(OrganisatieEenheid, fake.id)).tooi_uri is None
    assert rec.status == "open"


async def test_user_root_ministerie_is_not_merged(db_session):
    # A root with an eigenaar is someone's own organisation, whatever its type.
    db = db_session
    owner = await make_person(db, "Eigenaar")
    fake = await make_org(db, NAAM, "ministerie")
    db.add(
        ResourcePermission(
            person_id=owner.id,
            resource_type="organisatie_eenheid",
            resource_id=fake.id,
            rol="eigenaar",
        )
    )
    tooi = await _tooi_row(db)
    await _reconcile(db, fake, tooi)

    assert await merge_ministries(db) == 0
    assert await db.get(OrganisatieEenheid, tooi.id) is not None


async def test_top_level_manual_ministerie_merges_into_tooi_row(db_session):
    db = db_session
    manual = await make_org(db, NAAM, "ministerie")
    manual.afkorting = "TZ"
    dg = await make_org(db, "DG Testen", "directoraat_generaal", manual)
    tooi = await _tooi_row(db)
    tooi_uri = tooi.tooi_uri
    rec = await _reconcile(db, manual, tooi)
    manual_id, tooi_id, dg_id, rec_id = manual.id, tooi.id, dg.id, rec.id

    assert await merge_ministries(db) == 1

    db.expire_all()
    assert await db.get(OrganisatieEenheid, manual_id) is None
    kept = await db.get(OrganisatieEenheid, tooi_id)
    assert kept.tooi_uri == tooi_uri
    assert kept.bron == "tooi"
    assert kept.afkorting == "TZ"
    parent = await db.scalar(
        select(OrganisatieEenheid.parent_id).where(OrganisatieEenheid.id == dg_id)
    )
    assert parent == tooi_id
    assert (await db.get(PendingReconciliation, rec_id)).status == "merged"
