"""Temporal name records for OrganisatieEenheid."""

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bouwmeester.core.database import Base

if TYPE_CHECKING:
    from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid


class OrganisatieEenheidNaam(Base):
    __tablename__ = "organisatie_eenheid_naam"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    eenheid_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisatie_eenheid.id", ondelete="CASCADE"),
        nullable=False,
    )
    naam: Mapped[str] = mapped_column(nullable=False)
    geldig_van: Mapped[date] = mapped_column(nullable=False)
    geldig_tot: Mapped[date | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    eenheid: Mapped["OrganisatieEenheid"] = relationship(
        "OrganisatieEenheid",
        back_populates="namen",
    )
