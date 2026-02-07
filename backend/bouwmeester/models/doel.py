"""Doel model - extends CorpusNode for policy goals."""

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class Doel(Base):
    __tablename__ = "doel"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("corpus_node.id", ondelete="CASCADE"),
        primary_key=True,
    )
    type: Mapped[str] = mapped_column(
        comment="politiek|organisatorisch|operationeel",
        nullable=False,
    )
    bron: Mapped[str | None] = mapped_column(nullable=True)
    meetbaar: Mapped[bool] = mapped_column(default=False, server_default="false")
    streefwaarde: Mapped[str | None] = mapped_column(nullable=True)
