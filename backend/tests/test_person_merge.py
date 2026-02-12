"""Tests for person merge functionality."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.node_stakeholder import NodeStakeholder
from bouwmeester.models.notification import Notification
from bouwmeester.models.person import Person
from bouwmeester.models.person_email import PersonEmail
from bouwmeester.models.person_phone import PersonPhone
from bouwmeester.models.task import Task
from bouwmeester.services.merge import find_merge_candidates, merge_persons

# ---------------------------------------------------------------------------
# merge_persons service tests
# ---------------------------------------------------------------------------


async def test_merge_transfers_emails(db_session: AsyncSession):
    """Merge transfers emails from absorbed person to keep person."""
    keep = Person(id=uuid.uuid4(), naam="Keep", email="keep@minbzk.nl", is_active=True)
    absorb = Person(
        id=uuid.uuid4(), naam="Keep", email="keep@rijksoverheid.nl", is_active=True
    )
    db_session.add_all([keep, absorb])
    await db_session.flush()

    db_session.add(
        PersonEmail(person_id=keep.id, email="keep@minbzk.nl", is_default=True)
    )
    db_session.add(
        PersonEmail(person_id=absorb.id, email="keep@rijksoverheid.nl", is_default=True)
    )
    await db_session.flush()

    merged = await merge_persons(db_session, keep_id=keep.id, absorb_id=absorb.id)

    emails = (
        (
            await db_session.execute(
                select(PersonEmail.email).where(PersonEmail.person_id == merged.id)
            )
        )
        .scalars()
        .all()
    )
    assert "keep@minbzk.nl" in emails
    assert "keep@rijksoverheid.nl" in emails


async def test_merge_transfers_tasks(
    db_session: AsyncSession, sample_node, sample_person, second_person
):
    """Merge transfers tasks from absorbed person to keep person."""
    task = Task(
        id=uuid.uuid4(),
        title="Overgedragen taak",
        node_id=sample_node.id,
        assignee_id=second_person.id,
        status="open",
        priority="normaal",
    )
    db_session.add(task)
    await db_session.flush()

    await merge_persons(
        db_session, keep_id=sample_person.id, absorb_id=second_person.id
    )

    updated_task = await db_session.get(Task, task.id)
    assert updated_task.assignee_id == sample_person.id


async def test_merge_transfers_stakeholder_roles(
    db_session: AsyncSession, sample_node, sample_person, second_person
):
    """Merge transfers stakeholder roles from absorbed to keep."""
    ns = NodeStakeholder(
        id=uuid.uuid4(),
        node_id=sample_node.id,
        person_id=second_person.id,
        rol="eigenaar",
    )
    db_session.add(ns)
    await db_session.flush()

    await merge_persons(
        db_session, keep_id=sample_person.id, absorb_id=second_person.id
    )

    updated = await db_session.get(NodeStakeholder, ns.id)
    assert updated.person_id == sample_person.id


async def test_merge_transfers_oidc_subject(db_session: AsyncSession):
    """Merge transfers oidc_subject when keep doesn't have one."""
    keep = Person(
        id=uuid.uuid4(),
        naam="Merge OIDC",
        email="m1@minbzk.nl",
        is_active=True,
        oidc_subject=None,
    )
    absorb = Person(
        id=uuid.uuid4(),
        naam="Merge OIDC",
        email="m2@rijksoverheid.nl",
        is_active=True,
        oidc_subject="oidc-subject-123",
    )
    db_session.add_all([keep, absorb])
    await db_session.flush()

    db_session.add(
        PersonEmail(person_id=keep.id, email="m1@minbzk.nl", is_default=True)
    )
    db_session.add(
        PersonEmail(person_id=absorb.id, email="m2@rijksoverheid.nl", is_default=True)
    )
    await db_session.flush()

    merged = await merge_persons(db_session, keep_id=keep.id, absorb_id=absorb.id)
    assert merged.oidc_subject == "oidc-subject-123"


async def test_merge_keeps_oidc_subject_when_keep_has_one(
    db_session: AsyncSession,
):
    """Merge does NOT overwrite keep's oidc_subject."""
    keep = Person(
        id=uuid.uuid4(),
        naam="Keep OIDC",
        email="k1@minbzk.nl",
        is_active=True,
        oidc_subject="keep-oidc",
    )
    absorb = Person(
        id=uuid.uuid4(),
        naam="Keep OIDC",
        email="k2@rijksoverheid.nl",
        is_active=True,
        oidc_subject="absorb-oidc",
    )
    db_session.add_all([keep, absorb])
    await db_session.flush()

    db_session.add(
        PersonEmail(person_id=keep.id, email="k1@minbzk.nl", is_default=True)
    )
    db_session.add(
        PersonEmail(person_id=absorb.id, email="k2@rijksoverheid.nl", is_default=True)
    )
    await db_session.flush()

    merged = await merge_persons(db_session, keep_id=keep.id, absorb_id=absorb.id)
    assert merged.oidc_subject == "keep-oidc"


async def test_merge_deletes_absorbed_person(db_session: AsyncSession):
    """Absorbed person is deleted after merge."""
    keep = Person(
        id=uuid.uuid4(), naam="Delete Test", email="dt1@minbzk.nl", is_active=True
    )
    absorb = Person(
        id=uuid.uuid4(),
        naam="Delete Test",
        email="dt2@rijksoverheid.nl",
        is_active=True,
    )
    db_session.add_all([keep, absorb])
    await db_session.flush()

    db_session.add(
        PersonEmail(person_id=keep.id, email="dt1@minbzk.nl", is_default=True)
    )
    db_session.add(
        PersonEmail(person_id=absorb.id, email="dt2@rijksoverheid.nl", is_default=True)
    )
    await db_session.flush()

    absorb_id = absorb.id
    await merge_persons(db_session, keep_id=keep.id, absorb_id=absorb_id)

    gone = await db_session.get(Person, absorb_id)
    assert gone is None


async def test_merge_transfers_notifications(
    db_session: AsyncSession, sample_person, second_person
):
    """Merge transfers notifications from absorbed to keep."""
    notif = Notification(
        id=uuid.uuid4(),
        person_id=second_person.id,
        type="direct_message",
        title="Test",
        message="Bericht",
        sender_id=sample_person.id,
    )
    db_session.add(notif)
    await db_session.flush()

    await merge_persons(
        db_session, keep_id=sample_person.id, absorb_id=second_person.id
    )

    updated_notif = await db_session.get(Notification, notif.id)
    assert updated_notif.person_id == sample_person.id


async def test_merge_transfers_phones(db_session: AsyncSession):
    """Merge transfers phone numbers from absorbed to keep."""
    keep = Person(
        id=uuid.uuid4(), naam="Phone Merge", email="pm1@minbzk.nl", is_active=True
    )
    absorb = Person(
        id=uuid.uuid4(),
        naam="Phone Merge",
        email="pm2@rijksoverheid.nl",
        is_active=True,
    )
    db_session.add_all([keep, absorb])
    await db_session.flush()

    db_session.add(
        PersonEmail(person_id=keep.id, email="pm1@minbzk.nl", is_default=True)
    )
    db_session.add(
        PersonEmail(person_id=absorb.id, email="pm2@rijksoverheid.nl", is_default=True)
    )
    db_session.add(
        PersonPhone(
            person_id=absorb.id,
            phone_number="+31600000000",
            label="werk",
            is_default=True,
        )
    )
    await db_session.flush()

    merged = await merge_persons(db_session, keep_id=keep.id, absorb_id=absorb.id)

    phones = (
        (
            await db_session.execute(
                select(PersonPhone.phone_number).where(
                    PersonPhone.person_id == merged.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert "+31600000000" in phones


# ---------------------------------------------------------------------------
# find_merge_candidates service tests
# ---------------------------------------------------------------------------


async def test_find_merge_candidates_same_name_rijksoverheid(
    db_session: AsyncSession,
):
    """Finds candidates with same name in Rijksoverheid domain group."""
    person_a = Person(
        id=uuid.uuid4(),
        naam="Anne de Vries",
        email="anne@minbzk.nl",
        is_active=True,
    )
    person_b = Person(
        id=uuid.uuid4(),
        naam="Anne de Vries",
        email="anne@rijksoverheid.nl",
        is_active=True,
    )
    db_session.add_all([person_a, person_b])
    await db_session.flush()

    db_session.add(
        PersonEmail(person_id=person_a.id, email="anne@minbzk.nl", is_default=True)
    )
    db_session.add(
        PersonEmail(
            person_id=person_b.id, email="anne@rijksoverheid.nl", is_default=True
        )
    )
    await db_session.flush()

    candidates = await find_merge_candidates(db_session, person_a)
    assert len(candidates) >= 1
    assert any(c.id == person_b.id for c in candidates)


async def test_find_merge_candidates_non_rijksoverheid_no_results(
    db_session: AsyncSession,
):
    """No candidates returned when person has non-Rijksoverheid email."""
    person_a = Person(
        id=uuid.uuid4(),
        naam="Bob External",
        email="bob@gmail.com",
        is_active=True,
    )
    person_b = Person(
        id=uuid.uuid4(),
        naam="Bob External",
        email="bob@yahoo.com",
        is_active=True,
    )
    db_session.add_all([person_a, person_b])
    await db_session.flush()

    db_session.add(
        PersonEmail(person_id=person_a.id, email="bob@gmail.com", is_default=True)
    )
    db_session.add(
        PersonEmail(person_id=person_b.id, email="bob@yahoo.com", is_default=True)
    )
    await db_session.flush()

    candidates = await find_merge_candidates(db_session, person_a)
    assert len(candidates) == 0


async def test_find_merge_candidates_different_name_no_results(
    db_session: AsyncSession,
):
    """No candidates when names differ, even with Rijksoverheid emails."""
    person_a = Person(
        id=uuid.uuid4(),
        naam="Alice Jansen",
        email="alice@minbzk.nl",
        is_active=True,
    )
    person_b = Person(
        id=uuid.uuid4(),
        naam="Bob Pietersen",
        email="bob@rijksoverheid.nl",
        is_active=True,
    )
    db_session.add_all([person_a, person_b])
    await db_session.flush()

    db_session.add(
        PersonEmail(person_id=person_a.id, email="alice@minbzk.nl", is_default=True)
    )
    db_session.add(
        PersonEmail(
            person_id=person_b.id, email="bob@rijksoverheid.nl", is_default=True
        )
    )
    await db_session.flush()

    candidates = await find_merge_candidates(db_session, person_a)
    assert len(candidates) == 0


# ---------------------------------------------------------------------------
# Merge API endpoint tests
# ---------------------------------------------------------------------------


async def test_merge_endpoint(client, sample_person, second_person):
    """POST /api/people/{keep_id}/merge/{absorb_id} merges persons."""
    resp = await client.post(f"/api/people/{sample_person.id}/merge/{second_person.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(sample_person.id)

    # Absorbed person should be gone
    get_resp = await client.get(f"/api/people/{second_person.id}")
    assert get_resp.status_code == 404


async def test_merge_self_400(client, sample_person):
    """Merging a person with itself returns 400."""
    resp = await client.post(f"/api/people/{sample_person.id}/merge/{sample_person.id}")
    assert resp.status_code == 400


async def test_merge_not_found_404(client, sample_person):
    """Merging with non-existent person returns 404."""
    fake_id = uuid.uuid4()
    resp = await client.post(f"/api/people/{sample_person.id}/merge/{fake_id}")
    assert resp.status_code == 404
