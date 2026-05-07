"""Tests voor MattermostIngestService: auto-note op lead-kanalen + doc-links."""

import uuid

import pytest
from sqlalchemy import select

from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.lead_attachment import LeadAttachment
from bouwmeester.models.mattermost_channel_link import (
    SCOPE_INITIATIEF,
    SCOPE_LEAD,
    MattermostChannelLink,
)
from bouwmeester.models.mattermost_post_link import MattermostPostLink
from bouwmeester.models.mattermost_user import MattermostUser
from bouwmeester.services.mattermost_doc_link_extractor import (
    derive_attachment_label,
    extract_doc_links,
)
from bouwmeester.services.mattermost_ingest_service import MattermostIngestService


def _id() -> str:
    return uuid.uuid4().hex[:26]


@pytest.fixture
async def sample_initiatief(db_session):
    init = Initiatief(id=uuid.uuid4(), naam="Test initiatief")
    db_session.add(init)
    await db_session.flush()
    return init


@pytest.fixture
async def sample_lead(db_session, sample_initiatief):
    lead = Lead(
        id=uuid.uuid4(),
        title="Test lead",
        stage="inbox",
        initiatief_id=sample_initiatief.id,
    )
    db_session.add(lead)
    await db_session.flush()
    return lead


# ---------------------------------------------------------------------------
# Doc-link-extractor
# ---------------------------------------------------------------------------


def test_extract_doc_links_pikt_drive_op():
    msg = "Notulen: https://drive.google.com/file/d/abc/view"
    links = extract_doc_links(msg)
    assert len(links) == 1
    assert links[0]["url"].endswith("/view")
    assert links[0]["host"] == "drive.google.com"


def test_extract_doc_links_pikt_pdf_op_buiten_known_host():
    msg = "Bekijk de pdf op https://example.org/files/report.pdf voor details."
    links = extract_doc_links(msg)
    assert len(links) == 1
    assert links[0]["url"].endswith("report.pdf")


def test_extract_doc_links_negeert_gewone_artikelen():
    msg = "Zie https://nos.nl/artikel/123-overheid voor context."
    assert extract_doc_links(msg) == []


def test_extract_doc_links_dedupes_en_volgorde():
    msg = (
        "https://drive.google.com/file/d/A "
        "en https://drive.google.com/file/d/A nogmaals, plus "
        "https://atlassian.net/wiki/x"
    )
    links = extract_doc_links(msg)
    assert [link["url"] for link in links] == [
        "https://drive.google.com/file/d/A",
        "https://atlassian.net/wiki/x",
    ]


def test_extract_doc_links_strips_trailing_punctuation():
    msg = "Zie (https://drive.google.com/file/d/abc), prima."
    links = extract_doc_links(msg)
    assert links[0]["url"] == "https://drive.google.com/file/d/abc"


def test_derive_attachment_label_known_hosts():
    assert derive_attachment_label("https://drive.google.com/x") == "Google Drive"
    assert derive_attachment_label("https://team.atlassian.net/wiki/x") == "Confluence"
    assert (
        derive_attachment_label("https://contoso.sharepoint.com/x")
        == "SharePoint/OneDrive"
    )
    assert derive_attachment_label("https://www.example.org/file.pdf") == "example.org"


# ---------------------------------------------------------------------------
# Auto-note op lead-kanalen
# ---------------------------------------------------------------------------


async def test_lead_channel_creates_auto_note(db_session, sample_lead):
    cid = _id()
    db_session.add(
        MattermostChannelLink(
            channel_id=cid,
            channel_name="proj",
            channel_display_name="Project",
            scope_type=SCOPE_LEAD,
            scope_id=sample_lead.id,
            auto_note_enabled=True,
            suggest_leads_enabled=False,
        )
    )
    await db_session.flush()

    ingest = MattermostIngestService(db_session, mm_base_url="https://mm.example.org")
    post = {
        "id": _id(),
        "channel_id": cid,
        "user_id": _id(),
        "create_at": 1_700_000_000_000,
        "message": "Stand van zaken: gemeente X wacht op antwoord.",
    }
    await ingest.ingest_post(post)

    activities = (
        (
            await db_session.execute(
                select(LeadActivity).where(LeadActivity.lead_id == sample_lead.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(activities) == 1
    activity = activities[0]
    assert activity.activity_type == "note"
    assert "gemeente X" in activity.content
    assert activity.metadata_["source"] == "mattermost"
    assert activity.metadata_["mm_post_id"] == post["id"]
    assert activity.metadata_["mm_permalink"].endswith(post["id"])

    post_link = (
        await db_session.execute(
            select(MattermostPostLink).where(MattermostPostLink.post_id == post["id"])
        )
    ).scalar_one()
    assert post_link.lead_activity_id == activity.id


async def test_lead_channel_extracts_doc_link_attachment(db_session, sample_lead):
    cid = _id()
    db_session.add(
        MattermostChannelLink(
            channel_id=cid,
            channel_name="proj",
            channel_display_name="Project",
            scope_type=SCOPE_LEAD,
            scope_id=sample_lead.id,
            auto_note_enabled=True,
        )
    )
    await db_session.flush()

    ingest = MattermostIngestService(db_session)
    post = {
        "id": _id(),
        "channel_id": cid,
        "user_id": _id(),
        "create_at": 1_700_000_000_000,
        "message": "Notulen: https://drive.google.com/file/d/xyz/view",
    }
    await ingest.ingest_post(post)

    attachments = (
        (
            await db_session.execute(
                select(LeadAttachment).where(LeadAttachment.lead_id == sample_lead.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(attachments) == 1
    att = attachments[0]
    assert att.soort == "link"
    assert att.url == "https://drive.google.com/file/d/xyz/view"
    assert att.source == "mattermost"
    assert att.source_ref == post["id"]
    assert att.bestandsnaam == "Google Drive"
    # File-velden mogen leeg zijn voor URL-attachments.
    assert att.pad is None
    assert att.bestandsgrootte is None


async def test_lead_channel_dedupes_attachment_url(db_session, sample_lead):
    cid = _id()
    db_session.add(
        MattermostChannelLink(
            channel_id=cid,
            channel_name="proj",
            channel_display_name="Project",
            scope_type=SCOPE_LEAD,
            scope_id=sample_lead.id,
            auto_note_enabled=True,
        )
    )
    await db_session.flush()

    ingest = MattermostIngestService(db_session)
    url = "https://drive.google.com/file/d/dup/view"
    for _ in range(2):
        post = {
            "id": _id(),
            "channel_id": cid,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": f"Document: {url}",
        }
        await ingest.ingest_post(post)

    attachments = (
        (
            await db_session.execute(
                select(LeadAttachment).where(
                    LeadAttachment.lead_id == sample_lead.id,
                    LeadAttachment.url == url,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(attachments) == 1


async def test_lead_channel_resolves_author_via_mattermost_link(
    db_session, sample_lead, create_person
):
    """Als de MM-user gekoppeld is aan een Person → author_id wordt gezet."""
    person = await create_person(naam="Geanne Test", prefix="geanne")
    cid = _id()
    mm_uid = _id()
    db_session.add(
        MattermostChannelLink(
            channel_id=cid,
            channel_name="proj",
            channel_display_name="Project",
            scope_type=SCOPE_LEAD,
            scope_id=sample_lead.id,
            auto_note_enabled=True,
        )
    )
    db_session.add(
        MattermostUser(
            person_id=person.id,
            mattermost_user_id=mm_uid,
            mattermost_username="geanne",
        )
    )
    await db_session.flush()

    ingest = MattermostIngestService(db_session)
    post = {
        "id": _id(),
        "channel_id": cid,
        "user_id": mm_uid,
        "create_at": 1_700_000_000_000,
        "message": "Update vanuit Geanne.",
    }
    await ingest.ingest_post(post)

    activity = (
        await db_session.execute(
            select(LeadActivity).where(LeadActivity.lead_id == sample_lead.id)
        )
    ).scalar_one()
    assert activity.author_id == person.id
    # Geen "via mm:@..." prefix als auteur bekend is.
    assert "via mm:" not in activity.content


async def test_lead_channel_unlinked_author_uses_via_prefix(db_session, sample_lead):
    cid = _id()
    db_session.add(
        MattermostChannelLink(
            channel_id=cid,
            channel_name="proj",
            channel_display_name="Project",
            scope_type=SCOPE_LEAD,
            scope_id=sample_lead.id,
            auto_note_enabled=True,
        )
    )
    await db_session.flush()

    ingest = MattermostIngestService(db_session)
    mm_uid = _id()
    post = {
        "id": _id(),
        "channel_id": cid,
        "user_id": mm_uid,
        "create_at": 1_700_000_000_000,
        "message": "Onbekende afzender",
    }
    await ingest.ingest_post(post)

    activity = (
        await db_session.execute(
            select(LeadActivity).where(LeadActivity.lead_id == sample_lead.id)
        )
    ).scalar_one()
    assert activity.author_id is None
    assert f"via mm:@{mm_uid}" in activity.content


async def test_lead_channel_renders_at_mentions_as_tiptap(
    db_session, sample_lead, create_person
):
    """``@username`` van een gekoppeld persoon wordt een TipTap-mention
    zodat de frontend een klikbare badge kan tonen."""
    import json

    from bouwmeester.models.mention import Mention
    from bouwmeester.models.notification import Notification

    anne = await create_person(naam="Anne Schuth", prefix="anne.schuth")
    daan = await create_person(naam="Daan Wijnhorst", prefix="daan")
    cid = _id()
    daan_mm_uid = _id()
    db_session.add_all(
        [
            MattermostChannelLink(
                channel_id=cid,
                channel_name="proj",
                channel_display_name="Project",
                scope_type=SCOPE_LEAD,
                scope_id=sample_lead.id,
                auto_note_enabled=True,
            ),
            MattermostUser(
                person_id=anne.id,
                mattermost_user_id=_id(),
                mattermost_username="anne.schuth-rijksoverheid",
            ),
            MattermostUser(
                person_id=daan.id,
                mattermost_user_id=daan_mm_uid,
                mattermost_username="daan",
            ),
        ]
    )
    await db_session.flush()

    ingest = MattermostIngestService(db_session)
    post = {
        "id": _id(),
        "channel_id": cid,
        "user_id": daan_mm_uid,
        "create_at": 1_700_000_000_000,
        "message": ("@anne.schuth-rijksoverheid handig om ff over WOW te overleggen"),
    }
    await ingest.ingest_post(post)

    activity = (
        await db_session.execute(
            select(LeadActivity).where(LeadActivity.lead_id == sample_lead.id)
        )
    ).scalar_one()

    doc = json.loads(activity.content)
    assert doc["type"] == "doc"
    inline = doc["content"][0]["content"]
    mention_nodes = [n for n in inline if n["type"] == "mention"]
    assert len(mention_nodes) == 1
    assert mention_nodes[0]["attrs"]["id"] == str(anne.id)
    assert mention_nodes[0]["attrs"]["label"] == "Anne Schuth"
    assert mention_nodes[0]["attrs"]["mentionType"] == "person"

    # Mention-record voor back-references.
    mentions = (
        (
            await db_session.execute(
                select(Mention).where(
                    Mention.source_type == "lead_activity",
                    Mention.source_id == activity.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert [m.target_id for m in mentions] == [anne.id]

    # Anne krijgt een notification, Daan (de auteur) niet.
    notifs = (
        (
            await db_session.execute(
                select(Notification).where(Notification.type == "mention")
            )
        )
        .scalars()
        .all()
    )
    assert [n.person_id for n in notifs] == [anne.id]
    assert notifs[0].related_lead_id == sample_lead.id


async def test_lead_channel_unknown_username_stays_plain_text(db_session, sample_lead):
    """Een ``@username`` zonder MattermostUser-koppeling blijft platte tekst."""
    cid = _id()
    db_session.add(
        MattermostChannelLink(
            channel_id=cid,
            channel_name="proj",
            channel_display_name="Project",
            scope_type=SCOPE_LEAD,
            scope_id=sample_lead.id,
            auto_note_enabled=True,
        )
    )
    await db_session.flush()

    ingest = MattermostIngestService(db_session)
    post = {
        "id": _id(),
        "channel_id": cid,
        "user_id": _id(),
        "create_at": 1_700_000_000_000,
        "message": "@onbekend hoi",
    }
    await ingest.ingest_post(post)

    activity = (
        await db_session.execute(
            select(LeadActivity).where(LeadActivity.lead_id == sample_lead.id)
        )
    ).scalar_one()
    # Geen TipTap, geen mention-node — gewoon de oorspronkelijke tekst.
    assert "@onbekend hoi" in activity.content
    assert not activity.content.startswith("{")


async def test_lead_channel_with_auto_note_disabled_skips_activity(
    db_session, sample_lead
):
    cid = _id()
    db_session.add(
        MattermostChannelLink(
            channel_id=cid,
            channel_name="proj",
            channel_display_name="Project",
            scope_type=SCOPE_LEAD,
            scope_id=sample_lead.id,
            auto_note_enabled=False,
        )
    )
    await db_session.flush()

    ingest = MattermostIngestService(db_session)
    post = {
        "id": _id(),
        "channel_id": cid,
        "user_id": _id(),
        "create_at": 1_700_000_000_000,
        "message": "Iets",
    }
    await ingest.ingest_post(post)

    activities = (
        (
            await db_session.execute(
                select(LeadActivity).where(LeadActivity.lead_id == sample_lead.id)
            )
        )
        .scalars()
        .all()
    )
    assert activities == []
    # Wel een post_link zodat we niet opnieuw verwerken.
    post_link = (
        await db_session.execute(
            select(MattermostPostLink).where(MattermostPostLink.post_id == post["id"])
        )
    ).scalar_one()
    assert post_link.lead_activity_id is None


async def test_initiatief_channel_writes_only_post_link(db_session, sample_initiatief):
    """Initiatief-kanalen krijgen pas in PR3 suggested leads. Voor nu: alleen
    een post_link-record, geen LeadActivity, geen LeadAttachment."""
    cid = _id()
    db_session.add(
        MattermostChannelLink(
            channel_id=cid,
            channel_name="alg",
            channel_display_name="Algemeen",
            scope_type=SCOPE_INITIATIEF,
            scope_id=sample_initiatief.id,
            auto_note_enabled=False,
            suggest_leads_enabled=True,
        )
    )
    await db_session.flush()

    ingest = MattermostIngestService(db_session)
    post = {
        "id": _id(),
        "channel_id": cid,
        "user_id": _id(),
        "create_at": 1_700_000_000_000,
        "message": "Mogelijk een nieuwe lead?",
    }
    await ingest.ingest_post(post)

    post_link = (
        await db_session.execute(
            select(MattermostPostLink).where(MattermostPostLink.post_id == post["id"])
        )
    ).scalar_one()
    assert post_link.lead_activity_id is None
    assert post_link.scope_type == SCOPE_INITIATIEF


# ---------------------------------------------------------------------------
# DM-pad: link-codes via websocket-event ipv polling
# ---------------------------------------------------------------------------


def _patch_dm_session(db_session):
    """Patch ``async_session`` in ``mattermost_ingest_service`` zodat
    ``handle_dm_post`` op de test-session werkt ipv een eigen verbinding.

    ``commit()`` en ``rollback()`` op de inner session worden no-op
    gemaakt zodat de outer test-rollback alle DM-writes afvoert en een
    inner-rollback de outer-session niet vernielt — in productie zou
    ``handle_dm_post`` op een aparte session werken, dus de outer-session
    moet ongeacht inner-uitkomst bruikbaar blijven.
    """
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, patch

    @asynccontextmanager
    async def _fake_session():
        original_commit = db_session.commit
        original_rollback = db_session.rollback
        db_session.commit = AsyncMock(return_value=None)
        db_session.rollback = AsyncMock(return_value=None)
        try:
            yield db_session
        finally:
            db_session.commit = original_commit
            db_session.rollback = original_rollback

    return patch(
        "bouwmeester.services.mattermost_ingest_service.async_session",
        new=_fake_session,
    )


async def test_dm_post_with_valid_code_creates_mapping(db_session, create_person):
    """Een DM met een geldige BM-code koppelt het Mattermost-account aan
    de bijbehorende persoon — dezelfde uitkomst als de oude poller, maar
    nu via het websocket-pad in ``ingest_post``."""
    from unittest.mock import AsyncMock, patch

    from bouwmeester.repositories.mattermost_user import MattermostUserRepository

    person = await create_person(naam="DM Tester", prefix="dm")
    repo = MattermostUserRepository(db_session)
    code = await repo.create_link_code(person.id)

    mm_uid = _id()
    post = {
        "id": _id(),
        "channel_id": _id(),
        "user_id": mm_uid,
        "create_at": 1_700_000_000_000,
        "message": f"hoi, mijn code is {code.code}",
    }

    ingest = MattermostIngestService(db_session)
    with (
        _patch_dm_session(db_session),
        patch(
            "bouwmeester.services.mattermost_link_poller."
            "MattermostLinkPoller._safe_reply",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "bouwmeester.services.mattermost_service.MattermostService.get_username",
            new=AsyncMock(return_value="dm_user"),
        ),
    ):
        await ingest.ingest_post(post, channel_type="D")

    mapping = await repo.get_by_mattermost_user_id(mm_uid)
    assert mapping is not None
    assert mapping.person_id == person.id
    assert mapping.mattermost_username == "dm_user"
    # Code is verbruikt.
    assert await repo.verify_code(code.code) is None
    # Geen MattermostPostLink voor DMs — dat record is alleen voor
    # gekoppelde channels.
    post_link = (
        await db_session.execute(
            select(MattermostPostLink).where(MattermostPostLink.post_id == post["id"])
        )
    ).scalar_one_or_none()
    assert post_link is None


async def test_dm_post_with_unknown_code_does_not_create_mapping(db_session):
    """Een DM met een code die niet in de DB staat resulteert in een
    nette reply en géén mapping."""
    from unittest.mock import AsyncMock, patch

    from bouwmeester.repositories.mattermost_user import MattermostUserRepository

    mm_uid = _id()
    post = {
        "id": _id(),
        "channel_id": _id(),
        "user_id": mm_uid,
        "create_at": 1_700_000_000_000,
        "message": "BM-doesnotexist klopt dit?",
    }

    safe_reply = AsyncMock(return_value=None)
    ingest = MattermostIngestService(db_session)
    with (
        _patch_dm_session(db_session),
        patch(
            "bouwmeester.services.mattermost_link_poller."
            "MattermostLinkPoller._safe_reply",
            new=safe_reply,
        ),
    ):
        await ingest.ingest_post(post, channel_type="D")

    repo = MattermostUserRepository(db_session)
    assert await repo.get_by_mattermost_user_id(mm_uid) is None
    safe_reply.assert_called_once()
    _, _, message = safe_reply.call_args.args
    assert "code herken ik niet" in message


async def test_dm_post_from_bot_itself_is_ignored(db_session):
    """Bot-eigen DM-posts (anti feedback-loop) worden vroeg geskipt — dus
    we moeten geen MattermostLinkPoller instantiëren."""
    from unittest.mock import patch

    bot_id = _id()
    ingest = MattermostIngestService(db_session, bot_user_id=bot_id)
    post = {
        "id": _id(),
        "channel_id": _id(),
        "user_id": bot_id,
        "create_at": 1_700_000_000_000,
        "message": "BM-something",
    }

    with patch(
        "bouwmeester.services.mattermost_ingest_service.handle_dm_post"
    ) as handle_dm:
        await ingest.ingest_post(post, channel_type="D")
    handle_dm.assert_not_called()


async def test_group_dm_is_ignored(db_session):
    """Group-DMs (channel_type='G') vallen niet onder de link-flow én niet
    onder de channel-link-flow."""
    from unittest.mock import patch

    post = {
        "id": _id(),
        "channel_id": _id(),
        "user_id": _id(),
        "create_at": 1_700_000_000_000,
        "message": "BM-someothercode",
    }

    ingest = MattermostIngestService(db_session)
    with patch(
        "bouwmeester.services.mattermost_ingest_service.handle_dm_post"
    ) as handle_dm:
        await ingest.ingest_post(post, channel_type="G")
    handle_dm.assert_not_called()


async def test_link_poller_integrity_error_keeps_session_usable(
    db_session, create_person
):
    """Bij een race waar dezelfde Mattermost-user al elders is gekoppeld,
    moet de poller de IntegrityError netjes binnen een savepoint
    afvangen zodat de session bruikbaar blijft voor een volgende query.
    Voor de fix zat de session na de IntegrityError in aborted-state."""
    from unittest.mock import AsyncMock, patch

    from bouwmeester.repositories.mattermost_user import MattermostUserRepository
    from bouwmeester.services.mattermost_link_poller import MattermostLinkPoller
    from bouwmeester.services.mattermost_service import MattermostService

    p1 = await create_person(naam="P1", prefix="p1")
    p2 = await create_person(naam="P2", prefix="p2")

    repo = MattermostUserRepository(db_session)
    code = await repo.create_link_code(p2.id)

    # P1 is al gekoppeld aan een Mattermost-user; we proberen nu P2 te
    # koppelen aan dezelfde MM-user → IntegrityError op unique mm_user_id.
    shared_mm_uid = _id()
    await repo.create_mapping(
        person_id=p1.id,
        mattermost_user_id=shared_mm_uid,
        mattermost_username="p1",
    )

    post = {
        "id": _id(),
        "channel_id": _id(),
        "user_id": shared_mm_uid,
        "create_at": 1_700_000_000_000,
        "message": f"hier is mijn code: {code.code}",
    }

    mm_service = MattermostService(db_session)
    poller = MattermostLinkPoller(db_session, mm_service=mm_service)
    with (
        patch.object(poller, "_safe_reply", new=AsyncMock(return_value=None)),
        patch.object(
            mm_service, "get_username", new=AsyncMock(return_value="duplicate")
        ),
    ):
        await poller.process_posts([post])

    # Session moet nog werken na de afgevangen IntegrityError.
    refreshed = await db_session.get(type(p1), p1.id)
    assert refreshed is not None
    # P1's mapping bestaat nog steeds, P2 heeft géén nieuwe mapping.
    assert (await repo.get_by_mattermost_user_id(shared_mm_uid)).person_id == p1.id


async def test_dm_handling_failure_does_not_break_outer_session(
    db_session, create_person
):
    """Een onverwachte exception in ``handle_dm_post`` mag de
    outer-session van de WS-loop niet kapot maken. We forceren een fout
    en checken dat de outer-session daarna nog gewone queries kan
    uitvoeren."""
    from unittest.mock import AsyncMock, patch

    person = await create_person(naam="Outer", prefix="outer")
    post = {
        "id": _id(),
        "channel_id": _id(),
        "user_id": _id(),
        "create_at": 1_700_000_000_000,
        "message": "BM-irrelevantcode",
    }

    ingest = MattermostIngestService(db_session)
    with (
        _patch_dm_session(db_session),
        patch(
            "bouwmeester.services.mattermost_link_poller."
            "MattermostLinkPoller.process_posts",
            new=AsyncMock(side_effect=RuntimeError("simulated crash")),
        ),
    ):
        # Mag NIET propageren — handle_dm_post vangt het op.
        await ingest.ingest_post(post, channel_type="D")

    # Outer-session is nog bruikbaar voor een vervolgquery.
    refreshed = await db_session.get(type(person), person.id)
    assert refreshed is not None
    assert refreshed.naam == "Outer"


async def test_channel_post_without_channel_type_unaffected(db_session, sample_lead):
    """Bestaande aanroepen zonder ``channel_type`` blijven door de
    channel-link-flow lopen — backward compat met bestaande tests."""
    cid = _id()
    db_session.add(
        MattermostChannelLink(
            channel_id=cid,
            channel_name="proj",
            channel_display_name="Project",
            scope_type=SCOPE_LEAD,
            scope_id=sample_lead.id,
            auto_note_enabled=True,
        )
    )
    await db_session.flush()

    ingest = MattermostIngestService(db_session)
    post = {
        "id": _id(),
        "channel_id": cid,
        "user_id": _id(),
        "create_at": 1_700_000_000_000,
        "message": "Een gewone update over het project.",
    }
    # Default channel_type=None — moet door channel-link-flow vallen.
    await ingest.ingest_post(post)

    activity = (
        await db_session.execute(
            select(LeadActivity).where(LeadActivity.lead_id == sample_lead.id)
        )
    ).scalar_one()
    assert activity.activity_type == "note"
