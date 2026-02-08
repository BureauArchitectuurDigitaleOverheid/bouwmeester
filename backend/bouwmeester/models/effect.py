"""Effect model - extends CorpusNode for outcomes/effects."""

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class Effect(Base):
    __tablename__ = "effect"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        primary_key=True,
    )
    type: Mapped[str] = mapped_column(
        comment="output|outcome|impact",
        nullable=False,
    )
    indicator: Mapped[str | None] = mapped_column(nullable=True)
    streefwaarde: Mapped[str | None] = mapped_column(nullable=True)
    meetbaar: Mapped[bool] = mapped_column(default=False, server_default="false")
