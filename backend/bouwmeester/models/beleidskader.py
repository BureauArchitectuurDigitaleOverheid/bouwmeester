"""Beleidskader model - extends CorpusNode for policy frameworks."""

import uuid
from datetime import date

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class Beleidskader(Base):
    __tablename__ = "beleidskader"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        primary_key=True,
    )
    scope: Mapped[str] = mapped_column(
        comment="nationaal|eu|internationaal",
        nullable=False,
    )
    geldig_van: Mapped[date | None] = mapped_column(nullable=True)
    geldig_tot: Mapped[date | None] = mapped_column(nullable=True)
