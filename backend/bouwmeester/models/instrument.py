"""Instrument model - extends CorpusNode for policy instruments."""

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class Instrument(Base):
    __tablename__ = "instrument"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        primary_key=True,
    )
    type: Mapped[str] = mapped_column(
        comment="wetgeving|subsidie|voorlichting|handhaving|overig",
        nullable=False,
    )
    rechtsgrondslag: Mapped[str | None] = mapped_column(nullable=True)
