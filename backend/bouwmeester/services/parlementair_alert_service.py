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
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.parlementair_item import ParlementairItem
from bouwmeester.repositories.parlementair_abonnement import (
    ParlementairAbonnementRepository,
)
from bouwmeester.services.kamerstuk_soort import (
    CAT_NIEUWS,
    CAT_OVERIG,
    CATEGORIE_PRESENTATIE,
)
from bouwmeester.services.mattermost_service import MattermostService
from bouwmeester.services.mattermost_utils import escape_mattermost_md as _escape_md

logger = logging.getLogger(__name__)

# De kleur van de streep links komt uit de categorie (zie
# `kamerstuk_soort.CATEGORIE_PRESENTATIE`), zodat een kamervraag er anders
# uitziet dan een agenda. Een lage relevantie dempt hem naar grijs: bij een
# breed vangnet (recall boven precisie) wordt niets weggegooid, maar niet
# alles hoeft evenveel aandacht te trekken.
KLEUR_LAAG = "#CBD5E1"

DREMPEL_HOOG = 70
DREMPEL_MIDDEN = 40

_NL_MAANDEN = (
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
)

# De reactions die de bot zelf plaatst als affordance. De websocket-laag
# leest ze terug; eigen reactions triggeren daar geen actie.
REACTIE_NIET_RELEVANT = "x"
REACTIE_OPVOLGEN = "eyes"


def _vinkje_voor(item: ParlementairItem):
    """Welke kanaalinstelling bepaalt of dit stuk gepost mag worden.

    Op de categorie en niet op `item.type`, omdat de categorie al in
    `extra_data` staat op het moment dat een stuk wordt gepost, en omdat
    dat precies het veld is dat de rest van de presentatie stuurt.
    """
    categorie = (item.extra_data or {}).get("categorie")
    if categorie == CAT_NIEUWS:
        return MattermostChannelLink.nieuws_alerts_enabled
    return MattermostChannelLink.parlementaire_alerts_enabled


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

        # Een abonnement kan soorten uitzetten die het niet in Mattermost
        # wil zien — procedurevergaderingen zijn nuttig maar talrijk. Het
        # stuk is dan wél geïmporteerd en in de webapp zichtbaar; alleen
        # het bericht blijft uit. Zo verliest een filter nooit dekking.
        extra = item.extra_data or {}
        categorie = extra.get("categorie") or CAT_OVERIG
        score = _relevantie(extra)
        abonnementen = [
            a
            for a in abonnementen
            if categorie not in (a.uitgezette_categorieen or [])
            # Onder de drempel geen bericht. Het stuk is wél geïmporteerd
            # en staat in de webapp: een drempel hoort ruis te schelen,
            # geen dekking. Een meting over zeven stukken gaf een scherpe
            # scheiding: alles met inhoud op 15 of hoger, en alleen een
            # procedureel verslag zonder inhoud op 0. De standaard staat
            # daarom laag genoeg om een stuk waarin de term als gewoon
            # woord valt nog door te laten; of dat ruis is, is een oordeel
            # van de lezer en niet van het model.
            and score >= (a.minimum_relevantie or 0)
        ]
        if not abonnementen:
            logger.info(
                "Kamerstuk %s (%s, score %d) niet gepost: uitgezet of onder "
                "de drempel van alle abonnees",
                item.zaak_nummer,
                categorie,
                score,
            )
            return 0

        # Welk vinkje dit stuk nodig heeft. Nieuws en kamerstukken zijn
        # los aan te zetten: een kanaal dat de Kamer volgt heeft niet
        # vanzelf om de vakpers gevraagd, en andersom.
        vinkje = _vinkje_voor(item)

        # Eén kanaal kan via meerdere termen meekijken; post er één keer.
        kanalen: dict[str, MattermostChannelLink] = {}
        for abonnement in abonnementen:
            stmt = select(MattermostChannelLink).where(
                MattermostChannelLink.scope_type == abonnement.scope_type,
                MattermostChannelLink.scope_id == abonnement.scope_id,
                MattermostChannelLink.disabled_at.is_(None),
                # Per kanaal aan te zetten, net als auto-notes en
                # lead-suggesties. Een kanaal dat voor leads is gekoppeld
                # hoort niet ongevraagd elk kamerstuk te krijgen.
                vinkje.is_(True),
            )
            for link in (await self.session.execute(stmt)).scalars().all():
                kanalen.setdefault(link.channel_id, link)

        if not kanalen:
            logger.info(
                "Stuk %s heeft abonnees maar geen kanaal met dit soort alerts aan",
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
        """Bouw het bericht: strak, met bron, soort en herkomst.

        Het soort staat vooraan omdat het het eerste is wat iemand wil
        weten. Een agenda van een procedurevergadering die over twee dagen
        is, vraagt iets anders van de lezer dan een besluitenlijst van een
        vergadering die geweest is, en een position paper komt van buiten
        de Kamer en is geen beleid.
        """
        extra = item.extra_data or {}
        score = _relevantie(extra)
        categorie = extra.get("categorie") or CAT_OVERIG
        presentatie = CATEGORIE_PRESENTATIE.get(
            categorie, CATEGORIE_PRESENTATIE[CAT_OVERIG]
        )

        # De categorie geeft de kleur; een lage relevantie dempt hem naar
        # grijs. Zo blijft een zijdelingse treffer zichtbaar zonder de
        # aandacht te trekken die een kerntreffer verdient.
        kleur = presentatie["kleur"] if score >= DREMPEL_MIDDEN else KLEUR_LAAG

        kop = self._kopregel(extra, presentatie)

        # Escapen, ook al komt dit van ons eigen taalmodel: het model vat
        # een kamerstuk van derden samen, dus een stuk dat het overhaalt
        # om `@channel` of een link in de samenvatting te zetten krijgt
        # dat anders ongefilterd in het kanaal.
        samenvatting = _escape_md((item.llm_samenvatting or "").strip())
        if not samenvatting:
            samenvatting = _escape_md((item.onderwerp or "")[:300])

        tekst_delen = [samenvatting]

        actie = (extra.get("actie") or "").strip()
        if actie:
            tekst_delen.append(f":arrow_right: {_escape_md(actie)}")

        acties = []
        if item.document_url:
            acties.append(f"[Openen op tkconv]({item.document_url})")
        raw_url = extra.get("raw_url")
        if raw_url:
            acties.append(f"[Brondocument]({raw_url})")
        if acties:
            tekst_delen.append(" · ".join(acties))

        fields = [
            {
                "short": False,
                "title": "Gevonden op",
                "value": ", ".join(_escape_md(t) for t in termen),
            }
        ]

        titel = f"{presentatie['emoji']} {_escape_md(item.titel)}"
        attachment: dict = {
            "fallback": f"{presentatie['label']}: {_escape_md(item.titel)}",
            "color": kleur,
            "pretext": kop,
            "title": titel,
            "title_link": item.document_url or "",
            "text": "\n\n".join(tekst_delen),
            "fields": fields,
            "footer": self._voettekst(item, extra),
        }

        return "", {"attachments": [attachment]}

    @staticmethod
    def _kopregel(extra: dict, presentatie: dict) -> str:
        """De regel boven de titel: wat voor stuk, en wat dat betekent.

        Dit is waar het onderscheid zichtbaar wordt. Een vergadering die
        nog komt krijgt er hoeveel dagen bij, want dat is precies het
        verschil tussen "je kunt hier nog iets mee" en "dit is gebeurd".

        Het label is het `Soort` uit de TK-API en niet onze categorie:
        "POSITION PAPER" zegt wat het stuk is, "EXTERN" zegt alleen in
        welk hokje wij het hebben gestopt. De categorie stuurt wel het
        icoon, de kleur en de instructie aan het taalmodel, en springt in
        als de API geen soort kent.
        """
        label = (extra.get("soort") or presentatie["label"]).upper()
        delen = [f"**{label}**"]

        # Een position paper of burgerbrief komt van buiten de Kamer, en
        # dat is precies wat je bij zo'n stuk wilt weten: het is een
        # standpunt van een belanghebbende, geen beleid. Het soort alleen
        # zegt dat niet.
        if presentatie.get("herkomst"):
            delen.append(presentatie["herkomst"])

        termijn = _als_datum(extra.get("termijn"))
        if termijn:
            dagen = (termijn - date.today()).days
            if dagen < 0:
                delen.append(f"termijn verstreken ({_nl_datum(termijn)})")
            elif dagen == 0:
                delen.append("termijn vandaag")
            else:
                delen.append(f"termijn {_nl_datum(termijn)} (over {dagen} dagen)")

        vergadering = _als_datum(extra.get("activiteit_datum"))
        if vergadering:
            dagen = (vergadering - date.today()).days
            if dagen > 1:
                delen.append(f"{_nl_datum(vergadering)} (over {dagen} dagen)")
            elif dagen == 1:
                delen.append(f"{_nl_datum(vergadering)} (morgen)")
            elif dagen == 0:
                delen.append(f"{_nl_datum(vergadering)} (vandaag)")
            else:
                delen.append(_nl_datum(vergadering))

        bijlage_bij = extra.get("bijlage_bij_nummer")
        if bijlage_bij:
            onderwerp = (extra.get("bijlage_bij_onderwerp") or "").strip()
            if onderwerp:
                delen.append(f"bij _{_escape_md(onderwerp[:60])}_")
            else:
                delen.append(f"bij {bijlage_bij}")

        return " · ".join(delen)

    @staticmethod
    def _voettekst(item: ParlementairItem, extra: dict) -> str:
        soort = extra.get("soort")
        commissie = extra.get("commissie")
        datum = _nl_datum(item.datum) if item.datum else ""
        delen = [x for x in [soort, commissie, datum] if x]
        delen.append("via tkconv (berthub.eu)")
        return " · ".join(delen)

    async def post_inhaalslag(
        self, abonnementen: list, items: list[ParlementairItem]
    ) -> int:
        """Meld in één bericht wat nieuwe zoektermen terugvonden.

        Eén bericht voor álle termen die tegelijk worden aangezet, niet
        één per term. Twee termen vinden vaak dezelfde stukken: in
        productie gaven "van wet naar digitale werking" en "regelrecht"
        samen twee berichten met vier regels over drie unieke stukken,
        met de startnotitie NLDD er twee keer in. Bij vijf termen zouden
        dat vijf berichten zijn.

        De losse alerts ontdubbelen al op documentnummer; dit doet
        hetzelfde.
        """
        if not await self.mattermost.is_enabled() or not items:
            return 0
        if not abonnementen:
            return 0

        # Dezelfde drempel als bij een losse alert. Zonder dit staat de
        # inhaalslag los van elke instelling: in productie leverde dat één
        # bericht met 47 stukken op, waarvan 46 via een term die vooral de
        # metafoor ving. De stukken blijven geïmporteerd en in de webapp
        # zichtbaar; alleen het bericht wordt korter.
        drempel = min((a.minimum_relevantie or 0) for a in abonnementen)
        items = [i for i in items if _relevantie(i.extra_data or {}) >= drempel]
        if not items:
            logger.info(
                "Inhaalslag voor %s: niets boven de drempel van %d",
                ", ".join(repr(a.term) for a in abonnementen),
                drempel,
            )
            return 0

        # Alle termen delen dezelfde scope (de aanroeper groepeert
        # daarop), dus de kanalen zijn voor allemaal gelijk.
        eerste = abonnementen[0]
        stmt = select(MattermostChannelLink).where(
            MattermostChannelLink.scope_type == eerste.scope_type,
            MattermostChannelLink.scope_id == eerste.scope_id,
            MattermostChannelLink.disabled_at.is_(None),
            MattermostChannelLink.parlementaire_alerts_enabled.is_(True),
        )
        kanalen = list((await self.session.execute(stmt)).scalars().all())
        if not kanalen:
            return 0

        text, props = self.format_inhaalslag(abonnementen, items)
        gepost = 0
        for link in kanalen:
            if await self.mattermost.send_channel_message(link.channel_id, text, props):
                gepost += 1
        return gepost

    def format_inhaalslag(
        self, abonnementen: list, items: list[ParlementairItem]
    ) -> tuple[str, dict]:
        """Eén lijst met wat de nieuwe termen in de feed terugvonden."""
        regels = []
        for item in sorted(items, key=lambda i: i.datum or date.min, reverse=True):
            extra = item.extra_data or {}
            categorie = extra.get("categorie") or CAT_OVERIG
            presentatie = CATEGORIE_PRESENTATIE.get(
                categorie, CATEGORIE_PRESENTATIE[CAT_OVERIG]
            )
            datum = _nl_datum(item.datum) if item.datum else ""
            titel = _escape_md(item.titel[:70])
            link = item.document_url
            regel = f"{presentatie['emoji']} "
            regel += f"[{titel}]({link})" if link else titel
            if datum:
                regel += f" · {datum}"
            regels.append(regel)

        termen = ", ".join(_escape_md(a.term) for a in abonnementen)
        kop = "Nieuwe zoekterm" if len(abonnementen) == 1 else "Nieuwe zoektermen"
        attachment = {
            "fallback": f"{len(items)} eerdere stukken gevonden voor {termen}",
            "color": "#64748B",
            "pretext": f":mag: **{kop}** · {termen}",
            "title": f"{len(items)} stukken uit de afgelopen week gevonden",
            "text": "\n".join(regels),
            "footer": (
                "Eenmalige inhaalslag bij het aanzetten. Hierna verschijnen "
                "alleen nieuwe stukken."
            ),
        }
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
    # `bool` is een `int` in Python, en True zou dan score 1 worden — onder
    # elke drempel, dus stilte. En `int(float("nan"))` gooit een ValueError;
    # een taalmodel dat NaN in zijn JSON zet is niet exotisch.
    if isinstance(waarde, bool) or not isinstance(waarde, int | float):
        return DREMPEL_MIDDEN
    try:
        return max(0, min(100, int(waarde)))
    except (ValueError, OverflowError):
        return DREMPEL_MIDDEN


def _als_datum(waarde) -> date | None:
    """Lees een datum uit `extra_data`, waar hij als ISO-string staat."""
    if waarde is None:
        return None
    if isinstance(waarde, date) and not isinstance(waarde, datetime):
        return waarde
    if isinstance(waarde, datetime):
        return waarde.date()
    try:
        return date.fromisoformat(str(waarde)[:10])
    except ValueError:
        return None


def _nl_datum(waarde) -> str:
    """`24 september` — zonder jaar als het dit jaar is.

    Niet `strftime("%-d %B")`: dat volgt de locale van de container, en die
    staat in productie op C. Dan krijg je Engelse maandnamen in een
    Nederlands bericht.
    """
    d = _als_datum(waarde)
    if d is None:
        return ""
    maand = _NL_MAANDEN[d.month - 1]
    if d.year == date.today().year:
        return f"{d.day} {maand}"
    return f"{d.day} {maand} {d.year}"
