"""PersonEmail model — multiple emails per person."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.person import Person


class PersonEmail(Base):
    __tablename__ = "person_email"
    # One address belongs to one person regardless of case: lookups compare
    # lower-case, so the constraint must too.
    __table_args__ = (
        Index("uq_person_email_lower", func.lower(text("email")), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(unique=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Who added the address to this person: decides at the first login
    # whether it is proven (``core.authority.hold_access_of_unproven_login``).
    # No foreign key on purpose: when the adder is deleted the address must
    # stay unproven, not turn into an unknown (and therefore trusted) one.
    added_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    person: Mapped["Person"] = relationship(
        "Person",
        back_populates="emails",
    )
