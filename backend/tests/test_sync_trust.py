"""Official syncs never hand trust to something a user controls.

A placement from the ABD scrape or the kabinet syncs gives access, and
names are user-controlled: renaming yourself (or a contact carrying your
address) to an announced appointee must not put you in the ministerie, and
a user-made eenheid with a matching name must not receive an official
placement.  Likewise only official, top-level ministeries take part in the
ministerie merge and the organogram scrape.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
from bouwmeester.models.pending_reconciliation import PendingReconciliation
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_organisatie import PersonOrganisatieEenheid
from bouwmeester.models.tooi_sync_log import TooiSyncLog
from bouwmeester.services import tooi_sync
from bouwmeester.services.abd_scrape import (
    AbdBenoeming,
    _resolveer_organisatie,
    sync_abd,
)
from bouwmeester.services.auto_merge_ministeries import merge_ministries
from bouwmeester.services.historische_kabinetten_sync import (
    sync_historische_kabinetten,
)
from bouwmeester.services.kabinet_sync import sync_kabinet
from bouwmeester.services.organogram_scrape import DgInfo, sync_organogram
from tests.authz_world import rp
from tests.factories import make_org, make_person

BZK_URI = "https://identifier.overheid.nl/tooi/id/ministerie/mnre1034"
BZK = "ministerie van Binnenlandse Zaken en Koninkrijksrelaties"
NAAM = "Aangekondigde Benoemde"


@pytest.fixture
async def bzk(db_session: AsyncSession) -> OrganisatieEenheid:
    await db_session.execute(text("DELETE FROM person_organisatie_eenheid"))
    await db_session.execute(text("DELETE FROM organisatie_eenheid WHERE bron='tooi'"))
    eenheid = OrganisatieEenheid(
        naam=BZK, type="ministerie", bron="tooi", tooi_uri=BZK_URI
    )
    db_session.add(eenheid)
    await db_session.flush()
    return eenheid


async def _account(db: AsyncSession) -> Person:
    """A logged-in user who renamed themselves to the appointee."""
    person = Person(naam=NAAM, oidc_subject=f"sub-{uuid.uuid4()}")
    db.add(person)
    await db.flush()
    return person


async def _contact_with_address(db: AsyncSession) -> Person:
    """A plain contact carrying the attacker's address, renamed likewise."""
    person = Person(naam=NAAM)
    db.add(person)
    await db.flush()
    db.add(PersonEmail(person_id=person.id, email="aanvaller@example.org"))
    await db.flush()
    return person


async def _placements(db: AsyncSession, person_id: uuid.UUID) -> list:
    stmt = select(PersonOrganisatieEenheid).where(
        PersonOrganisatieEenheid.person_id == person_id
    )
    return list((await db.scalars(stmt)).all())


async def _synced_persons(db: AsyncSession, bron: str) -> list[Person]:
    stmt = select(Person).where(Person.naam == NAAM, Person.bron == bron)
    return list((await db.scalars(stmt)).all())


def _yaml(tmp_path, kind: str):
    path = tmp_path / f"{kind}.yaml"
    person = (
        f'  - naam: "{NAAM}"\n'
        f'    ministerie_tooi_uri: "{BZK_URI}"\n'
        '    functietitel: "Minister van BZK"\n'
    )
    if kind == "kabinet":
        path.write_text("bewindspersonen:\n" + person + "    van: 2026-01-01\n")
    else:
        body = "".join("  " + line + "\n" for line in person.splitlines())
        path.write_text(
            "kabinet_test:\n  van: 2024-01-01\n  tot: 2025-12-31\n"
            "  bewindspersonen:\n" + body
        )
    return path


async def _run(kind: str, db: AsyncSession, tmp_path):
    if kind == "abd":
        benoeming = AbdBenoeming(
            naam=NAAM,
            functietitel="directeur-generaal",
            organisatie_hint="BZK",
            nieuws_url="https://example.com/benoeming",
            publicatiedatum=date(2026, 5, 9),
            ingangsdatum=date(2026, 6, 1),
        )

        async def fetch():
            return [benoeming]

        return await sync_abd(db, fetcher=fetch, commit=False)
    if kind == "kabinet":
        return await sync_kabinet(db, _yaml(tmp_path, kind))
    return await sync_historische_kabinetten(db, _yaml(tmp_path, kind), commit=False)


_BRON = {"abd": "abd_scrape", "kabinet": "kabinet_yaml", "historisch": "kabinet_yaml"}
_SYNCS = list(_BRON)


@pytest.mark.parametrize("kind", _SYNCS)
@pytest.mark.parametrize("make", [_account, _contact_with_address])
async def test_renamed_record_gets_no_trusted_placement(
    db_session: AsyncSession, bzk, tmp_path, kind, make
):
    victim = await make(db_session)

    await _run(kind, db_session, tmp_path)

    assert await _placements(db_session, victim.id) == []
    [created] = await _synced_persons(db_session, _BRON[kind])
    assert created.id != victim.id
    [placement] = await _placements(db_session, created.id)
    assert placement.organisatie_eenheid_id == bzk.id
    conflict = await db_session.scalar(
        select(TooiSyncLog.id).where(
            TooiSyncLog.person_id == created.id, TooiSyncLog.action == "conflict"
        )
    )
    assert conflict is not None
    # A second run reuses the synced person.
    await _run(kind, db_session, tmp_path)
    assert len(await _synced_persons(db_session, _BRON[kind])) == 1


@pytest.mark.parametrize("kind", _SYNCS)
async def test_ambiguous_name_is_refused(db_session: AsyncSession, bzk, tmp_path, kind):
    for _ in range(2):
        db_session.add(Person(naam=NAAM, bron=_BRON[kind]))
    await db_session.flush()

    stats = await _run(kind, db_session, tmp_path)

    assert stats.new_placements == 0
    assert any("meerdere" in f.lower() for f in stats.fouten)
    assert len(await _synced_persons(db_session, _BRON[kind])) == 2


@pytest.mark.parametrize(
    ("naam", "account", "placed"),
    [
        (NAAM, False, True),  # an ex-Kamerlid synced from TK: reused by key
        ("Aangekondigde Tussen Benoemde", True, False),  # surname match, account
    ],
)
async def test_kabinet_and_tk_persons(
    db_session: AsyncSession, bzk, tmp_path, naam, account, placed
):
    tk = Person(
        naam=naam,
        bron="tk_odata",
        tk_persoon_id=str(uuid.uuid4()),
        oidc_subject=f"sub-{uuid.uuid4()}" if account else None,
    )
    db_session.add(tk)
    await db_session.flush()

    await _run("kabinet", db_session, tmp_path)

    assert len(await _placements(db_session, tk.id)) == int(placed)


async def test_resolver_trusts_only_one_official_literal_match(
    db_session: AsyncSession, bzk
):
    """A handmatig eenheid named like a dienst gets no official placement; an
    ambiguous match is refused; the hint is no LIKE pattern."""
    db_session.add(
        OrganisatieEenheid(naam="Dienst Uitvoering Onderwijs", type="dienst")
    )
    for naam in ("Rijksdienst Een", "Rijksdienst Twee"):
        db_session.add(OrganisatieEenheid(naam=naam, type="dienst", bron="tooi"))
    await db_session.flush()

    for hint in ("DUO", "Rijksdienst", "%"):
        assert await _resolveer_organisatie(db_session, hint) is None, hint


# ---------------------------------------------------------------------------
# The ministerie merge after a TOOI sync, and the organogram scrape
# ---------------------------------------------------------------------------

TESTZAKEN = "Ministerie van Testzaken"


async def _tooi_row(db) -> OrganisatieEenheid:
    row = await make_org(db, TESTZAKEN, "ministerie")
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


async def _owned_root(db, type_: str) -> OrganisatieEenheid:
    owner = await make_person(db, "Eigenaar")
    root = await make_org(db, "Eigen stichting", type_)
    db.add(rp("organisatie_eenheid", root.id, "eigenaar", person=owner))
    return root


def test_tooi_sync_uses_the_real_module():
    # The sync imported a module that does not exist, so the merge (and
    # the organogram scrape after it in the worker) never ran.
    assert tooi_sync.merge_ministries is merge_ministries


@pytest.mark.parametrize("where", ["below_own_root", "own_root"])
async def test_user_ministerie_is_not_merged(db_session, where):
    """A root with an eigenaar is someone's own organisation, whatever its
    type; a ministerie below it must not take over the official row."""
    db = db_session
    if where == "own_root":
        fake = await _owned_root(db, "ministerie")
        fake.naam = TESTZAKEN
    else:
        fake = await make_org(
            db, TESTZAKEN, "ministerie", await _owned_root(db, "stichting")
        )
    tooi = await _tooi_row(db)
    rec = await _reconcile(db, fake, tooi)

    assert await merge_ministries(db) == 0

    assert await db.get(OrganisatieEenheid, tooi.id) is not None
    assert (await db.get(OrganisatieEenheid, fake.id)).tooi_uri is None
    assert rec.status == "open"


async def test_top_level_manual_ministerie_merges_into_tooi_row(db_session):
    db = db_session
    manual = await make_org(db, TESTZAKEN, "ministerie")
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
    assert (kept.tooi_uri, kept.bron, kept.afkorting) == (tooi_uri, "tooi", "TZ")
    parent = await db.scalar(
        select(OrganisatieEenheid.parent_id).where(OrganisatieEenheid.id == dg_id)
    )
    assert parent == tooi_id
    assert (await db.get(PendingReconciliation, rec_id)).status == "merged"


async def test_organogram_scrape_ignores_user_ministeries(db_session):
    """Only official top-level ministeries receive (trusted) DGs."""
    root = await make_org(db_session, "Eigen stichting", "stichting")
    below_root = await make_org(db_session, BZK, "ministerie", root)
    manual_top = await make_org(db_session, BZK, "ministerie")

    async def fake_fetch(slug: str):
        return [DgInfo(naam="DG Overname", detail_url="x")], {}

    await sync_organogram(db_session, fetcher=fake_fetch)
    for ministerie in (below_root, manual_top):
        child = await db_session.scalar(
            select(OrganisatieEenheid.id).where(
                OrganisatieEenheid.parent_id == ministerie.id
            )
        )
        assert child is None
