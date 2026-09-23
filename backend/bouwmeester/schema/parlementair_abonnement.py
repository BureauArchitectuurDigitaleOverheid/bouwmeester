"""Schema's voor parlementaire abonnementen op zoektermen."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from bouwmeester.models.signaalcontext import MAX_TEKST


class AbonnementCreate(BaseModel):
    term: str = Field(min_length=3, max_length=255)
    is_frase: bool = True
    notitie: str | None = None

    @field_validator("term")
    @classmethod
    def strip_quotes(cls, v: str) -> str:
        """Haal aanhalingstekens eruit; het quoten gebeurt bij het zoeken.

        Een gebruiker die zelf quotes typt zou anders op '"term"' zoeken.
        """
        gestript = v.strip().strip('"').strip()
        if len(gestript) < 3:
            raise ValueError(
                "Een zoekterm van minder dan drie tekens levert te veel ruis op"
            )
        return gestript


class AbonnementUpdate(BaseModel):
    actief: bool | None = None
    notitie: str | None = None
    uitgezette_categorieen: list[str] | None = None
    minimum_relevantie: int | None = Field(default=None, ge=0, le=100)


class AbonnementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scope_type: str
    scope_id: UUID
    term: str
    is_frase: bool
    actief: bool
    laatste_treffer_op: datetime | None
    treffers_totaal: int
    weggeklikt_totaal: int
    notitie: str | None
    uitgezette_categorieen: list[str] | None
    minimum_relevantie: int
    # Null zolang de eenmalige inhaalslag nog niet is gedaan; de UI kan
    # daarmee tonen dat een verse term nog de feed-week gaat ophalen.
    ingehaald_op: datetime | None
    created_by_id: UUID | None
    created_at: datetime


class AbonnementMetTellingResponse(AbonnementResponse):
    """Abonnement met het werkelijke aantal gekoppelde treffers.

    `treffers_totaal` telt op bij elke ronde; `treffers` is het aantal
    items dat er nu aan hangt. Die twee lopen uiteen zodra een item wordt
    verwijderd, en het verschil is precies wat iemand wil zien die een
    brede term beoordeelt.
    """

    treffers: int = 0


class SuggestieResponse(BaseModel):
    """Een voorgestelde zoekterm, met wat hij bij de bron oplevert.

    `nieuwe_treffers` is het getal dat telt: een term die alleen dubbelt
    met wat je al volgt voegt niets toe, hoeveel treffers hij ook heeft.
    """

    term: str
    reden: str
    soort: str
    treffers: int
    nieuwe_treffers: int
    voorbeelden: list[str] = []


class SignaalcontextResponse(BaseModel):
    """De vrije tekst die de prompts vertelt wat hier een treffer is.

    Bewust gescheiden van de beschrijving van het initiatief: die is
    publiek en beschrijft wat het initiatief doet, deze is intern en
    beschrijft wat wel en niet meetelt. Eén veld voor allebei maakt de
    tekst voor beide publieken onleesbaar.
    """

    tekst: str = ""


class SignaalcontextUpdate(BaseModel):
    """Leeg opslaan is toegestaan: dat wist de context."""

    tekst: str = Field(default="", max_length=MAX_TEKST)
