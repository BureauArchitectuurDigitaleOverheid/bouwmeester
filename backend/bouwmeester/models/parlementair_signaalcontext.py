"""Vrije tekst die de prompts vertelt wat voor deze scope een treffer is.

Waarom dit niet de beschrijving van het initiatief is, en dus een eigen
veld: die beschrijving is publiek (`/public/initiatief` geeft hem uit) en
is geschreven voor een mens die wil weten wat het initiatief doet. Wat een
taalmodel nodig heeft om ruis te scheiden is iets anders: wat telt niet
mee, welke homoniemen zijn er, welk woord is hier een metafoor. Dat is
afstelling van een zoekmachine, geen omschrijving, en het hoort niet op
een publieke pagina.

Het geval dat dit uitwees: "Het Fundament" is de naam van een project
(Fundament, Soevereine Overheidscloud) én een staande Haagse metafoor
("het fundament onder de begroting"). Van de 47 stukken in de eerste
inhaalslag kwamen er 46 via die term binnen, vrijwel allemaal de
metafoor. Geen enkele zoekterm lost dat op; het onderscheid is een
oordeel, en een oordeel heeft context nodig.

Per scope en niet per term: de termen zijn de vangst, de context is het
oordeel daaroverheen. Per term zou dezelfde tekst vijf keer onderhouden
moeten worden, en dan lopen de vijf kopieën uit elkaar.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base

# Genoeg voor een paar alinea's, en een harde bovengrens omdat deze tekst
# integraal in elke prompt belandt. Wie meer nodig heeft, beschrijft
# waarschijnlijk het initiatief in plaats van het signaal.
MAX_TEKST = 4000


class ParlementairSignaalcontext(Base):
    """Eén vrije tekst per scope, alleen voor de prompts."""

    __tablename__ = "parlementair_signaalcontext"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", name="uq_signaalcontext_scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Zelfde polymorfe sleutel als `ParlementairAbonnement`: geen FK, want
    # `scope_id` kan een initiatief of een lead zijn.
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    tekst: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment=(
            "Wat het taalmodel moet weten om een treffer van ruis te "
            "scheiden. Niet publiek: dit is afstelling, geen omschrijving."
        ),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
