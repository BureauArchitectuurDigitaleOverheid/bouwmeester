"""Beleidsoptie model - extends CorpusNode for policy options/alternatives."""

import uuid

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class Beleidsoptie(Base):
    __tablename__ = "beleidsoptie"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(
        default="verkennend",
        server_default="verkennend",
        comment="verkennend|voorgesteld|gekozen|afgewezen",
    )
    kosten_indicatie: Mapped[str | None] = mapped_column(nullable=True)
    verwacht_effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    risico: Mapped[str | None] = mapped_column(Text, nullable=True)
