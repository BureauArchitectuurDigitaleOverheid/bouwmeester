"""The lead suggestion leaks no other leads, to the LLM or into the channel.

The channel is read by people who may not read the initiatief's leads, and
the model's free text is not ours to vouch for.  So the model sees only the
message; a match with an existing lead is found here, by trigram
similarity; and the channel gets a neutral message, the proposal itself
only by DM to its author when they may read the initiatief.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.mattermost_channel_link import (
    SCOPE_INITIATIEF,
    MattermostChannelLink,
)
from bouwmeester.models.resource_permission import ResourcePermission
from bouwmeester.models.suggested_lead import SuggestedLead
from bouwmeester.services.llm.base import LeadCandidateClassification
from bouwmeester.services.mattermost_ingest_service import MattermostIngestService

SECRET_TITLE = "Geheime Onderhandeling Waterschap"
MODEL_TITLE = "Modeltitel Vrije Tekst"
MODEL_DESCRIPTION = "Modelbeschrijving met vrije tekst"


def _id() -> str:
    return uuid.uuid4().hex[:26]


@pytest.fixture
async def initiatief(db_session):
    init = Initiatief(id=uuid.uuid4(), naam="Regelrecht")
    db_session.add(init)
    db_session.add(
        Lead(
            id=uuid.uuid4(),
            title=SECRET_TITLE,
            organization="Waterschap Geheim",
            stage="lead",
            initiatief_id=init.id,
        )
    )
    await db_session.flush()
    return init


@pytest.fixture
async def channel(db_session, initiatief):
    link = MattermostChannelLink(
        channel_id=_id(),
        channel_name="alg",
        channel_display_name="Algemeen",
        scope_type=SCOPE_INITIATIEF,
        scope_id=initiatief.id,
        auto_note_enabled=False,
        suggest_leads_enabled=True,
    )
    db_session.add(link)
    await db_session.flush()
    return link


def _llm():
    llm = AsyncMock()
    llm.classify_mattermost_lead_candidate = AsyncMock(
        return_value=LeadCandidateClassification(
            is_lead=True,
            confidence=0.8,
            proposed_title=MODEL_TITLE,
            proposed_description=MODEL_DESCRIPTION,
            reasoning="nieuw",
        )
    )
    return llm


def _mm_stub():
    stub = AsyncMock()
    stub.is_enabled = AsyncMock(return_value=True)
    stub.reply_to_post = AsyncMock(return_value={"id": "thread-post"})
    stub.add_reaction = AsyncMock(return_value=True)
    stub.send_dm = AsyncMock(return_value=None)
    stub.close = AsyncMock(return_value=None)
    return stub


async def _ingest(db_session, channel, message, llm, stub):
    with (
        patch(
            "bouwmeester.services.llm.factory.get_llm_service_for",
            new=AsyncMock(return_value=llm),
        ),
        patch(
            "bouwmeester.services.mattermost_service.MattermostService",
            return_value=stub,
        ),
    ):
        await MattermostIngestService(db_session).ingest_post(
            {
                "id": _id(),
                "channel_id": channel.channel_id,
                "user_id": _id(),
                "create_at": 1_700_000_000_000,
                "message": message,
            }
        )


async def test_llm_sees_no_other_leads(db_session, channel):
    llm = _llm()
    await _ingest(db_session, channel, "Gemeente X wil aanhaken.", llm, _mm_stub())

    kwargs = llm.classify_mattermost_lead_candidate.await_args.kwargs
    assert SECRET_TITLE not in repr(kwargs)
    assert "Waterschap Geheim" not in repr(kwargs)


async def test_channel_gets_no_model_free_text(db_session, channel):
    stub = _mm_stub()
    await _ingest(db_session, channel, "Gemeente X wil aanhaken.", _llm(), stub)

    posted = repr(stub.reply_to_post.await_args)
    assert MODEL_TITLE not in posted
    assert MODEL_DESCRIPTION not in posted
    assert "Nieuwe lead" in posted


async def test_proposal_goes_by_dm_to_author_who_may_read(
    db_session, initiatief, create_person
):
    author = await create_person(naam="Schrijver", prefix="schrijver")
    db_session.add(
        ResourcePermission(
            person_id=author.id,
            resource_type="initiatief",
            resource_id=initiatief.id,
            rol="eigenaar",
        )
    )
    suggested = SuggestedLead(
        source_post_id=_id(),
        source_channel_id=_id(),
        initiatief_id=initiatief.id,
        proposed_title=MODEL_TITLE,
        proposed_description=MODEL_DESCRIPTION,
        raw_text="x",
        confidence=0.8,
        status="pending",
    )
    db_session.add(suggested)
    await db_session.flush()

    stub = _mm_stub()
    with patch(
        "bouwmeester.services.mattermost_service.MattermostService",
        return_value=stub,
    ):
        await MattermostIngestService(db_session)._post_suggestion_reply(
            channel_id="c",
            root_post_id="r",
            suggested=suggested,
            initiatief=initiatief,
            matched_lead=None,
            author_person_id=author.id,
        )

    stub.send_dm.assert_awaited_once()
    assert MODEL_TITLE in stub.send_dm.await_args.args[1]


async def test_no_dm_for_author_who_may_not_read(db_session, initiatief, create_person):
    outsider = await create_person(naam="Buiten", prefix="buiten")
    suggested = SuggestedLead(
        source_post_id=_id(),
        source_channel_id=_id(),
        initiatief_id=initiatief.id,
        proposed_title=MODEL_TITLE,
        raw_text="x",
        status="pending",
    )
    db_session.add(suggested)
    await db_session.flush()

    stub = _mm_stub()
    with patch(
        "bouwmeester.services.mattermost_service.MattermostService",
        return_value=stub,
    ):
        await MattermostIngestService(db_session)._post_suggestion_reply(
            channel_id="c",
            root_post_id="r",
            suggested=suggested,
            initiatief=initiatief,
            matched_lead=None,
            author_person_id=outsider.id,
        )

    stub.send_dm.assert_not_awaited()


async def test_existing_lead_is_matched_without_the_llm(db_session, channel):
    """The duplicate check runs here: a message naming the lead matches it."""
    stub = _mm_stub()
    await _ingest(
        db_session,
        channel,
        "Waterschap Geheim heeft een vervolgvraag.",
        _llm(),
        stub,
    )

    suggested = (
        await db_session.execute(
            SuggestedLead.__table__.select().where(
                SuggestedLead.source_channel_id == channel.channel_id
            )
        )
    ).one()
    assert suggested.match_existing_lead_id is not None
    assert "bestaande lead" in repr(stub.reply_to_post.await_args).lower()
    assert SECRET_TITLE not in repr(stub.reply_to_post.await_args)
