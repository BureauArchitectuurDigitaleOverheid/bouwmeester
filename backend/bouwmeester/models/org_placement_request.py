"""OrgPlacementRequest model - onboarding placement requests."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid
    from bouwmeester.models.person import Person


class OrgPlacementRequest(Base):
    __tablename__ = "org_placement_request"

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
    organisatie_eenheid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisatie_eenheid.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        default="pending",
        server_default="pending",
        comment="pending|approved|denied",
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    person: Mapped["Person"] = relationship("Person", foreign_keys=[person_id])
    organisatie_eenheid: Mapped["OrganisatieEenheid"] = relationship(
        "OrganisatieEenheid"
    )
    decider: Mapped[Optional["Person"]] = relationship(
        "Person", foreign_keys=[decided_by]
    )
