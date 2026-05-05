"""LeadActivity model - notes, stage changes, and other activity on a lead."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.lead import Lead
    from bouwmeester.models.person import Person


class LeadActivity(Base):
    __tablename__ = "lead_activity"

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
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    content: Mapped[str] = mapped_column(Text, default="", server_default="")
    activity_type: Mapped[str] = mapped_column(
        default="note",
        server_default="note",
        comment="note|stage_change|meeting|call|email|evaluatie",
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSON, default=dict, server_default="{}"
    )
    uitkomst: Mapped[str | None] = mapped_column(Text, nullable=True)
    vervolgacties: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    lead: Mapped["Lead"] = relationship("Lead", back_populates="activities")
    author: Mapped[Optional["Person"]] = relationship("Person")
