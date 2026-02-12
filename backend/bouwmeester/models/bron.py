"""Bron model - extends CorpusNode for source documents."""

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.bron_bijlage import BronBijlage


class Bron(Base):
    __tablename__ = "bron"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        primary_key=True,
    )
    type: Mapped[str] = mapped_column(
        default="overig",
        server_default="overig",
        comment="rapport|onderzoek|wetgeving|advies|opinie|beleidsnota|evaluatie|overig",
    )
    auteur: Mapped[str | None] = mapped_column(nullable=True)
    publicatie_datum: Mapped[date | None] = mapped_column(nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    bijlage: Mapped["BronBijlage | None"] = relationship(
        "BronBijlage",
        back_populates="bron",
        uselist=False,
        cascade="all, delete-orphan",
    )
