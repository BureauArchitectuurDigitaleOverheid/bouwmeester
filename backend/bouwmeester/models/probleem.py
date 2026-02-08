"""Probleem model - extends CorpusNode for problems/drivers."""

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class Probleem(Base):
    __tablename__ = "probleem"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        primary_key=True,
    )
    urgentie: Mapped[str] = mapped_column(
        default="normaal",
        server_default="normaal",
        comment="laag|normaal|hoog|kritiek",
    )
    bron: Mapped[str | None] = mapped_column(nullable=True)
    impact_beschrijving: Mapped[str | None] = mapped_column(Text, nullable=True)
