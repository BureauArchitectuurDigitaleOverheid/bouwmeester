"""Initiatief model."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base


class Initiatief(Base):
    __tablename__ = "initiatief"
    __table_args__ = (
        UniqueConstraint("naam", name="uq_initiatief_naam"),
        UniqueConstraint("slug", name="uq_initiatief_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    naam: Mapped[str] = mapped_column(nullable=False)
    slug: Mapped[str | None] = mapped_column(nullable=True)
    beschrijving: Mapped[str | None] = mapped_column(Text, nullable=True)
    kleur: Mapped[str | None] = mapped_column(nullable=True)
    funnel_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    public_page_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    score_strategisch_label: Mapped[str | None] = mapped_column(nullable=True)
    score_politiek_label: Mapped[str | None] = mapped_column(nullable=True)
    score_positie_label: Mapped[str | None] = mapped_column(nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    created_by: Mapped["Person"] = relationship("Person", foreign_keys=[created_by_id])  # noqa: F821
    leads: Mapped[list["Lead"]] = relationship(  # noqa: F821
        "Lead",
        back_populates="initiatief",
    )
    updates: Mapped[list["InitiatiefUpdatePost"]] = relationship(  # noqa: F821
        "InitiatiefUpdatePost",
        back_populates="initiatief",
        cascade="all, delete-orphan",
        order_by="InitiatiefUpdatePost.created_at.desc()",
    )
    lead_columns: Mapped[list["LeadColumn"]] = relationship(  # noqa: F821
        "LeadColumn",
        back_populates="initiatief",
        cascade="all, delete-orphan",
        order_by="LeadColumn.sort_order",
    )
