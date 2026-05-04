"""Tests for lead activity endpoints, including @-mention notifications."""

import json
import uuid

import pytest
from sqlalchemy import select

from bouwmeester.models.lead import Lead
from bouwmeester.models.notification import Notification


@pytest.fixture
async def sample_lead(db_session):
    lead = Lead(
        id=uuid.uuid4(),
        title="Test lead",
        stage="inbox",
    )
    db_session.add(lead)
    await db_session.flush()
    return lead


@pytest.fixture
async def assigned_lead(db_session, sample_person):
    lead = Lead(
        id=uuid.uuid4(),
        title="Assigned lead",
        stage="inbox",
        assignee_id=sample_person.id,
    )
    db_session.add(lead)
    await db_session.flush()
    return lead


async def test_add_activity_returns_201(client, sample_lead):
    """Plain note creates activity and returns 201 (regression for data.type bug)."""
    resp = await client.post(
        f"/api/leads/{sample_lead.id}/activities",
        json={"content": "Eerste notitie", "activity_type": "note"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["content"] == "Eerste notitie"
    assert body["activity_type"] == "note"


async def test_add_activity_with_mention_notifies_target(
    client, db_session, sample_lead, second_person
):
    """An @-mention in a note creates a 'mention' notification with related_lead_id."""
    tiptap_content = json.dumps(
        {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "mention",
                            "attrs": {
                                "id": str(second_person.id),
                                "label": second_person.naam,
                                "mentionType": "person",
                            },
                        },
                        {"type": "text", "text": " kun jij hierop reageren?"},
                    ],
                }
            ],
        }
    )

    resp = await client.post(
        f"/api/leads/{sample_lead.id}/activities",
        json={"content": tiptap_content, "activity_type": "note"},
    )
    assert resp.status_code == 201

    notifs = (
        (
            await db_session.execute(
                select(Notification).where(
                    Notification.person_id == second_person.id,
                    Notification.type == "mention",
                )
            )
        )
        .scalars()
        .all()
    )

    assert len(notifs) == 1
    assert notifs[0].related_lead_id == sample_lead.id
    assert "Test lead" in notifs[0].title


async def test_mentioned_assignee_only_gets_one_notification(
    client, db_session, assigned_lead, sample_person
):
    """Assignee gets only the lead_activity_added notification, not also a mention."""
    tiptap_content = json.dumps(
        {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "mention",
                            "attrs": {
                                "id": str(sample_person.id),
                                "label": sample_person.naam,
                                "mentionType": "person",
                            },
                        }
                    ],
                }
            ],
        }
    )

    resp = await client.post(
        f"/api/leads/{assigned_lead.id}/activities",
        json={"content": tiptap_content, "activity_type": "note"},
    )
    assert resp.status_code == 201

    notifs = (
        (
            await db_session.execute(
                select(Notification).where(Notification.person_id == sample_person.id)
            )
        )
        .scalars()
        .all()
    )

    assert len(notifs) == 1
    assert notifs[0].type == "lead_activity_added"
