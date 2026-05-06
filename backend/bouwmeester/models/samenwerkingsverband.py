"""Samenwerkingsverband model: ad-hoc samenwerkingsvormen los van de
hierarchische OrganisatieEenheid-boom (programma, werkgroep,
opschalingsticket, ketenproject, stuurgroep, taskforce, innovatiebudget,
community_of_practice, pilot, convenant)."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.persoon_samenwerkingsverband import (
        PersoonSamenwerkingsverband,
    )


class Samenwerkingsverband(Base):
    __tablename__ = "samenwerkingsverband"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    naam: Mapped[str] = mapped_column(nullable=False)
    type: Mapped[str] = mapped_column(
        nullable=False,
        comment=(
            "programma|werkgroep|opschalingsticket|ketenproject|stuurgroep|"
            "taskforce|innovatiebudget|community_of_practice|pilot|convenant"
        ),
    )
    beschrijving: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_datum: Mapped[date | None] = mapped_column(Date, nullable=True)
    eind_datum: Mapped[date | None] = mapped_column(Date, nullable=True)
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

    leden: Mapped[list["PersoonSamenwerkingsverband"]] = relationship(
        "PersoonSamenwerkingsverband",
        back_populates="samenwerkingsverband",
        cascade="all, delete-orphan",
    )
