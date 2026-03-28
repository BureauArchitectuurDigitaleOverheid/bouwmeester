"""ResourcePermission model - unified resource-level access control.

Replaces the domain-specific junction tables (NodeStakeholder,
InitiatiefMember, LeadContact, TeamMember) with a single polymorphic
table that links a person to any resource with a role.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base


class ResourcePermission(Base):
    """Links a person to a resource with a role."""

    __tablename__ = "resource_permission"
    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "resource_type",
            "resource_id",
            "rol",
            name="uq_resource_permission",
        ),
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
    resource_type: Mapped[str] = mapped_column(
        nullable=False,
        comment="corpus_node|initiatief|lead|team|opdracht",
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Polymorphic FK - references the PK of the resource table",
    )
    rol: Mapped[str] = mapped_column(
        nullable=False,
        comment="eigenaar|betrokken|adviseur|indiener|contributor|contactpersoon|opdrachtgever|coordinator|lid",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    person: Mapped["Person"] = relationship("Person")  # noqa: F821
