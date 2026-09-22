"""Post een gevonden kamerstuk in de kanalen van het abonnerende initiatief.

Vorm van het bericht: kort, met de bron erbij en een handeling die met één
klik kan. Drie regels samenvatting is de bovengrens — een alert die je moet
lezen zoals je een kamerstuk leest, is geen alert.

Waarom emoji-reactions en geen knoppen: Mattermost stuurt voor
message-attachment-button-clicks geen POST naar onze endpoint, en de
"Taak afronden"-knop die dat wel probeerde deed daarom nooit iets (zie
`MattermostService.format_notification`). Suggested-leads lossen dat al op
met reactions over de bestaande websocket; deze alerts volgen datzelfde
pad.
"""

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.parlementair_item import ParlementairItem
from bouwmeester.repositories.parlementair_abonnement import (
    ParlementairAbonnementRepository,
)
from bouwmeester.services.mattermost_service import MattermostService
from bouwmeester.services.mattermost_utils import escape_mattermost_md as _escape_md

logger = logging.getLogger(__name__)

# Kleur van de streep links van het bericht, naar relevantie. Een hoge
# score krijgt de volle kaart, een lage blijft grijs: bij een breed
# vangnet (recall boven precisie) wordt niets weggegooid, maar niet alles
# hoeft evenveel aandacht te trekken.
KLEUR_HOOG = "#1E3A8A"
KLEUR_MIDDEN = "#64748B"
KLEUR_LAAG = "#CBD5E1"

DREMPEL_HOOG = 70
DREMPEL_MIDDEN = 40

# De reactions die de bot zelf plaatst als affordance. De websocket-laag
# leest ze terug; eigen reactions triggeren daar geen actie.
REACTIE_NIET_RELEVANT = "x"
REACTIE_OPVOLGEN = "eyes"


class ParlementairAlertService:
    """Zet een geïmporteerd kamerstuk om in een bericht per kanaal."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.abonnement_repo = ParlementairAbonnementRepository(session)
        self.mattermost = MattermostService(session)

    async def post_alert(self, item: ParlementairItem) -> int:
        """Post het item in elk kanaal dat via een abonnement meekijkt.

        Geeft terug in hoeveel kanalen is gepost. Nul is een geldige
        uitkomst: een initiatief hoeft geen kanaal te hebben, en dan staat
        de treffer alleen in de webapp.
        """
        if not await self.mattermost.is_enabled():
            return 0

        abonnementen = await self.abonnement_repo.list_abonnementen_voor_item(item.id)
        if not abonnementen:
            return 0

        # Eén kanaal kan via meerdere termen meekijken; post er één keer.
        kanalen: dict[str, MattermostChannelLink] = {}
        for abonnement in abonnementen:
            stmt = select(MattermostChannelLink).where(
                MattermostChannelLink.scope_type == abonnement.scope_type,
                MattermostChannelLink.scope_id == abonnement.scope_id,
                MattermostChannelLink.disabled_at.is_(None),
            )
            for link in (await self.session.execute(stmt)).scalars().all():
                kanalen.setdefault(link.channel_id, link)

        if not kanalen:
            logger.info(
                "Kamerstuk %s heeft abonnees maar geen gekoppeld kanaal",
                item.zaak_nummer,
            )
            return 0

        termen = [a.term for a in abonnementen]
        text, props = self.format_alert(item, termen)

        gepost = 0
        for channel_id in kanalen:
            if await self.mattermost.send_channel_message(channel_id, text, props):
                gepost += 1
        return gepost

    def format_alert(
        self, item: ParlementairItem, termen: list[str]
    ) -> tuple[str, dict]:
        """Bouw het bericht: strak, met bron en herkomst."""
        extra = item.extra_data or {}
        score = _relevantie(extra)

        if score >= DREMPEL_HOOG:
            kleur = KLEUR_HOOG
        elif score >= DREMPEL_MIDDEN:
            kleur = KLEUR_MIDDEN
        else:
            kleur = KLEUR_LAAG

        soort = extra.get("soort") or "Kamerstuk"
        commissie = extra.get("commissie")
        datum = item.datum.strftime("%-d %B %Y") if item.datum else ""
        herkomst = " · ".join(x for x in [soort, commissie, datum] if x)

        samenvatting = (item.llm_samenvatting or "").strip()
        if not samenvatting:
            samenvatting = _escape_md((item.onderwerp or "")[:300])

        fields = [
            {
                "short": False,
                "title": "Gevonden op",
                "value": ", ".join(_escape_md(t) for t in termen),
            }
        ]

        raw_url = extra.get("raw_url")
        attachment: dict = {
            "fallback": _escape_md(item.titel),
            "color": kleur,
            "title": _escape_md(item.titel),
            "title_link": item.document_url or "",
            "text": samenvatting,
            "fields": fields,
            "footer": (
                f"{herkomst} · via tkconv (berthub.eu)"
                if herkomst
                else "via tkconv (berthub.eu)"
            ),
        }

        # Links in plaats van knoppen: een attachment-button levert geen
        # callback op, een link werkt altijd.
        acties = []
        if item.document_url:
            acties.append(f"[Openen op tkconv]({item.document_url})")
        if raw_url:
            acties.append(f"[Brondocument]({raw_url})")
        if acties:
            attachment["text"] = f"{samenvatting}\n\n{' · '.join(acties)}"

        return "", {"attachments": [attachment]}

    async def markeer_niet_relevant(self, item_id: UUID) -> None:
        """Tel een wegklik bij elke term die dit stuk aandroeg.

        Deactiveert nooit automatisch: bij recall boven precisie is
        wegklikken normaal gedrag, en een term die zichzelf uitzet levert
        stil dekkingsverlies op. Het getal is een signaal voor de
        gebruiker, niet een schakelaar.
        """
        await self.abonnement_repo.markeer_weggeklikt(item_id)


def _relevantie(extra: dict) -> int:
    """Lees de relevantiescore uit extra_data, met een veilige default.

    Zonder score behandelen we het stuk als middenmoot: zichtbaar, niet
    schreeuwend. Een ontbrekende score mag nooit stilte betekenen.
    """
    waarde = extra.get("relevantie_score")
    if isinstance(waarde, int | float):
        return max(0, min(100, int(waarde)))
    return DREMPEL_MIDDEN
