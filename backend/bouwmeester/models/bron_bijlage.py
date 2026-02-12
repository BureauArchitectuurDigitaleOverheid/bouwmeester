"""BronBijlage model - file attachment metadata for Bron nodes."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base


class BronBijlage(Base):
    __tablename__ = "bron_bijlage"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    bron_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bron.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    bestandsnaam: Mapped[str] = mapped_column(nullable=False)
    content_type: Mapped[str] = mapped_column(nullable=False)
    bestandsgrootte: Mapped[int] = mapped_column(nullable=False)
    pad: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    bron: Mapped["Bron"] = relationship(  # noqa: F821
        "Bron",
        back_populates="bijlage",
    )
