"""LeadContact model - links persons to leads with a role."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.lead import Lead
    from bouwmeester.models.person import Person


class LeadContact(Base):
    __tablename__ = "lead_contact"
    __table_args__ = (
        UniqueConstraint("lead_id", "person_id", "rol", name="uq_lead_contact"),
    )

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
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rol: Mapped[str] = mapped_column(
        default="contactpersoon",
        server_default="contactpersoon",
        comment="contactpersoon|opdrachtgever|betrokken",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    lead: Mapped["Lead"] = relationship("Lead", back_populates="contacts")
    person: Mapped["Person"] = relationship("Person")
