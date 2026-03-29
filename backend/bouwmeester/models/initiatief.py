"""Initiatief and InitiatiefEenheid models."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base


class Initiatief(Base):
    __tablename__ = "initiatief"
    __table_args__ = (UniqueConstraint("naam", name="uq_initiatief_naam"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    naam: Mapped[str] = mapped_column(nullable=False)
    beschrijving: Mapped[str | None] = mapped_column(Text, nullable=True)
    kleur: Mapped[str | None] = mapped_column(nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    created_by: Mapped["Person"] = relationship("Person", foreign_keys=[created_by_id])  # noqa: F821
    eenheden: Mapped[list["InitiatiefEenheid"]] = relationship(
        "InitiatiefEenheid",
        back_populates="initiatief",
        cascade="all, delete-orphan",
    )
    leads: Mapped[list["Lead"]] = relationship(  # noqa: F821
        "Lead",
        back_populates="initiatief",
    )


class InitiatiefEenheid(Base):
    __tablename__ = "initiatief_eenheid"

    initiatief_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("initiatief.id", ondelete="CASCADE"),
        primary_key=True,
    )
    eenheid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisatie_eenheid.id", ondelete="CASCADE"),
        primary_key=True,
    )
    rol: Mapped[str] = mapped_column(
        default="contributor",
        server_default="contributor",
        comment="eigenaar|contributor|viewer",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    initiatief: Mapped["Initiatief"] = relationship(
        "Initiatief", back_populates="eenheden"
    )
    eenheid: Mapped["OrganisatieEenheid"] = relationship("OrganisatieEenheid")  # noqa: F821
