"""StakeholderAssessment model — belang/houding/invloed of a person on a scope."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.person import Person


class StakeholderAssessment(Base):
    """Per-person assessment scoped to a corpus node or initiatief.

    Tracks how important a topic is to a stakeholder (belang), how they
    feel about it (houding), and how much influence they have (invloed).
    Distinct from `resource_permission` which tracks role/access.
    """

    __tablename__ = "stakeholder_assessment"
    __table_args__ = (
        UniqueConstraint(
            "person_id",
            "scope_type",
            "scope_id",
            name="uq_stakeholder_assessment_person_scope",
        ),
        Index(
            "ix_stakeholder_assessment_scope",
            "scope_type",
            "scope_id",
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
    scope_type: Mapped[str] = mapped_column(
        nullable=False,
        comment="corpus_node|initiatief",
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    belang: Mapped[int | None] = mapped_column(nullable=True)
    houding: Mapped[str | None] = mapped_column(
        nullable=True,
        comment="tegen|kritisch|neutraal|welwillend|voorstander",
    )
    invloed: Mapped[int | None] = mapped_column(nullable=True)
    notitie: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    person: Mapped["Person"] = relationship("Person", foreign_keys=[person_id])
    assessed_by: Mapped[Optional["Person"]] = relationship(
        "Person", foreign_keys=[assessed_by_id]
    )
