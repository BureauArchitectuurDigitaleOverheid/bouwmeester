"""Maatregel model - extends CorpusNode for specific measures."""

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class Maatregel(Base):
    __tablename__ = "maatregel"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        primary_key=True,
    )
    kosten_indicatie: Mapped[str | None] = mapped_column(nullable=True)
    verwacht_effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    uitvoerder: Mapped[str | None] = mapped_column(nullable=True)
