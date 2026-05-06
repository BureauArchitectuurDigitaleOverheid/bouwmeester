"""Tests voor LLM-ruisfilter + thread-samenvatting in lead-kanalen."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.mattermost_channel_link import (
    SCOPE_LEAD,
    MattermostChannelLink,
)
from bouwmeester.models.mattermost_post_link import MattermostPostLink
from bouwmeester.services.mattermost_ingest_service import MattermostIngestService


def _id() -> str:
    return uuid.uuid4().hex[:26]


@pytest.fixture
async def lead_channel(db_session):
    init = Initiatief(id=uuid.uuid4(), naam="X")
    db_session.add(init)
    await db_session.flush()
    lead = Lead(
        id=uuid.uuid4(),
        title="Test lead",
        stage="inbox",
        initiatief_id=init.id,
    )
    db_session.add(lead)
    await db_session.flush()
    cid = _id()
    link = MattermostChannelLink(
        channel_id=cid,
        channel_name="proj",
        channel_display_name="Project",
        scope_type=SCOPE_LEAD,
        scope_id=lead.id,
        auto_note_enabled=True,
    )
    db_session.add(link)
    await db_session.flush()
    return lead, link


def _patch_llm(*, is_noise: bool = False, summary: str | None = None):
    fake = AsyncMock()
    fake.is_mattermost_noise = AsyncMock(return_value=is_noise)
    fake.summarize_mattermost_message = AsyncMock(return_value=summary or "")
    return patch(
        "bouwmeester.services.llm.factory.get_llm_service_for",
        new=AsyncMock(return_value=fake),
    )


async def test_noise_message_skips_activity(db_session, lead_channel):
    lead, link = lead_channel
    with _patch_llm(is_noise=True):
        ingest = MattermostIngestService(db_session)
        post = {
            "id": _id(),
            "channel_id": link.channel_id,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": "ja prima dat klopt",
        }
        await ingest.ingest_post(post)

    activities = (
        (
            await db_session.execute(
                select(LeadActivity).where(LeadActivity.lead_id == lead.id)
            )
        )
        .scalars()
        .all()
    )
    assert activities == []
    pl = (
        await db_session.execute(
            select(MattermostPostLink).where(MattermostPostLink.post_id == post["id"])
        )
    ).scalar_one()
    assert pl.skipped_reason == "noise"


async def test_short_message_is_noise_via_heuristic(db_session, lead_channel):
    lead, link = lead_channel
    # LLM mag niet eens worden aangeroepen — heuristiek pakt het voor < 4 chars.
    fake = AsyncMock()
    fake.is_mattermost_noise = AsyncMock(return_value=False)
    fake.summarize_mattermost_message = AsyncMock(return_value="")
    with patch(
        "bouwmeester.services.llm.factory.get_llm_service_for",
        new=AsyncMock(return_value=fake),
    ):
        ingest = MattermostIngestService(db_session)
        post = {
            "id": _id(),
            "channel_id": link.channel_id,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": "ok",
        }
        await ingest.ingest_post(post)

    activities = (
        (
            await db_session.execute(
                select(LeadActivity).where(LeadActivity.lead_id == lead.id)
            )
        )
        .scalars()
        .all()
    )
    assert activities == []
    fake.is_mattermost_noise.assert_not_called()


async def test_long_message_is_summarized(db_session, lead_channel):
    lead, link = lead_channel
    long_msg = "Update: " + ("Dit is een uitgebreid verslag. " * 40)
    summary = "Korte samenvatting van het verslag."
    with _patch_llm(is_noise=False, summary=summary):
        ingest = MattermostIngestService(db_session)
        post = {
            "id": _id(),
            "channel_id": link.channel_id,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": long_msg,
        }
        await ingest.ingest_post(post)

    activity = (
        await db_session.execute(
            select(LeadActivity).where(LeadActivity.lead_id == lead.id)
        )
    ).scalar_one()
    assert summary in (activity.content or "")
    assert activity.metadata_["mm_original"].startswith("Update:")


async def test_normal_message_passes_through(db_session, lead_channel):
    lead, link = lead_channel
    msg = "Gemeente X belde net. Willen volgende week kennismaken."
    with _patch_llm(is_noise=False, summary=""):
        ingest = MattermostIngestService(db_session)
        post = {
            "id": _id(),
            "channel_id": link.channel_id,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": msg,
        }
        await ingest.ingest_post(post)

    activity = (
        await db_session.execute(
            select(LeadActivity).where(LeadActivity.lead_id == lead.id)
        )
    ).scalar_one()
    assert msg in (activity.content or "")
    assert "mm_original" not in activity.metadata_
