"""Temporal title records for CorpusNode."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.corpus_node import CorpusNode


class CorpusNodeTitle(Base):
    __tablename__ = "corpus_node_title"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(nullable=False)
    geldig_van: Mapped[date] = mapped_column(nullable=False)
    geldig_tot: Mapped[date | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    node: Mapped["CorpusNode"] = relationship(
        "CorpusNode",
        back_populates="title_records",
    )
