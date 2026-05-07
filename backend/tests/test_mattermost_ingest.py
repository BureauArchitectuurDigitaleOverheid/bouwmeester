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
