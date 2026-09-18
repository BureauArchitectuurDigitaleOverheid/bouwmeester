"""Tests voor @bouwmeester-vermeldingen in Mattermost-kanalen.

Een mention is een expliciet menselijk signaal en krijgt daarom twee
uitzonderingen op het normale zwijgzame gedrag:

1. De ruis-classificatie wordt overgeslagen — iemand zegt al dat dit
   relevant is, dus de LLM hoeft dat niet meer te raden.
2. De bot bevestigt kort in de thread wat hij ermee gedaan heeft, ook in een
   ongekoppeld kanaal. Zonder die bevestiging is "niets zien gebeuren" niet
   te onderscheiden van "de bot is stuk", en dat is precies hoe een prima
   werkende bot voor dood werd versleten.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.lead import Lead
from bouwmeester.models.lead_activity import LeadActivity
from bouwmeester.models.mattermost_channel_link import (
    SCOPE_LEAD,
    MattermostChannelLink,
)
from bouwmeester.services import mattermost_ingest_service as ingest_module
from bouwmeester.services.mattermost_ingest_service import (
    MattermostIngestService,
    message_mentions_bot,
)

BOT = "bouwmeester"


def _id() -> str:
    return uuid.uuid4().hex[:26]


class FakeMattermostService:
    """Vangt replies op in plaats van ze naar Mattermost te sturen."""

    replies: list[tuple[str, str, str]] = []

    def __init__(self, session):
        self.session = session

    async def is_enabled(self) -> bool:
        return True

    async def reply_to_post(self, channel_id, root_id, message, *, props=None):
        FakeMattermostService.replies.append((channel_id, root_id, message))
        return {"id": _id()}

    async def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _fake_mattermost(monkeypatch):
    """Vervang MattermostService overal waar de ingest 'm lazy importeert."""
    FakeMattermostService.replies = []
    monkeypatch.setattr(
        "bouwmeester.services.mattermost_service.MattermostService",
        FakeMattermostService,
    )
    # Cooldown-cache leeg per test, anders lekt state tussen tests.
    ingest_module._unlinked_hint_sent_at.clear()
    yield
    ingest_module._unlinked_hint_sent_at.clear()


@pytest.fixture
async def sample_lead(db_session):
    init = Initiatief(id=uuid.uuid4(), naam="Test initiatief")
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
    return lead


# ---------------------------------------------------------------------------
# Mention-herkenning
# ---------------------------------------------------------------------------


class TestMentionDetection:
    def test_herkent_directe_mention(self):
        assert message_mentions_bot("Werkt @bouwmeester niet meer?", BOT)

    def test_is_hoofdletter_ongevoelig(self):
        assert message_mentions_bot("Hoi @Bouwmeester", BOT)

    def test_negeert_los_woord_zonder_at(self):
        # Anders zou elk gesprek *over* het product de bot laten reageren.
        assert not message_mentions_bot("bouwmeester pakt niks meer op", BOT)

    def test_negeert_channel_en_here(self):
        assert not message_mentions_bot("@channel let op", BOT)
        assert not message_mentions_bot("@here iemand?", BOT)

    def test_negeert_andere_username_met_prefix(self):
        assert not message_mentions_bot("@bouwmeester-test hallo", BOT)

    def test_negeert_email_achtige_string(self):
        assert not message_mentions_bot("mail naar foo@bouwmeester.nl", BOT)

    def test_zonder_bekende_botnaam_nooit_true(self):
        # Bij een onbekende bot-username doen we niets bijzonders.
        assert not message_mentions_bot("@bouwmeester hoi", None)


# ---------------------------------------------------------------------------
# Gekoppeld kanaal
# ---------------------------------------------------------------------------


async def _link_lead_channel(db_session, lead, cid, *, auto_note=True):
    db_session.add(
        MattermostChannelLink(
            channel_id=cid,
            channel_name="proj",
            channel_display_name="Project",
            scope_type=SCOPE_LEAD,
            scope_id=lead.id,
            auto_note_enabled=auto_note,
            suggest_leads_enabled=False,
        )
    )
    await db_session.flush()


async def test_mention_slaat_ruisfilter_over(db_session, sample_lead, monkeypatch):
    """Een kort bericht mét mention moet alsnog een notitie worden.

    Precies het geval uit de praktijk: "Werkt @Bouwmeester niet meer?" werd
    als ruis geklasseerd en stil weggegooid.
    """
    cid = _id()
    await _link_lead_channel(db_session, sample_lead, cid)

    # Forceer dat de ruis-classificatie 'ja, ruis' zou zeggen.
    async def always_noise(self, message):
        return True

    monkeypatch.setattr(MattermostIngestService, "_is_noise", always_noise)

    ingest = MattermostIngestService(db_session, bot_username=BOT)
    await ingest.ingest_post(
        {
            "id": _id(),
            "channel_id": cid,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": "@bouwmeester dit moet je vastleggen",
        }
    )

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


async def test_zonder_mention_blijft_ruis_ruis(db_session, sample_lead, monkeypatch):
    """De ruisfilter moet z'n werk blijven doen voor gewone berichten."""
    cid = _id()
    await _link_lead_channel(db_session, sample_lead, cid)

    async def always_noise(self, message):
        return True

    monkeypatch.setattr(MattermostIngestService, "_is_noise", always_noise)

    ingest = MattermostIngestService(db_session, bot_username=BOT)
    await ingest.ingest_post(
        {
            "id": _id(),
            "channel_id": cid,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": "ok top, thanks",
        }
    )

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
    assert FakeMattermostService.replies == []


async def test_mention_bevestigt_in_thread(db_session, sample_lead, monkeypatch):
    """Na een mention hoort er zichtbaar iets terug te komen."""
    cid = _id()
    await _link_lead_channel(db_session, sample_lead, cid)

    async def never_noise(self, message):
        return False

    monkeypatch.setattr(MattermostIngestService, "_is_noise", never_noise)

    ingest = MattermostIngestService(db_session, bot_username=BOT)
    await ingest.ingest_post(
        {
            "id": _id(),
            "channel_id": cid,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": "@bouwmeester leg dit even vast",
        }
    )

    assert len(FakeMattermostService.replies) == 1
    assert "Genoteerd" in FakeMattermostService.replies[0][2]


async def test_mention_legt_uit_dat_notities_uitstaan(db_session, sample_lead):
    """Gekoppeld maar modus uit: dat moet je te horen krijgen."""
    cid = _id()
    await _link_lead_channel(db_session, sample_lead, cid, auto_note=False)

    ingest = MattermostIngestService(db_session, bot_username=BOT)
    await ingest.ingest_post(
        {
            "id": _id(),
            "channel_id": cid,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": "@bouwmeester en nu?",
        }
    )

    assert len(FakeMattermostService.replies) == 1
    assert "staan uit" in FakeMattermostService.replies[0][2]


# ---------------------------------------------------------------------------
# Ongekoppeld kanaal
# ---------------------------------------------------------------------------


async def test_mention_in_ongekoppeld_kanaal_legt_uit(db_session):
    """Het scenario uit de screenshot: bot lijkt stuk, is het niet."""
    ingest = MattermostIngestService(db_session, bot_username=BOT)
    await ingest.ingest_post(
        {
            "id": _id(),
            "channel_id": _id(),
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": "Werkt @bouwmeester niet meer?",
        }
    )

    assert len(FakeMattermostService.replies) == 1
    reply = FakeMattermostService.replies[0][2]
    assert "lees in dit kanaal niet mee" in reply
    assert "/bouwmeester koppel" in reply


async def test_geen_mention_in_ongekoppeld_kanaal_blijft_stil(db_session):
    """Zonder mention zwijgt de bot in een ongekoppeld kanaal."""
    ingest = MattermostIngestService(db_session, bot_username=BOT)
    await ingest.ingest_post(
        {
            "id": _id(),
            "channel_id": _id(),
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": "Even iets heel anders bespreken.",
        }
    )
    assert FakeMattermostService.replies == []


async def test_uitleg_is_gerateremd_per_kanaal(db_session):
    """Herhaalde mentions in hetzelfde kanaal leveren één uitleg op."""
    cid = _id()
    ingest = MattermostIngestService(db_session, bot_username=BOT)
    for _ in range(3):
        await ingest.ingest_post(
            {
                "id": _id(),
                "channel_id": cid,
                "user_id": _id(),
                "create_at": 1_700_000_000_000,
                "message": "@bouwmeester?",
            }
        )
    assert len(FakeMattermostService.replies) == 1


async def test_ander_kanaal_krijgt_eigen_uitleg(db_session):
    """De rem geldt per kanaal, niet globaal."""
    ingest = MattermostIngestService(db_session, bot_username=BOT)
    for _ in range(2):
        await ingest.ingest_post(
            {
                "id": _id(),
                "channel_id": _id(),
                "user_id": _id(),
                "create_at": 1_700_000_000_000,
                "message": "@bouwmeester?",
            }
        )
    assert len(FakeMattermostService.replies) == 2


async def test_bot_reageert_niet_op_zichzelf(db_session):
    """Anti feedback-loop: de bot mag zijn eigen uitleg niet beantwoorden."""
    bot_id = _id()
    ingest = MattermostIngestService(db_session, bot_user_id=bot_id, bot_username=BOT)
    await ingest.ingest_post(
        {
            "id": _id(),
            "channel_id": _id(),
            "user_id": bot_id,
            "create_at": 1_700_000_000_000,
            "message": "@bouwmeester ik praat tegen mezelf",
        }
    )
    assert FakeMattermostService.replies == []


async def test_mislukte_uitleg_blokkeert_volgende_poging_niet(db_session, monkeypatch):
    """Een niet-geplaatste uitleg mag de rem niet een uur laten hangen.

    De claim wordt vóór het posten gezet; als het posten dan faalt zou het
    kanaal een uur stil blijven zonder dat er ooit iets verschenen is.
    """

    class FailingService(FakeMattermostService):
        async def reply_to_post(self, channel_id, root_id, message, *, props=None):
            return None  # reply_to_post swallowt HTTP-fouten en geeft None

    monkeypatch.setattr(
        "bouwmeester.services.mattermost_service.MattermostService",
        FailingService,
    )

    cid = _id()
    ingest = MattermostIngestService(db_session, bot_username=BOT)
    await ingest.ingest_post(
        {
            "id": _id(),
            "channel_id": cid,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": "@bouwmeester?",
        }
    )
    # Claim moet weer vrij zijn.
    assert cid not in ingest_module._unlinked_hint_sent_at

    # En een volgende poging mag het dus opnieuw proberen.
    monkeypatch.setattr(
        "bouwmeester.services.mattermost_service.MattermostService",
        FakeMattermostService,
    )
    await ingest.ingest_post(
        {
            "id": _id(),
            "channel_id": cid,
            "user_id": _id(),
            "create_at": 1_700_000_000_000,
            "message": "@bouwmeester?",
        }
    )
    assert len(FakeMattermostService.replies) == 1
