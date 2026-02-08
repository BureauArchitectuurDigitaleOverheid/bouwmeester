"""Mention model - tracks @person and #node/#task/#tag mentions in descriptions."""

import uuid
from datetime import datetime

from sqlalchemy import Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class Mention(Base):
    __tablename__ = "mention"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="node|task|organisatie|notification",
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    mention_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="person|organisatie|node|task|tag",
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("ix_mention_target", "target_id", "mention_type"),
        Index("ix_mention_source", "source_id", "source_type"),
    )
