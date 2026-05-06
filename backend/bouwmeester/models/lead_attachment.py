"""LeadAttachment model - file attachment metadata for leads."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.lead import Lead


class LeadAttachment(Base):
    __tablename__ = "lead_attachment"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lead.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    soort: Mapped[str] = mapped_column(
        nullable=False,
        default="file",
        server_default="file",
        comment="file|link",
    )
    bestandsnaam: Mapped[str | None] = mapped_column(nullable=True)
    content_type: Mapped[str | None] = mapped_column(nullable=True)
    bestandsgrootte: Mapped[int | None] = mapped_column(nullable=True)
    pad: Mapped[str | None] = mapped_column(nullable=True)
    url: Mapped[str | None] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(
        nullable=False,
        default="upload",
        server_default="upload",
        comment="upload|mattermost",
    )
    source_ref: Mapped[str | None] = mapped_column(
        nullable=True,
        comment="bv. mattermost post_id",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    lead: Mapped["Lead"] = relationship("Lead", back_populates="attachments")
