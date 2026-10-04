"""Set up a Mattermost channel for one debate.

Someone presses the start reaction under a convocatie. That creates a
channel with a header, a purpose and a pinned message listing the agenda.
No audio yet: this alone saves setting up a channel by hand and looking up
the documents.

The channel is made when the button is pressed, not on the day of the
debate. A convocatie arrives a median of 20.5 days ahead, so the documents
are there for weeks for whoever wants to prepare.
"""

from __future__ import annotations

import enum
import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.debat_sessie import DebatSessie
from bouwmeester.models.mattermost_channel_link import MattermostChannelLink
from bouwmeester.models.parlementair_item import ParlementairItem
from bouwmeester.services.mattermost_service import (
    CHANNEL_DISPLAY_NAME_MAX,
    CHANNEL_NAME_MAX,
    CHANNEL_PURPOSE_MAX,
    ChannelNameTakenError,
    MattermostPermissionError,
    MattermostService,
    MattermostUnavailableError,
)
from bouwmeester.services.mattermost_utils import (
    escape_mattermost_md,
    escape_mattermost_prose,
)
from bouwmeester.services.parlementair_alert_service import (
    _bruikbare_samenvatting,
    _kort,
)
from bouwmeester.services.tk_activiteit import (
    STATUS_CANCELLED,
    STATUS_MOVED,
    Activiteit,
    TkApiError,
    fetch_activiteit,
)

logger = logging.getLogger(__name__)

# The reaction the bot places under a convocatie as the start button.
REACTIE_UITLUISTEREN = "headphones"

# Only this soort gets the button. A "Convocatie inbreng" announces a
# deadline for written input, not a meeting anyone can listen to.
_SOORT_MET_KNOP = "Convocatie commissieactiviteit"

AMSTERDAM = ZoneInfo("Europe/Amsterdam")

# A claim without a channel that is older than this is a start that broke
# off halfway (a restart between the insert and the Mattermost call).
# Setting up a channel takes seconds, so minutes is already generous.
STALE_CLAIM = timedelta(minutes=5)

# Without an end time: how long after the start a meeting still counts as
# possibly running. The longest debates run into the night.
_ASSUMED_DURATION = timedelta(hours=12)

# Mattermost refuses a post above 16383 characters. Stay well below it:
# the limit counts the message as stored, and that is not always what we
# send.
_MESSAGE_MAX = 15000
_SUMMARY_MAX = 300

_TK_TIMEOUT = 15.0

_WEEKDAGEN = (
    "maandag",
    "dinsdag",
    "woensdag",
    "donderdag",
    "vrijdag",
    "zaterdag",
    "zondag",
)
_MAANDEN = (
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
_MAANDEN_KORT = (
    "jan",
    "feb",
    "mrt",
    "apr",
    "mei",
    "jun",
    "jul",
    "aug",
    "sep",
    "okt",
    "nov",
    "dec",
)

DEBAT_DIRECT_URL = "https://debatdirect.tweedekamer.nl"


def activiteit_url(nummer: str) -> str:
    return (
        "https://www.tweedekamer.nl/debat_en_vergadering/commissievergaderingen/"
        f"details?id={nummer}"
    )


def document_url(zaak_nummer: str | None, document_nummer: str) -> str:
    if zaak_nummer:
        return (
            "https://www.tweedekamer.nl/kamerstukken/detail"
            f"?id={zaak_nummer}&did={document_nummer}"
        )
    return f"https://www.tweedekamer.nl/kamerstukken/detail?did={document_nummer}"


def is_startable(extra: dict | None, today: date | None = None) -> bool:
    """Should this alert get the start button?

    Decided on what the import stored, without a call to the TK API: this
    runs for every alert that is posted. Pressing the button reads the
    current state, so a meeting that was cancelled afterwards is caught
    there.
    """
    extra = extra or {}
    if not extra.get("activiteit_id"):
        return False
    if extra.get("soort") != _SOORT_MET_KNOP:
        return False
    if extra.get("activiteit_status") in (STATUS_CANCELLED, STATUS_MOVED):
        return False
    raw = extra.get("activiteit_datum")
    if raw:
        try:
            datum = date.fromisoformat(str(raw)[:10])
        except ValueError:
            return True
        if datum < (today or datetime.now(AMSTERDAM).date()):
            return False
    return True


def _local(moment: datetime) -> datetime:
    return moment.astimezone(AMSTERDAM)


def format_moment(activiteit: Activiteit) -> str:
    """`dinsdag 6 oktober, 16:30 tot 21:30`, in Dutch local time.

    Not `strftime("%A %d %B")`: that follows the locale of the container,
    which is C in production.
    """
    if activiteit.aanvang is None:
        return ""
    start = _local(activiteit.aanvang)
    tekst = (
        f"{_WEEKDAGEN[start.weekday()]} {start.day} {_MAANDEN[start.month - 1]}, "
        f"{start:%H:%M}"
    )
    if activiteit.einde is not None:
        end = _local(activiteit.einde)
        # An end on another day is not an end time anyone reads as such.
        if end.date() == start.date() and end > start:
            tekst += f" tot {end:%H:%M}"
    return tekst


def _slug(tekst: str) -> str:
    plat = unicodedata.normalize("NFKD", tekst)
    plat = "".join(c for c in plat if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", plat).strip("-")


def channel_name(activiteit: Activiteit, *, with_nummer: bool = False) -> str:
    """The url name: `debat-digitaliserende-overheid-30-sep`.

    `with_nummer` adds the activiteit nummer, for when the plain name is
    taken. That happens: a debate with the same subject returns every
    year, and Mattermost keeps the name of an archived channel reserved.
    """
    prefix = "debat-"
    suffix = ""
    if activiteit.aanvang is not None:
        start = _local(activiteit.aanvang)
        suffix = f"-{start.day}-{_MAANDEN_KORT[start.month - 1]}"
    if with_nummer:
        suffix += f"-{_slug(activiteit.nummer or activiteit.id)}"

    room = CHANNEL_NAME_MAX - len(prefix) - len(suffix)
    slug = _slug(activiteit.onderwerp)
    if len(slug) > room:
        cut = slug[:room]
        # Back to a word boundary, unless that throws away half the name.
        hyphen = cut.rfind("-")
        if slug[room] != "-" and hyphen > room * 0.6:
            cut = cut[:hyphen]
        slug = cut.strip("-")
    if not slug:
        slug = _slug(activiteit.nummer or "") or "zonder-titel"
    # The slice guards the fallback: an id as slug can be longer than the
    # room that is left.
    return f"{prefix}{slug}{suffix}"[:CHANNEL_NAME_MAX].strip("-")


def channel_display_name(activiteit: Activiteit) -> str:
    suffix = ""
    if activiteit.aanvang is not None:
        start = _local(activiteit.aanvang)
        suffix = f" ({start.day} {_MAANDEN_KORT[start.month - 1]})"
    onderwerp = activiteit.onderwerp or activiteit.nummer or "Debat"
    return _kort(onderwerp, CHANNEL_DISPLAY_NAME_MAX - len(suffix)) + suffix


def channel_header(activiteit: Activiteit) -> str:
    """What stands above the channel: kind, time, and where to follow it.

    No room: the TK API has `Locatie` empty for every activiteit until the
    day itself.
    """
    delen = [f"**{escape_mattermost_md(activiteit.soort or 'Debat')}**"]
    moment = format_moment(activiteit)
    if moment:
        delen.append(moment)
    if activiteit.nummer:
        delen.append(f"[Agenda]({activiteit_url(activiteit.nummer)})")
    delen.append(f"[Debat Direct]({DEBAT_DIRECT_URL})")
    return " · ".join(delen)


def channel_purpose(activiteit: Activiteit) -> str:
    """What this debate was about, for whoever finds the channel later."""
    kop = activiteit.soort or "Debat"
    if activiteit.commissie:
        kop += f" {activiteit.commissie}"
    return _kort(f"{kop}: {activiteit.onderwerp}", CHANNEL_PURPOSE_MAX)


def _agenda_lines(
    activiteit: Activiteit, samenvattingen: dict[str, str], limit: int | None
) -> list[str]:
    regels: list[str] = []
    punten = activiteit.agendapunten
    shown = punten if limit is None else punten[:limit]
    for index, punt in enumerate(shown, start=1):
        titel = escape_mattermost_md(_kort(punt.onderwerp or "Agendapunt", 200))
        if not punt.documenten:
            regels.append(f"{index}. {titel}")
            continue
        eerste = punt.documenten[0]
        regel = f"{index}. [{titel}]({document_url(punt.zaak_nummer, eerste.nummer)})"
        if eerste.soort:
            regel += f" · {escape_mattermost_prose(eerste.soort)}"
        meer = len(punt.documenten) - 1
        if meer == 1:
            regel += " (+1 stuk)"
        elif meer > 1:
            regel += f" (+{meer} stukken)"
        regels.append(regel)
        samenvatting = next(
            (
                samenvattingen[doc.nummer]
                for doc in punt.documenten
                if samenvattingen.get(doc.nummer)
            ),
            "",
        )
        if samenvatting:
            # One line: a line break would end the list item and start a
            # paragraph outside the numbering.
            regels.append(
                "    > "
                + escape_mattermost_prose(
                    _kort(" ".join(samenvatting.split()), _SUMMARY_MAX)
                )
            )
    rest = len(punten) - len(shown)
    if rest > 0:
        regels.append("")
        regels.append(
            f"En nog {rest} agendapunt{'en' if rest != 1 else ''}; "
            "zie de agenda bovenaan dit kanaal."
        )
    return regels


def stukken_message(
    activiteit: Activiteit,
    samenvattingen: dict[str, str] | None = None,
    *,
    now: datetime | None = None,
) -> str:
    """The pinned message: what is on the agenda, with links.

    A summary is added where Bouwmeester already has one for that document
    (it came in as an alert earlier). Nothing is summarised here.
    """
    samenvattingen = samenvattingen or {}
    kop = [f"#### Geagendeerde stukken: {escape_mattermost_md(activiteit.onderwerp)}"]
    moment = format_moment(activiteit)
    meta = [m for m in (activiteit.soort, moment, activiteit.commissie) if m]
    if meta:
        kop.append(" · ".join(escape_mattermost_prose(m) for m in meta))
    if activiteit.bewindspersonen:
        namen = ", ".join(
            escape_mattermost_prose(f"{b.functie} ({b.naam})" if b.functie else b.naam)
            for b in activiteit.bewindspersonen
        )
        kop.append(f"Bewindspersonen: {namen}")

    moment_nu = _local(now or datetime.now(UTC))
    voet = (
        f"_Uit de agenda van de Tweede Kamer, opgehaald op {moment_nu.day} "
        f"{_MAANDEN[moment_nu.month - 1]} om {moment_nu:%H:%M}._"
    )

    def build(with_summaries: bool, limit: int | None) -> str:
        if activiteit.agendapunten:
            lijst = _agenda_lines(
                activiteit, samenvattingen if with_summaries else {}, limit
            )
        else:
            lijst = ["Er staan nog geen stukken op de agenda."]
        return "\n".join([*kop, "", *lijst, "", voet])

    # Too long: first drop the summaries, then the tail of the agenda. A
    # message Mattermost refuses leaves a channel without its agenda.
    bericht = build(True, None)
    if len(bericht) > _MESSAGE_MAX:
        bericht = build(False, None)
    limit = len(activiteit.agendapunten)
    while len(bericht) > _MESSAGE_MAX and limit > 1:
        limit = limit // 2
        bericht = build(False, limit)
    return bericht


class StartOutcome(enum.Enum):
    CREATED = "created"
    EXISTS = "exists"
    IN_PROGRESS = "in_progress"
    REFUSED = "refused"
    FAILED = "failed"


@dataclass(frozen=True)
class StartResult:
    outcome: StartOutcome
    # What was said in the thread under the convocatie; empty if nothing.
    message: str = ""
    channel_id: str | None = None


_RETRY_HINT = "Haal je reactie weg en zet hem opnieuw om het nog eens te proberen."


class DebatKanaalService:
    def __init__(
        self, session: AsyncSession, mattermost: MattermostService | None = None
    ) -> None:
        self.session = session
        self.mattermost = mattermost or MattermostService(session)

    async def close(self) -> None:
        await self.mattermost.close()

    async def start(
        self,
        *,
        item: ParlementairItem,
        source_channel_id: str,
        source_post_id: str,
        mattermost_user_id: str,
    ) -> StartResult:
        """Set up the channel for the debate this convocatie announces.

        Always answers in the thread under the convocatie, also when it
        does nothing. A button that stays silent looks broken, and the
        person who pressed it has no other way to find out why.
        """
        result = await self._start(
            item=item,
            source_channel_id=source_channel_id,
            mattermost_user_id=mattermost_user_id,
        )
        if result.message:
            posted = await self.mattermost.send_channel_message(
                source_channel_id, result.message, root_id=source_post_id
            )
            if not posted:
                logger.warning(
                    "Antwoord op de startknop onder post %s niet geplaatst",
                    source_post_id,
                )
        return result

    async def _start(
        self,
        *,
        item: ParlementairItem,
        source_channel_id: str,
        mattermost_user_id: str,
    ) -> StartResult:
        activiteit_id = (item.extra_data or {}).get("activiteit_id")
        if not activiteit_id:
            return StartResult(
                StartOutcome.REFUSED,
                "Bij dit stuk is geen vergadering bekend, dus ik kan er geen "
                "kanaal voor opzetten.",
            )

        try:
            async with httpx.AsyncClient(timeout=_TK_TIMEOUT) as client:
                activiteit = await fetch_activiteit(str(activiteit_id), client)
        except TkApiError:
            logger.warning(
                "Activiteit %s niet op te halen", activiteit_id, exc_info=True
            )
            return StartResult(
                StartOutcome.FAILED,
                "De agenda van de Tweede Kamer is nu niet op te halen. " + _RETRY_HINT,
            )
        if activiteit is None:
            return StartResult(
                StartOutcome.REFUSED,
                "Deze vergadering staat niet meer in de agenda van de Tweede Kamer.",
            )
        if activiteit.status == STATUS_CANCELLED:
            return StartResult(StartOutcome.REFUSED, "Deze vergadering is geannuleerd.")
        if activiteit.status == STATUS_MOVED:
            return StartResult(
                StartOutcome.REFUSED,
                "Deze vergadering is verplaatst. De nieuwe datum komt als een "
                "nieuwe convocatie; start het kanaal daaronder.",
            )
        if _is_over(activiteit):
            return StartResult(StartOutcome.REFUSED, "Deze vergadering is al geweest.")

        team_id = await self._team_of(source_channel_id)
        if not team_id:
            return StartResult(
                StartOutcome.FAILED,
                "Ik kan niet vinden in welk team dit kanaal staat. " + _RETRY_HINT,
            )

        sessie, existing = await self._claim(
            activiteit, team_id, item.id, mattermost_user_id
        )
        if sessie is None:
            if existing is not None and existing.channel_id:
                await self.mattermost.add_channel_member(
                    existing.channel_id, mattermost_user_id
                )
                return StartResult(
                    StartOutcome.EXISTS,
                    f"Er is al een kanaal voor dit debat: ~{existing.channel_name}",
                    channel_id=existing.channel_id,
                )
            # Someone else is setting it up right now. That run answers.
            return StartResult(StartOutcome.IN_PROGRESS)

        try:
            channel = await self._create_channel(activiteit, team_id)
        except MattermostPermissionError as exc:
            await self._release(sessie)
            return StartResult(
                StartOutcome.FAILED,
                "Ik mag in dit team geen kanalen aanmaken. Een "
                "Mattermost-beheerder moet de permissie "
                f"`{exc.permission}` aanzetten voor dit team (of mij eerst "
                "lid maken van het team); daarna werkt deze knop.",
            )
        except (MattermostUnavailableError, ChannelNameTakenError):
            logger.exception("Kanaal voor activiteit %s niet aangemaakt", activiteit.id)
            await self._release(sessie)
            return StartResult(
                StartOutcome.FAILED,
                "Het kanaal aanmaken is niet gelukt. " + _RETRY_HINT,
            )

        # Record the channel before anything else is posted in it. If the
        # rest breaks off, the channel is at least known, and a second
        # press points to it instead of creating another one.
        sessie.channel_id = channel["id"]
        sessie.channel_name = channel.get("name")
        await self.session.commit()

        samenvattingen = await self._summaries(activiteit)
        post_id = await self.mattermost.send_channel_message(
            sessie.channel_id, stukken_message(activiteit, samenvattingen)
        )
        if post_id:
            if not await self.mattermost.pin_post(post_id):
                logger.warning("Stukkenbericht %s niet vastgepind", post_id)
            sessie.stukken_post_id = post_id
            await self.session.commit()
        else:
            logger.warning(
                "Stukkenbericht voor kanaal %s niet geplaatst", sessie.channel_id
            )

        await self.mattermost.add_channel_member(sessie.channel_id, mattermost_user_id)

        tekst = (
            f"Kanaal ~{sessie.channel_name} staat klaar voor "
            f"**{escape_mattermost_md(activiteit.onderwerp)}**"
        )
        moment = format_moment(activiteit)
        if moment:
            tekst += f" ({moment})"
        tekst += "."
        if post_id:
            tekst += " De geagendeerde stukken staan er vastgepind."
        username = await self.mattermost.get_username(mattermost_user_id)
        # `get_username` returns the id itself when the lookup fails, and
        # an id is not something to mention.
        if username and username != mattermost_user_id:
            tekst += f" Gestart door @{username}."
        return StartResult(StartOutcome.CREATED, tekst, channel_id=sessie.channel_id)

    async def _team_of(self, channel_id: str) -> str | None:
        """The team a channel is in; from our own link if it knows."""
        stmt = select(MattermostChannelLink.team_id).where(
            MattermostChannelLink.channel_id == channel_id
        )
        team_id = (await self.session.execute(stmt)).scalar_one_or_none()
        if team_id:
            return team_id
        channel = await self.mattermost.get_channel(channel_id)
        return (channel or {}).get("team_id") or None

    async def _find(self, activiteit_id: str, team_id: str) -> DebatSessie | None:
        stmt = select(DebatSessie).where(
            DebatSessie.activiteit_id == activiteit_id,
            DebatSessie.team_id == team_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def _claim(
        self,
        activiteit: Activiteit,
        team_id: str,
        item_id: uuid.UUID,
        mattermost_user_id: str,
    ) -> tuple[DebatSessie | None, DebatSessie | None]:
        """Reserve this debate: ``(claim, None)`` or ``(None, existing)``.

        The row goes in before the channel exists. The unique constraint
        then decides between two simultaneous starts; a check followed by
        a create would let both through.
        """
        existing = await self._find(activiteit.id, team_id)
        if existing is not None:
            taken = existing.channel_id is not None
            fresh = existing.created_at > datetime.now(UTC) - STALE_CLAIM
            if taken or fresh:
                return None, existing
            logger.warning(
                "Afgebroken start voor activiteit %s overgenomen", activiteit.id
            )
            await self.session.delete(existing)
            await self.session.commit()

        sessie = DebatSessie(
            activiteit_id=activiteit.id,
            activiteit_nummer=activiteit.nummer,
            onderwerp=activiteit.onderwerp,
            aanvang=activiteit.aanvang,
            team_id=team_id,
            parlementair_item_id=item_id,
            started_by_mattermost_user_id=mattermost_user_id,
        )
        self.session.add(sessie)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return None, await self._find(activiteit.id, team_id)
        return sessie, None

    async def _release(self, sessie: DebatSessie) -> None:
        """Give the claim back, so a next press can try again."""
        try:
            await self.session.delete(sessie)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.exception(
                "Claim op activiteit %s niet vrijgegeven; hij verloopt vanzelf",
                sessie.activiteit_id,
            )

    async def _create_channel(self, activiteit: Activiteit, team_id: str) -> dict:
        args = {
            "team_id": team_id,
            "display_name": channel_display_name(activiteit),
            "header": channel_header(activiteit),
            "purpose": channel_purpose(activiteit),
        }
        # First the plain name, then once more with the nummer in it,
        # which is unique per activiteit.
        name = ""
        for with_nummer in (False, True):
            name = channel_name(activiteit, with_nummer=with_nummer)
            try:
                return await self.mattermost.create_channel(name=name, **args)
            except ChannelNameTakenError:
                orphan = await self._own_orphan(team_id, name)
                if orphan is not None:
                    logger.warning(
                        "Kanaal %s bestond al zonder sessie; overgenomen", name
                    )
                    return orphan
        raise ChannelNameTakenError(name)

    async def _own_orphan(self, team_id: str, name: str) -> dict | None:
        """The channel holding this name, if an earlier attempt left it.

        Mattermost can save a channel and still answer with an error, or
        answer after our timeout. The claim is then released, the channel
        stays, and the next press finds the name taken by its own
        predecessor. Taking another name would give one debate two
        channels.

        Only a channel the bot created and that no sessie points to. The
        name carries subject and date, so a channel that passes both is
        the one that attempt was making. Anything else (a channel a human
        made, or another debate with the same subject on the same day)
        keeps its name, and this debate gets the one with the nummer.
        """
        channel = await self.mattermost.get_channel_by_name(team_id, name)
        if channel is None:
            return None
        bot_user_id = await self.mattermost.get_bot_user_id()
        if not bot_user_id or channel.get("creator_id") != bot_user_id:
            return None
        stmt = select(DebatSessie.id).where(DebatSessie.channel_id == channel["id"])
        if (await self.session.execute(stmt)).first() is not None:
            return None
        return channel

    async def _summaries(self, activiteit: Activiteit) -> dict[str, str]:
        """Summaries we already have, per document nummer."""
        nummers = [
            doc.nummer for punt in activiteit.agendapunten for doc in punt.documenten
        ]
        if not nummers:
            return {}
        try:
            stmt = select(
                ParlementairItem.zaak_id, ParlementairItem.llm_samenvatting
            ).where(ParlementairItem.zaak_id.in_(nummers))
            rows = (await self.session.execute(stmt)).all()
        except Exception:
            # The agenda without summaries is still the agenda.
            await self.session.rollback()
            logger.exception("Samenvattingen voor de agenda niet opgehaald")
            return {}
        return {
            nummer: tekst
            for nummer, ruwe in rows
            if (tekst := _bruikbare_samenvatting(ruwe))
        }


def _is_over(activiteit: Activiteit, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    if activiteit.einde is not None:
        return activiteit.einde < now
    if activiteit.aanvang is not None:
        return activiteit.aanvang + _ASSUMED_DURATION < now
    return False
