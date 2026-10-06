"""Schemas for the debates page: what is coming, and starting a channel."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


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
