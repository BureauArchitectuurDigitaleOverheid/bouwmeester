"""What lead content reaches a language model, a channel and a DM.

Uses ``world`` from ``tests/authz_world.py``: the afdeling owns the
initiatief (its editor reads it and holds people:read), ``role_only`` is a
contributor on it.  A Mattermost channel is read by people who may not read
the initiatief's leads and the model's free text is not ours to vouch for:
the model sees only the message, a match with an existing lead is found
here, and the channel gets a neutral message; the proposal itself goes by
DM to its author only when they may read the initiatief.
"""

import logging
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from bouwmeester.api.routes import leads as leads_module
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.mattermost_channel_link import (
    SCOPE_INITIATIEF,
    MattermostChannelLink,
)
from bouwmeester.models.suggested_lead import SuggestedLead
from bouwmeester.services.llm import DataSensitivity
from bouwmeester.services.llm.base import LeadCandidateClassification
from bouwmeester.services.mattermost_ingest_service import MattermostIngestService
from bouwmeester.services.mattermost_slash_service import MattermostSlashService
from tests.authz_world import World, add, mm_account, mm_id, request, rp
from tests.factories import make_person

SECRET_TITLE = "Geheime Onderhandeling Waterschap"
MODEL_TITLE = "Modeltitel Vrije Tekst"
MODEL_DESCRIPTION = "Modelbeschrijving met vrije tekst"
_DRAFT = '{"titel": "T", "body_internal": "B", "body_public": "P"}'
_INTAKE = '{"title": "Lead", "contact_email": "geheim@example.org"}'

# ---------------------------------------------------------------------------
# Lead routes that prompt a model
# ---------------------------------------------------------------------------


@pytest.fixture
async def llm(monkeypatch):
    """A fake language model; records the sensitivity asked and the prompts."""
    fake = AsyncMock()
    fake.asked = []
    fake._complete = AsyncMock(return_value=_DRAFT)

    async def _for(sensitivity, _db):
        fake.asked.append(sensitivity)
        return fake

    monkeypatch.setattr(leads_module, "get_llm_service_for", _for)
    return fake


@pytest.fixture
async def lw(world: World) -> World:
    """An opdrachtgever placed nowhere (writes the lead, reads neither the
    initiatief nor the people directory) and a contact on the lead."""
    opdrachtgever = await make_person(world.db, "Opdrachtgever")
    contact = await make_person(world.db, "Contact")
    lead = world.res["lead"]
    await add(
        world,
        rp("lead", lead, "opdrachtgever", person=opdrachtgever),
        rp("lead", lead, "contactpersoon", person=contact),
    )
    world.person.update(opdrachtgever=opdrachtgever, contact=contact)
    return world


async def _parse_update(w: World, who: str):
    return await request(
        w, who, "POST", "/api/leads/{lead}/updates/parse", data={"raw_text": "Kort"}
    )


async def _intake(w: World, who: str, **data):
    return await request(
        w, who, "POST", "/api/leads/parse-intake", data={"raw_text": "Mail", **data}
    )


async def test_update_prompt_holds_only_what_the_caller_may_read(lw, llm):
    initiatief = await lw.db.get(Initiatief, lw.res["initiatief"])
    email = lw.person["contact"].email
    for who, reads in (("opdrachtgever", False), ("afd_editor", True)):
        resp = await _parse_update(lw, who)
        assert resp.status_code == 200, resp.text
        prompt = llm._complete.await_args.args[0]
        assert "Contact" in prompt  # the lead's contacts are on the lead itself
        assert (initiatief.naam in prompt) is reads
        assert (email in prompt) is reads
        assert (email in resp.json()["suggested_to"]) is reads


async def test_lead_prompts_only_go_to_a_confidential_model(lw, llm, monkeypatch):
    await _parse_update(lw, "afd_editor")
    await _intake(lw, "team_editor")
    assert llm.asked == [DataSensitivity.CONFIDENTIAL] * 2

    async def _none(_sensitivity, _db):
        return None

    monkeypatch.setattr(leads_module, "get_llm_service_for", _none)
    assert (await _parse_update(lw, "afd_editor")).status_code == 503


@pytest.mark.parametrize(
    ("who", "with_initiatief", "expected"),
    [
        ("team_editor", False, 200),  # creates leads in the own team
        ("viewer", False, 403),  # creates leads nowhere
        ("role_only", False, 403),  # only in the initiatief
        ("role_only", True, 200),
        ("team_editor", True, 403),  # sees the initiatief, may not add to it
    ],
)
async def test_parse_intake_is_for_who_may_create_a_lead(
    lw, llm, who, with_initiatief, expected
):
    llm._complete.return_value = _INTAKE
    extra = {"initiatief_id": str(lw.res["initiatief"])} if with_initiatief else {}
    assert (await _intake(lw, who, **extra)).status_code == expected


@pytest.mark.parametrize("too_many", [True, False])
async def test_parse_intake_limits_uploads(lw, llm, too_many):
    if too_many:
        n, size = leads_module.MAX_LLM_UPLOADS + 1, 1
    else:
        n, size = 1, leads_module.MAX_LLM_UPLOAD_BYTES + 1
    files = [("files", (f"f{i}.txt", b"x" * size, "text/plain")) for i in range(n)]
    resp = await request(
        lw, "team_editor", "POST", "/api/leads/parse-intake", files=files
    )
    assert resp.status_code == 400, resp.text
    llm._complete.assert_not_awaited()


async def test_parse_intake_does_not_log_the_model_output(lw, llm, caplog):
    llm._complete.return_value = _INTAKE
    with caplog.at_level(logging.DEBUG):
        ok = await _intake(lw, "team_editor")
        llm._complete.return_value = "geen json, wel geheim@example.org"
        broken = await _intake(lw, "team_editor")
    assert ok.status_code == 200, ok.text
    assert broken.status_code == 500, broken.text
    assert "geheim@example.org" not in caplog.text


# ---------------------------------------------------------------------------
# Mattermost lead suggestions
# ---------------------------------------------------------------------------


@pytest.fixture
async def channel(world: World) -> MattermostChannelLink:
    """A suggesting channel of the initiatief, which holds a secret lead."""
    secret = Lead(
        title=SECRET_TITLE,
        organization="Waterschap Geheim",
        stage="lead",
        initiatief_id=world.res["initiatief"],
    )
    link = MattermostChannelLink(
        channel_id=mm_id(),
        channel_name="alg",
        channel_display_name="Algemeen",
        scope_type=SCOPE_INITIATIEF,
        scope_id=world.res["initiatief"],
        auto_note_enabled=False,
        suggest_leads_enabled=True,
    )
    await add(world, secret, link)
    world.res["secret_lead"] = secret.id
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
    stub.send_dm = AsyncMock(return_value=True)
    stub.update_post = AsyncMock(return_value=True)
    stub.close = AsyncMock(return_value=None)
    return stub


def _patched(stub, llm=None):
    patches = [
        patch(
            "bouwmeester.services.mattermost_service.MattermostService",
            return_value=stub,
        )
    ]
    if llm is not None:
        patches.append(
            patch(
                "bouwmeester.services.llm.factory.get_llm_service_for",
                new=AsyncMock(return_value=llm),
            )
        )
    return patches


async def _ingest(w: World, channel, message: str, llm, stub):
    p1, p2 = _patched(stub, llm)
    with p1, p2:
        await MattermostIngestService(w.db).ingest_post(
            {"id": mm_id(), "channel_id": channel.channel_id, "user_id": mm_id(),
             "create_at": 1_700_000_000_000, "message": message}
        )  # fmt: skip


async def test_model_sees_the_message_and_the_channel_no_free_text(world, channel):
    llm, stub = _llm(), _mm_stub()
    await _ingest(world, channel, "Gemeente X wil aanhaken.", llm, stub)
    prompt = repr(llm.classify_mattermost_lead_candidate.await_args.kwargs)
    assert SECRET_TITLE not in prompt
    assert "Waterschap Geheim" not in prompt
    posted = repr(stub.reply_to_post.await_args)
    assert MODEL_TITLE not in posted
    assert MODEL_DESCRIPTION not in posted
    assert "Nieuwe lead" in posted


async def test_existing_lead_is_matched_without_the_model(world, channel):
    stub = _mm_stub()
    message = "Waterschap Geheim heeft een vervolgvraag."
    await _ingest(world, channel, message, _llm(), stub)
    suggested = await world.db.scalar(
        select(SuggestedLead).where(
            SuggestedLead.source_channel_id == channel.channel_id
        )
    )
    assert suggested.match_existing_lead_id is not None
    posted = repr(stub.reply_to_post.await_args)
    assert "bestaande lead" in posted.lower()
    assert SECRET_TITLE not in posted


# (matched a lead?, author, DM): readers of the initiatief get the proposal
# or the recognised lead by DM; the channel never names either.
DM_CASES = [
    (False, "role_only", True),
    (False, "outsider", False),
    (True, "role_only", True),
    (True, "outsider", False),
]


@pytest.mark.parametrize(("matched", "author", "dm"), DM_CASES)
async def test_proposal_is_named_only_by_dm_to_a_reader(world, matched, author, dm):
    world.person["outsider"] = await make_person(world.db, "Buitenstaander")
    initiatief = await world.db.get(Initiatief, world.res["initiatief"])
    lead = await world.db.get(Lead, world.res["lead"])
    lead.title = "Geheime gemeente"
    suggested = await add(
        world,
        SuggestedLead(
            source_post_id=mm_id(), source_channel_id="c" * 26,
            initiatief_id=initiatief.id, proposed_title=MODEL_TITLE,
            proposed_description=MODEL_DESCRIPTION, raw_text="x", confidence=0.8,
            status="pending",
        ),
    )  # fmt: skip
    matched_lead = (
        {"id": lead.id, "title": lead.title, "stage": lead.stage,
         "stage_label": "Verkennen"}
        if matched else None
    )  # fmt: skip
    stub = _mm_stub()
    person_id = world.person[author].id
    with _patched(stub)[0]:
        await MattermostIngestService(world.db)._post_suggestion_reply(
            channel_id="c" * 26, root_post_id="root", suggested=suggested,
            initiatief=initiatief, matched_lead=matched_lead,
            author_person_id=person_id,
        )  # fmt: skip
    posted = str(stub.reply_to_post.await_args)
    for secret in ("Geheime gemeente", "Verkennen", MODEL_TITLE):
        assert secret not in posted
    if not dm:
        stub.send_dm.assert_not_awaited()
        return
    stub.send_dm.assert_awaited_once()
    to, text = stub.send_dm.await_args.args[:2]
    assert to == person_id
    assert ("Geheime gemeente" if matched else MODEL_TITLE) in text


async def test_approving_posts_no_model_title_in_the_channel(world):
    """Approving from Mattermost: neutral text in the channel, title to the
    clicker (a contributor, so initiatief:update)."""
    mm_uid = await mm_account(world, "role_only")
    suggested = await add(
        world,
        SuggestedLead(
            source_post_id=mm_id(), source_channel_id=mm_id(),
            initiatief_id=world.res["initiatief"], proposed_title=MODEL_TITLE,
            raw_text="x", status="pending", mm_thread_post_id="thread-post",
        ),
    )  # fmt: skip
    stub = _mm_stub()
    with _patched(stub)[0]:
        result = await MattermostSlashService(world.db).handle_action(
            mattermost_user_id=mm_uid,
            action="create_lead_from_suggestion",
            context={"suggested_lead_id": str(suggested.id)},
        )
    stub.update_post.assert_awaited_once()
    assert MODEL_TITLE not in repr(stub.update_post.await_args)
    assert MODEL_TITLE in result["ephemeral_text"]
