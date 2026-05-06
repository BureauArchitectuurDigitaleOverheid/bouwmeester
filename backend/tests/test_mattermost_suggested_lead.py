"""Tests voor de suggested-lead flow + approval-actions."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.mattermost_channel_link import (
    SCOPE_INITIATIEF,
    MattermostChannelLink,
)
from bouwmeester.models.mattermost_user import MattermostUser
from bouwmeester.models.suggested_lead import SuggestedLead
from bouwmeester.services.llm.base import LeadCandidateClassification
from bouwmeester.services.mattermost_ingest_service import MattermostIngestService
from bouwmeester.services.mattermost_slash_service import MattermostSlashService


def _id() -> str:
    return uuid.uuid4().hex[:26]


@pytest.fixture
async def sample_initiatief(db_session):
    init = Initiatief(id=uuid.uuid4(), naam="Regelrecht")
    db_session.add(init)
    await db_session.flush()
    return init


@pytest.fixture
async def sample_channel(db_session, sample_initiatief):
    cid = _id()
    link = MattermostChannelLink(
        channel_id=cid,
        channel_name="alg",
        channel_display_name="Algemeen",
        scope_type=SCOPE_INITIATIEF,
        scope_id=sample_initiatief.id,
        auto_note_enabled=False,
        suggest_leads_enabled=True,
    )
    db_session.add(link)
    await db_session.flush()
    return link


def _llm_yes(title="Gemeente X", description="Wil iets met regelhulp"):
    return AsyncMock(
        return_value=LeadCandidateClassification(
            is_lead=True,
            confidence=0.82,
            proposed_title=title,
            proposed_description=description,
            match_existing_lead_id=None,
            reasoning="lijkt een nieuwe lead",
        )
    )


def _llm_no():
    return AsyncMock(
        return_value=LeadCandidateClassification(
            is_lead=False,
            confidence=0.1,
            proposed_title="",
            proposed_description="",
            match_existing_lead_id=None,
            reasoning="ack-bericht",
        )
    )


def _patch_llm(mock):
    """Patch zowel get_llm_service_for als de bot-reply-call."""
    fake_llm = AsyncMock()
    fake_llm.classify_mattermost_lead_candidate = mock
    return [
        patch(
            "bouwmeester.services.llm.factory.get_llm_service_for",
            new=AsyncMock(return_value=fake_llm),
        ),
        patch.object(
            MattermostIngestService,
            "_post_suggestion_reply",
            new=AsyncMock(return_value=None),
        ),
    ]


# ---------------------------------------------------------------------------
# Ingest pad
# ---------------------------------------------------------------------------


async def test_initiatief_channel_creates_suggested_lead(db_session, sample_channel):
    patches = _patch_llm(_llm_yes())
    for p in patches:
        p.start()
    try:
        ingest = MattermostIngestService(db_session)
        post = {
            "id": _id(),
            "channel_id": sample_channel.channel_id,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": "Gemeente X wil graag bij ons aanhaken op de regelhulp.",
        }
        await ingest.ingest_post(post)
    finally:
        for p in patches:
            p.stop()

    rows = (await db_session.execute(select(SuggestedLead))).scalars().all()
    assert len(rows) == 1
    sug = rows[0]
    assert sug.status == "pending"
    assert sug.proposed_title == "Gemeente X"
    assert sug.confidence == pytest.approx(0.82)
    assert sug.source_post_id == post["id"]


async def test_initiatief_channel_no_lead_when_llm_says_no(db_session, sample_channel):
    patches = _patch_llm(_llm_no())
    for p in patches:
        p.start()
    try:
        ingest = MattermostIngestService(db_session)
        post = {
            "id": _id(),
            "channel_id": sample_channel.channel_id,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": "ok 👍",
        }
        await ingest.ingest_post(post)
    finally:
        for p in patches:
            p.stop()

    sugs = (await db_session.execute(select(SuggestedLead))).scalars().all()
    assert sugs == []


# ---------------------------------------------------------------------------
# Approval-actions
# ---------------------------------------------------------------------------


async def test_create_lead_from_suggestion(
    db_session, sample_initiatief, sample_channel, create_person
):
    from bouwmeester.models.resource_permission import ResourcePermission

    person = await create_person(naam="Anne Reviewer", prefix="anne")
    mm_uid = _id()
    db_session.add(
        MattermostUser(
            person_id=person.id,
            mattermost_user_id=mm_uid,
            mattermost_username="anne",
        )
    )
    db_session.add(
        ResourcePermission(
            person_id=person.id,
            resource_type="initiatief",
            resource_id=sample_initiatief.id,
            rol="eigenaar",
        )
    )
    suggested = SuggestedLead(
        source_post_id=_id(),
        source_channel_id=sample_channel.channel_id,
        initiatief_id=sample_initiatief.id,
        proposed_title="Gemeente Y",
        proposed_description="Vraag over regelhulp",
        raw_text="Gemeente Y vraagt om een gesprek.",
        confidence=0.8,
        status="pending",
    )
    db_session.add(suggested)
    await db_session.flush()
    await db_session.refresh(suggested)

    with patch(
        "bouwmeester.services.mattermost_slash_service."
        "MattermostSlashService._update_thread_post",
        new=AsyncMock(return_value=None),
    ):
        service = MattermostSlashService(db_session)
        result = await service.handle_action(
            mattermost_user_id=mm_uid,
            action="create_lead_from_suggestion",
            context={"suggested_lead_id": str(suggested.id)},
        )

    assert "ephemeral_text" in result

    leads = (
        (
            await db_session.execute(
                select(Lead).where(Lead.initiatief_id == sample_initiatief.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(leads) == 1
    assert leads[0].title == "Gemeente Y"
    assert leads[0].brought_by_id == person.id

    activities = (await db_session.execute(select(LeadActivity))).scalars().all()
    assert len(activities) == 1
    assert "Gemeente Y" in (activities[0].content or "")

    await db_session.refresh(suggested)
    assert suggested.status == "approved_new"
    assert suggested.approved_lead_id == leads[0].id
    assert suggested.reviewed_by_id == person.id


async def test_reject_suggestion(
    db_session, sample_initiatief, sample_channel, create_person
):
    person = await create_person(naam="Anne", prefix="anne")
    mm_uid = _id()
    db_session.add(
        MattermostUser(
            person_id=person.id,
            mattermost_user_id=mm_uid,
            mattermost_username="anne",
        )
    )
    suggested = SuggestedLead(
        source_post_id=_id(),
        source_channel_id=sample_channel.channel_id,
        initiatief_id=sample_initiatief.id,
        proposed_title="Lijkt geen lead",
        raw_text="ok",
        status="pending",
    )
    db_session.add(suggested)
    await db_session.flush()
    await db_session.refresh(suggested)

    with patch(
        "bouwmeester.services.mattermost_slash_service."
        "MattermostSlashService._update_thread_post",
        new=AsyncMock(return_value=None),
    ):
        service = MattermostSlashService(db_session)
        await service.handle_action(
            mattermost_user_id=mm_uid,
            action="reject_suggestion",
            context={"suggested_lead_id": str(suggested.id)},
        )

    await db_session.refresh(suggested)
    assert suggested.status == "rejected"
    assert suggested.reviewed_by_id == person.id


async def test_approval_requires_linked_mattermost_user(
    db_session, sample_initiatief, sample_channel
):
    suggested = SuggestedLead(
        source_post_id=_id(),
        source_channel_id=sample_channel.channel_id,
        initiatief_id=sample_initiatief.id,
        proposed_title="X",
        status="pending",
    )
    db_session.add(suggested)
    await db_session.flush()

    service = MattermostSlashService(db_session)
    res = await service.handle_action(
        mattermost_user_id=_id(),
        action="create_lead_from_suggestion",
        context={"suggested_lead_id": str(suggested.id)},
    )
    assert res.get("text") == "Je account is niet gekoppeld."
    leads = (await db_session.execute(select(Lead))).scalars().all()
    assert leads == []
