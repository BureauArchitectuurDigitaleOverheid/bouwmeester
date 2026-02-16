"""Opdracht model - assignments and subsidies linked to instruments.

Opdracht is a standalone transactional entity (not a CorpusNode) that tracks
budget and spending per begrotingsjaar for a given instrument.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.corpus_node import CorpusNode
    from bouwmeester.models.externe_organisatie import ExterneOrganisatie
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
    from bouwmeester.models.person import Person


class Opdracht(Base):
    __tablename__ = "opdracht"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    type: Mapped[str] = mapped_column(
        comment="opdracht|subsidie",
        nullable=False,
    )
    titel: Mapped[str] = mapped_column(nullable=False)
    beschrijving: Mapped[str | None] = mapped_column(Text, nullable=True)
    begrotingsjaar: Mapped[int] = mapped_column(nullable=False, index=True)

    # Financieel
    budget: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=14, scale=2), nullable=True
    )
    gerealiseerd: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=14, scale=2), nullable=True
    )
    kostensoort: Mapped[str | None] = mapped_column(
        comment="investering|exploitatie|gemengd",
        nullable=True,
    )
    volgend_jaar_benodigd: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=14, scale=2), nullable=True
    )
    volgend_jaar_aangevraagd: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=14, scale=2), nullable=True
    )

    # Links
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opdrachtnemer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("externe_organisatie.id", ondelete="SET NULL"),
        nullable=True,
    )
    opdrachtgever_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisatie_eenheid.id", ondelete="SET NULL"),
        nullable=True,
    )
    verantwoordelijke_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Subsidie-specifiek (nullable)
    subsidieregeling: Mapped[str | None] = mapped_column(nullable=True)
    beschikking_nummer: Mapped[str | None] = mapped_column(nullable=True)

    # Status & dates
    status: Mapped[str] = mapped_column(
        default="concept",
        server_default="concept",
        comment="concept|actief|afgerond|verantwoord|geannuleerd",
    )
    referentie: Mapped[str | None] = mapped_column(nullable=True)
    startdatum: Mapped[date | None] = mapped_column(nullable=True)
    einddatum: Mapped[date | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    instrument: Mapped["CorpusNode"] = relationship(
        "CorpusNode",
        foreign_keys=[instrument_id],
        lazy="joined",
    )
    opdrachtnemer: Mapped["ExterneOrganisatie | None"] = relationship(
        "ExterneOrganisatie",
        foreign_keys=[opdrachtnemer_id],
        lazy="joined",
    )
    opdrachtgever: Mapped["OrganisatieEenheid | None"] = relationship(
        "OrganisatieEenheid",
        foreign_keys=[opdrachtgever_id],
        lazy="joined",
    )
    verantwoordelijke: Mapped["Person | None"] = relationship(
        "Person",
        foreign_keys=[verantwoordelijke_id],
        lazy="joined",
    )
    node_koppelingen: Mapped[list["OpdrachtNode"]] = relationship(
        "OpdrachtNode",
        back_populates="opdracht",
        cascade="all, delete-orphan",
    )


class OpdrachtNode(Base):
    """Junction table linking an Opdracht to additional CorpusNodes."""

    __tablename__ = "opdracht_node"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    opdracht_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opdracht.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        nullable=False,
    )
    relatie_type: Mapped[str] = mapped_column(
        comment="bekostigt|draagt_bij_aan",
        default="bekostigt",
        server_default="bekostigt",
    )

    opdracht: Mapped["Opdracht"] = relationship(
        "Opdracht",
        back_populates="node_koppelingen",
    )
    node: Mapped["CorpusNode"] = relationship(
        "CorpusNode",
        foreign_keys=[node_id],
    )
