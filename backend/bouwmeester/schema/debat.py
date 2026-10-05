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
