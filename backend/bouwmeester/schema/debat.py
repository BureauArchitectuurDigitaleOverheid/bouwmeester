"""Schemas for the debates page: what is coming, and starting a channel."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DebatTeam(BaseModel):
    """A Mattermost team the bot is in."""

    team_id: str
    team_name: str | None = None
    can_create_channel: bool


class DebatKanaal(BaseModel):
    """The channel that was set up for a debate, in one team."""

    team_id: str
    channel_name: str
    # Empty when the team's url name could not be read from Mattermost.
    channel_url: str | None = None
    # The sessie behind the channel: what stopping and resuming are asked for.
    sessie_id: UUID | None = None
    # Where the timeline stands: null (not yet found on Debat Direct),
    # gekoppeld, loopt, afgelopen or afgelast.
    tijdlijn_status: str | None = None
    # Whether the bot follows this debate: null, gekoppeld and loopt do.
    # Spelled out because null is a status here, not a missing value.
    wordt_gevolgd: bool = False


class DebatInitiatief(BaseModel):
    """An initiatief a debate was announced for."""

    id: UUID
    naam: str


class AankomendDebat(BaseModel):
    activiteit_id: str
    nummer: str | None = None
    soort: str | None = None
    onderwerp: str
    aanvang: datetime | None = None
    einde: datetime | None = None
    commissie: str | None = None
    agenda_url: str | None = None
    kanalen: list[DebatKanaal] = []
    # Where the debate stands according to Debat Direct: niet_begonnen,
    # bezig, geschorst or afgelopen. Null when Debat Direct does not know it
    # (it knows a debate on the day itself) or could not be read.
    stand: str | None = None
    # When it really started, once it has.
    begonnen_om: datetime | None = None
    # The initiatieven this debate was announced for, as far as this person
    # may see them.
    aangekondigd_voor: list[DebatInitiatief] = []


class AankomendeDebattenResponse(BaseModel):
    debatten: list[AankomendDebat]
    teams: list[DebatTeam]
    # Why there are no teams, if Mattermost could not be asked. The list of
    # debates is still worth showing then.
    mattermost_melding: str | None = None


class DebatStartRequest(BaseModel):
    activiteit_id: UUID
    team_id: str


class DebatStartResponse(BaseModel):
    # created | exists | in_progress | refused | failed
    outcome: str
    # For refused and failed: the reason, in Dutch, to show as is.
    melding: str | None = None
    kanaal: DebatKanaal | None = None


class DebatVolgenResponse(BaseModel):
    """What stopping or resuming left behind."""

    sessie_id: UUID
    tijdlijn_status: str | None = None
    wordt_gevolgd: bool


class GevolgdDebat(BaseModel):
    """A debate a team followed that is over, as the sessie remembers it.

    Only what was stored when the channel was set up: the kind of meeting
    and the committee are not kept on a sessie, so they are not here.
    """

    sessie_id: UUID
    activiteit_id: str
    nummer: str | None = None
    onderwerp: str
    aanvang: datetime | None = None
    agenda_url: str | None = None
    # Whether the channel still exists in Mattermost is not checked.
    kanaal: DebatKanaal
    # How the timeline ended: afgelopen (ran to its end, or was stopped by
    # hand: the two are stored the same), afgelast (cancelled or moved), or
    # null when the timeline never closed it.
    afloop: str | None = None
    # Events of the timeline that became a message in the channel.
    berichten: int = 0
    # Questions marked in the debate, and how many of those are still open.
    vragen: int = 0
    vragen_open: int = 0


class GevolgdeDebattenResponse(BaseModel):
    debatten: list[GevolgdDebat]
    # Of everything, not of this page.
    totaal: int
    limit: int
    offset: int


class DebatAankondigingCreate(BaseModel):
    activiteit_id: UUID


class DebatAankondigingResponse(BaseModel):
    """A debate that was announced for an initiatief."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    activiteit_id: str
    nummer: str | None = None
    soort: str | None = None
    onderwerp: str
    commissie: str | None = None
    aanvang: datetime | None = None
    einde: datetime | None = None
    agenda_url: str | None = None
    # aangekondigd | herinnerd | afgelast | voorbij
    stand: str
    created_at: datetime
    # Only on the answer to announcing: in how many channels the message
    # was posted. Zero when the initiatief has no channel yet.
    gepost_in: int | None = None
