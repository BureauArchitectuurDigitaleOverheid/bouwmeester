"""Tests voor herverwerking van posts na een LLM-storing.

Toen VLAM eruit lag, gaf ``classify_mattermost_lead_candidate`` bij een
connectiefout gewoon ``is_lead=False`` terug — niet te onderscheiden van een
echt oordeel "dit is geen lead". Gevolg: een duidelijke lead in een gekoppeld
kanaal werd weggeschreven als ``no_lead`` en was definitief verloren, want
``ingest_post`` slaat elke post over die al een ``mattermost_post_link``
heeft. De gebruiker kreeg bovendien te horen dat er geen lead in zat terwijl
er niemand naar gekeken had.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.mattermost_channel_link import (
    SCOPE_INITIATIEF,
    MattermostChannelLink,
)
from bouwmeester.models.mattermost_post_link import MattermostPostLink
from bouwmeester.services.llm.base import LeadCandidateClassification
from bouwmeester.services.mattermost_ingest_service import MattermostIngestService


def _id() -> str:
    return uuid.uuid4().hex[:26]


class FakeMattermostService:
    """Vangt replies op en serveert posts uit een dict."""

    replies: list[tuple[str, str, str]] = []
    posts: dict[str, dict] = {}

    def __init__(self, session):
        self.session = session

    async def is_enabled(self) -> bool:
        return True

    async def get_post(self, post_id):
        return FakeMattermostService.posts.get(post_id)

    async def reply_to_post(self, channel_id, root_id, message, *, props=None):
        FakeMattermostService.replies.append((channel_id, root_id, message))
        return {"id": _id()}

    async def add_reaction(self, post_id, emoji_name):
        return True

    async def close(self) -> None:
        return None


class FakeLLM:
    """LLM die faalt of slaagt, afhankelijk van ``fails``."""

    fails = True

    async def classify_mattermost_lead_candidate(self, **kwargs):
        if FakeLLM.fails:
            # Exact wat base.py teruggeeft bij een APIConnectionError.
            return LeadCandidateClassification(
                is_lead=False,
                confidence=0.0,
                proposed_title="",
                proposed_description="",
                match_existing_lead_id=None,
                reasoning="LLM-call mislukt",
                failed=True,
            )
        return LeadCandidateClassification(
            is_lead=True,
            confidence=0.9,
            proposed_title="Wetgevingsproces JenV",
            proposed_description="Hoofd wetgevingsbeleid wil capaciteit vrijmaken",
            match_existing_lead_id=None,
            reasoning="Concrete toezegging van capaciteit",
            failed=False,
        )


@pytest.fixture(autouse=True)
def _fakes(monkeypatch):
    FakeMattermostService.replies = []
    FakeMattermostService.posts = {}
    FakeLLM.fails = True
    monkeypatch.setattr(
        "bouwmeester.services.mattermost_service.MattermostService",
        FakeMattermostService,
    )

    async def fake_get_llm(sensitivity, session):
        return FakeLLM()

    monkeypatch.setattr(
        "bouwmeester.services.llm.factory.get_llm_service_for", fake_get_llm
    )
    yield


@pytest.fixture
async def initiatief_kanaal(db_session):
    init = Initiatief(id=uuid.uuid4(), naam=f"RegelRecht {uuid.uuid4().hex[:8]}")
    db_session.add(init)
    await db_session.flush()
    cid = _id()
    db_session.add(
        MattermostChannelLink(
            channel_id=cid,
            channel_name="leads",
            channel_display_name="Leads",
            scope_type=SCOPE_INITIATIEF,
            scope_id=init.id,
            auto_note_enabled=False,
            suggest_leads_enabled=True,
        )
    )
    await db_session.flush()
    return init, cid


async def _link_for(db_session, post_id) -> MattermostPostLink | None:
    return (
        await db_session.execute(
            select(MattermostPostLink).where(MattermostPostLink.post_id == post_id)
        )
    ).scalar_one_or_none()


async def test_llm_storing_is_geen_no_lead(db_session, initiatief_kanaal):
    """Een mislukte LLM-call mag niet als 'geen lead' geboekt worden."""
    _, cid = initiatief_kanaal
    post_id = _id()
    ingest = MattermostIngestService(
        db_session, bot_user_id=_id(), bot_username="bouwmeester"
    )
    await ingest.ingest_post(
        {
            "id": post_id,
            "channel_id": cid,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": "Hoofd wetgevingsbeleid JenV wil capaciteit vrijmaken.",
        }
    )

    link = await _link_for(db_session, post_id)
    assert link is not None
    assert link.skipped_reason == "llm_unavailable"


async def test_mention_meldt_storing_niet_als_oordeel(db_session, initiatief_kanaal):
    """De bot mag niet zeggen dat er geen lead in zit als hij niets wist."""
    _, cid = initiatief_kanaal
    ingest = MattermostIngestService(
        db_session, bot_user_id=_id(), bot_username="bouwmeester"
    )
    await ingest.ingest_post(
        {
            "id": _id(),
            "channel_id": cid,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": "@bouwmeester nu dan?",
        }
    )

    assert len(FakeMattermostService.replies) == 1
    reply = FakeMattermostService.replies[0][2]
    assert "niet beoordelen" in reply
    assert "geen nieuwe lead" not in reply


async def test_herverwerking_pakt_lead_alsnog_op(db_session, initiatief_kanaal):
    """Na herstel van de LLM wordt de gemiste lead alsnog voorgesteld."""
    _, cid = initiatief_kanaal
    post_id = _id()
    post = {
        "id": post_id,
        "channel_id": cid,
        "user_id": _id(),
        "create_at": 1_700_000_000_000,
        "message": "Hoofd wetgevingsbeleid JenV wil capaciteit vrijmaken.",
    }
    FakeMattermostService.posts[post_id] = post

    ingest = MattermostIngestService(
        db_session, bot_user_id=_id(), bot_username="bouwmeester"
    )
    await ingest.ingest_post(post)
    assert (await _link_for(db_session, post_id)).skipped_reason == "llm_unavailable"

    # VLAM is er weer.
    FakeLLM.fails = False
    processed, leads = await ingest.retry_llm_unavailable()

    assert processed == 1
    assert leads == 1
    link = await _link_for(db_session, post_id)
    assert link is not None
    assert link.suggested_lead_id is not None
    assert link.skipped_reason is None


async def test_herverwerking_dubbelt_geen_mention_bevestiging(
    db_session, initiatief_kanaal
):
    """Bij een herkansing geen tweede ':eyes: Gezien' in de thread.

    Anders zou een lange storing elke ronde opnieuw in de thread posten.
    """
    _, cid = initiatief_kanaal
    post_id = _id()
    post = {
        "id": post_id,
        "channel_id": cid,
        "user_id": _id(),
        "create_at": 1_700_000_000_000,
        "message": "@bouwmeester kijk hier eens naar",
    }
    FakeMattermostService.posts[post_id] = post

    ingest = MattermostIngestService(
        db_session, bot_user_id=_id(), bot_username="bouwmeester"
    )
    await ingest.ingest_post(post)
    replies_na_eerste = len(FakeMattermostService.replies)
    assert replies_na_eerste == 1

    # Storing duurt voort: herverwerking levert geen nieuwe bevestiging op.
    await ingest.retry_llm_unavailable()
    assert len(FakeMattermostService.replies) == replies_na_eerste


async def test_verwijderde_post_blijft_niet_in_de_wachtrij(
    db_session, initiatief_kanaal
):
    """Een in Mattermost verwijderde post wordt niet elke ronde opgehaald."""
    _, cid = initiatief_kanaal
    post_id = _id()
    post = {
        "id": post_id,
        "channel_id": cid,
        "user_id": _id(),
        "create_at": 1_700_000_000_000,
        "message": "Iets met een lead erin",
    }
    ingest = MattermostIngestService(
        db_session, bot_user_id=_id(), bot_username="bouwmeester"
    )
    await ingest.ingest_post(post)
    # Post bestaat niet meer in Mattermost (niet in FakeMattermostService.posts).

    processed, _ = await ingest.retry_llm_unavailable()
    assert processed == 0
    link = await _link_for(db_session, post_id)
    assert link is not None
    assert link.skipped_reason == "post_gone"
