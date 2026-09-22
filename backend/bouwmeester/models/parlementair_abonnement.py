"""ParlementairAbonnement - een zoekterm waarop een initiatief of lead volgt.

Het abonnement hangt aan het initiatief (of de lead), niet aan het
Mattermost-kanaal. Een kanaal draagt in `mattermost_channel_link` een
unique constraint op `channel_id`, dus het hangt sowieso al aan precies
één scope; de termen daar nog eens aan ophangen zou dezelfde relatie via
een omweg leggen die breekt zodra iemand `/bouwmeester ontkoppel` doet.
Bezorging is daarmee een join over die tabel in plaats van een tweede
plek waar hetzelfde geconfigureerd staat.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.person import Person


SCOPE_INITIATIEF = "initiatief"
SCOPE_LEAD = "lead"


class ParlementairAbonnement(Base):
    """Eén zoekterm, gevolgd namens één initiatief of lead.

    `scope_id` is polymorf en draagt geen DB-FK, net als in
    `MattermostChannelLink`: het wijst zowel naar `initiatief.id` als naar
    `lead.id`. De aanroeper checkt `scope_type` vóór gebruik.
    """

    __tablename__ = "parlementair_abonnement"
    __table_args__ = (
        UniqueConstraint(
            "scope_type",
            "scope_id",
            "term_genormaliseerd",
            name="uq_abonnement_scope_term",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    scope_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="initiatief|lead",
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    term: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Zoekterm zoals de gebruiker hem intypte, inclusief hoofdletters",
    )
    term_genormaliseerd: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment=(
            "Lowercase, whitespace-genormaliseerde vorm. Alleen voor de unique "
            "constraint: 'RegelRecht' en 'regelrecht' zijn hetzelfde abonnement. "
            "De zoekopdracht zelf gaat met `term` de bron in."
        ),
    )
    is_frase: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment=(
            "Quote de term bij het zoeken. Een ongequote meerwoordsterm OR't de "
            "woorden bij tkconv en levert dan willekeurige treffers op."
        ),
    )
    actief: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    laatste_treffer_op: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Wanneer deze term voor het laatst iets opleverde",
    )
    treffers_totaal: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment=(
            "Aantal documenten dat deze term ooit aandroeg. Maakt een breed "
            "vangnet bestuurbaar: een term die niets oplevert is zichtbaar, "
            "net als een term die alles binnenhaalt."
        ),
    )
    weggeklikt_totaal: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment=(
            "Hoe vaak een treffer van deze term als niet-relevant is gemarkeerd. "
            "Signaal voor de gebruiker, nooit een automatische deactivering."
        ),
    )
    notitie: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Waarom deze term gevolgd wordt",
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    created_by: Mapped[Optional["Person"]] = relationship(
        "Person", foreign_keys=[created_by_id]
    )

    @staticmethod
    def normaliseer(term: str) -> str:
        """Normaliseer een term voor de unique constraint."""
        return " ".join(term.strip().strip('"').split()).lower()

    def zoekopdracht(self) -> str:
        """De string die de bron in gaat.

        Quoten is bij tkconv niet cosmetisch: `nederlandse digitale dienst`
        zonder quotes OR't de drie woorden en levert onder meer een
        WODC-monitor over zorgcontinuïteit op.
        """
        kern = self.term.strip().strip('"')
        return f'"{kern}"' if self.is_frase else kern
