"""Dossier model - extends CorpusNode for policy files/topics."""

import uuid
from datetime import date

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class Dossier(Base):
    __tablename__ = "dossier"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        primary_key=True,
    )
    fase: Mapped[str] = mapped_column(
        comment="verkenning|beleidsvorming|uitvoering|evaluatie",
        nullable=False,
    )
    eigenaar: Mapped[str | None] = mapped_column(nullable=True)
    deadline: Mapped[date | None] = mapped_column(nullable=True)
    prioriteit: Mapped[str] = mapped_column(
        default="normaal",
        server_default="normaal",
        comment="laag|normaal|hoog|kritiek",
    )
